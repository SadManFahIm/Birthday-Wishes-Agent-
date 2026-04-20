"""
email_digest.py
───────────────
Weekly Email Digest module for Birthday Wishes Agent.

Sends a comprehensive weekly summary email every Monday with:
  - Total wishes sent this week
  - Upcoming birthdays (next 7 days)
  - Fading connections that need attention
  - Top engaged contacts
  - Platform breakdown
  - A/B test results summary

Setup:
  Uses the same EMAIL_SENDER and EMAIL_PASSWORD from .env
  Add DIGEST_RECIPIENTS to .env for custom recipients

Run manually:
    from email_digest import send_weekly_digest
    await send_weekly_digest()
"""

import logging
import smtplib
import sqlite3
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import dotenv_values

logger  = logging.getLogger(__name__)
_env    = dotenv_values(".env")
DB_FILE = Path("agent_history.db")

EMAIL_SENDER       = _env.get("EMAIL_SENDER", "")
EMAIL_PASSWORD     = _env.get("EMAIL_PASSWORD", "")
DIGEST_RECIPIENTS  = _env.get("DIGEST_RECIPIENTS",
                               _env.get("EMAIL_SENDER", ""))


# ──────────────────────────────────────────────
# DATA COLLECTORS
# ──────────────────────────────────────────────
def get_weekly_wishes() -> dict:
    """Get wish stats for the past 7 days."""
    if not DB_FILE.exists():
        return {"total": 0, "contacts": [], "by_platform": {}}

    week_ago = (date.today() - timedelta(days=7)).isoformat()
    try:
        conn = sqlite3.connect(DB_FILE)

        total = conn.execute(
            "SELECT COUNT(*) FROM history "
            "WHERE date >= ? AND dry_run = 0",
            (week_ago,),
        ).fetchone()[0]

        contacts = conn.execute(
            "SELECT contact, task, date FROM history "
            "WHERE date >= ? AND dry_run = 0 "
            "ORDER BY date DESC LIMIT 10",
            (week_ago,),
        ).fetchall()

        by_platform = {}
        for platform in ["LinkedIn", "WhatsApp", "Facebook", "Instagram"]:
            count = conn.execute(
                "SELECT COUNT(*) FROM history "
                "WHERE date >= ? AND task LIKE ? AND dry_run = 0",
                (week_ago, f"%{platform}%"),
            ).fetchone()[0]
            if count > 0:
                by_platform[platform] = count

        conn.close()
        return {
            "total":       total,
            "contacts":    [{"contact": r[0], "task": r[1], "date": r[2]}
                            for r in contacts],
            "by_platform": by_platform,
        }
    except Exception as e:
        logger.error("❌ Weekly wishes error: %s", e)
        return {"total": 0, "contacts": [], "by_platform": {}}


def get_upcoming_birthdays(days: int = 7) -> list[dict]:
    """Get contacts with birthdays in the next N days from calendar."""
    if not DB_FILE.exists():
        return []
    try:
        conn  = sqlite3.connect(DB_FILE)
        rows  = conn.execute(
            "SELECT name, birthday, job_title, company "
            "FROM (SELECT name, birthday, '' as job_title, '' as company "
            "      FROM (SELECT DISTINCT contact as name, '' as birthday "
            "            FROM history WHERE dry_run=0))"
        ).fetchall()
        conn.close()

        # Try calendar table if exists
        try:
            conn = sqlite3.connect(DB_FILE)
            # Check if we have a contacts table with birthdays
            rows = conn.execute(
                "SELECT name, birthday FROM contacts "
                "WHERE birthday IS NOT NULL AND birthday != '' LIMIT 20"
            ).fetchall()
            conn.close()
        except Exception:
            rows = []

        upcoming = []
        today    = date.today()
        for row in rows:
            name     = row[0]
            bday_str = row[1] if len(row) > 1 else ""
            if not bday_str:
                continue
            try:
                # Parse MM-DD format
                parts = bday_str.split("-")
                if len(parts) >= 2:
                    month = int(parts[-2])
                    day   = int(parts[-1])
                    bday  = date(today.year, month, day)
                    if bday < today:
                        bday = date(today.year + 1, month, day)
                    days_until = (bday - today).days
                    if 0 <= days_until <= days:
                        upcoming.append({
                            "name":       name,
                            "birthday":   bday.strftime("%B %d"),
                            "days_until": days_until,
                        })
            except Exception:
                continue

        return sorted(upcoming, key=lambda x: x["days_until"])
    except Exception:
        return []


def get_fading_connections(limit: int = 5) -> list[dict]:
    """Get contacts whose interaction is fading."""
    if not DB_FILE.exists():
        return []
    try:
        six_months_ago = (date.today() - timedelta(days=180)).isoformat()
        three_months   = (date.today() - timedelta(days=90)).isoformat()

        conn = sqlite3.connect(DB_FILE)
        rows = conn.execute(
            "SELECT contact, MAX(date) as last_date, COUNT(*) as total "
            "FROM history WHERE dry_run = 0 "
            "GROUP BY contact "
            "HAVING last_date <= ? "
            "ORDER BY last_date ASC LIMIT ?",
            (three_months, limit),
        ).fetchall()
        conn.close()

        fading = []
        for row in rows:
            contact   = row[0]
            last_date = row[1]
            total     = row[2]
            try:
                days_ago = (date.today() -
                            date.fromisoformat(last_date)).days
            except Exception:
                days_ago = 999

            fading.append({
                "contact":    contact,
                "last_date":  last_date,
                "days_ago":   days_ago,
                "total_interactions": total,
            })
        return fading
    except Exception:
        return []


def get_top_contacts(limit: int = 5) -> list[dict]:
    """Get most engaged contacts this week."""
    if not DB_FILE.exists():
        return []
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    try:
        conn = sqlite3.connect(DB_FILE)
        rows = conn.execute(
            "SELECT contact, COUNT(*) as count "
            "FROM history WHERE date >= ? AND dry_run = 0 "
            "GROUP BY contact ORDER BY count DESC LIMIT ?",
            (week_ago, limit),
        ).fetchall()
        conn.close()
        return [{"contact": r[0], "count": r[1]} for r in rows]
    except Exception:
        return []


def get_ab_summary() -> dict:
    """Get A/B test summary."""
    if not DB_FILE.exists():
        return {}
    try:
        conn = sqlite3.connect(DB_FILE)
        rows = conn.execute(
            "SELECT variant, COUNT(*) as sends, SUM(replied) as replies "
            "FROM ab_tests WHERE dry_run = 0 GROUP BY variant"
        ).fetchall()
        conn.close()
        result = {}
        for row in rows:
            sends   = row[1] or 0
            replies = row[2] or 0
            result[row[0]] = {
                "sends":      sends,
                "replies":    replies,
                "reply_rate": round(replies / sends * 100, 1) if sends else 0,
            }
        return result
    except Exception:
        return {}


# ──────────────────────────────────────────────
# EMAIL BUILDER
# ──────────────────────────────────────────────
def build_digest_email(data: dict) -> tuple[str, str]:
    """Build the weekly digest email HTML."""
    week_label    = date.today().strftime("Week of %B %d, %Y")
    wishes        = data["wishes"]
    upcoming      = data["upcoming_birthdays"]
    fading        = data["fading_connections"]
    top           = data["top_contacts"]
    ab            = data["ab_summary"]

    subject = f"🎂 Weekly Birthday Agent Digest — {week_label}"

    # ── Upcoming Birthdays ──────────────────
    if upcoming:
        upcoming_rows = "".join(
            f"""<tr>
              <td style='padding:8px 12px;color:#FAFAFA;'>{r['name']}</td>
              <td style='padding:8px 12px;color:#4CAF50;font-weight:600;'>{r['birthday']}</td>
              <td style='padding:8px 12px;text-align:center;'>
                {'🎂 Today!' if r['days_until'] == 0
                 else f"In {r['days_until']} day{'s' if r['days_until'] > 1 else ''}"}
              </td>
            </tr>"""
            for r in upcoming
        )
        upcoming_section = f"""
        <h3 style='color:#FFC107;margin:24px 0 12px;'>
          🎈 Upcoming Birthdays ({len(upcoming)})
        </h3>
        <table style='width:100%;border-collapse:collapse;
                      background:#1E2329;border-radius:8px;overflow:hidden;'>
          <tr style='background:#2E3440;'>
            <th style='padding:10px 12px;text-align:left;color:#aaa;'>Contact</th>
            <th style='padding:10px 12px;text-align:left;color:#aaa;'>Birthday</th>
            <th style='padding:10px 12px;color:#aaa;'>When</th>
          </tr>
          {upcoming_rows}
        </table>"""
    else:
        upcoming_section = """
        <div style='background:#1E2329;border-radius:8px;padding:16px;
                    margin-top:16px;color:#555;text-align:center;'>
          No upcoming birthdays in the next 7 days.
        </div>"""

    # ── Fading Connections ──────────────────
    if fading:
        fading_rows = "".join(
            f"""<tr>
              <td style='padding:8px 12px;color:#FAFAFA;'>{r['contact']}</td>
              <td style='padding:8px 12px;color:#F44336;'>
                {r['days_ago']} days ago
              </td>
              <td style='padding:8px 12px;color:#555;font-size:0.85rem;'>
                {r['total_interactions']} total interactions
              </td>
            </tr>"""
            for r in fading
        )
        fading_section = f"""
        <h3 style='color:#F44336;margin:24px 0 12px;'>
          📉 Fading Connections ({len(fading)})
        </h3>
        <p style='color:#888;font-size:0.85rem;margin-bottom:12px;'>
          These contacts haven't heard from you in a while. Consider reaching out!
        </p>
        <table style='width:100%;border-collapse:collapse;
                      background:#1E2329;border-radius:8px;overflow:hidden;'>
          <tr style='background:#2E3440;'>
            <th style='padding:10px 12px;text-align:left;color:#aaa;'>Contact</th>
            <th style='padding:10px 12px;text-align:left;color:#aaa;'>Last Contact</th>
            <th style='padding:10px 12px;text-align:left;color:#aaa;'>History</th>
          </tr>
          {fading_rows}
        </table>"""
    else:
        fading_section = ""

    # ── Top Contacts ────────────────────────
    if top:
        top_items = "".join(
            f"<div style='display:flex;justify-content:space-between;"
            f"padding:6px 0;border-bottom:1px solid #2E3440;'>"
            f"<span>{r['contact']}</span>"
            f"<span style='color:#4CAF50;font-weight:600;'>"
            f"{r['count']} interaction{'s' if r['count'] > 1 else ''}</span></div>"
            for r in top
        )
        top_section = f"""
        <div style='background:#1E2329;border-radius:8px;padding:16px;margin-top:16px;'>
          <h4 style='color:#4CAF50;margin-bottom:12px;'>🌟 Most Active This Week</h4>
          {top_items}
        </div>"""
    else:
        top_section = ""

    # ── A/B Summary ─────────────────────────
    ab_section = ""
    if ab:
        a_rate = ab.get("A", {}).get("reply_rate", 0)
        b_rate = ab.get("B", {}).get("reply_rate", 0)
        winner = "A" if a_rate > b_rate + 5 else "B" if b_rate > a_rate + 5 else None
        ab_section = f"""
        <div style='background:#1E2329;border-radius:8px;padding:16px;margin-top:16px;'>
          <h4 style='color:#4CAF50;margin-bottom:12px;'>🧪 A/B Test Update</h4>
          <div style='display:flex;gap:16px;'>
            <div style='flex:1;text-align:center;'>
              <div style='font-size:1.4rem;font-weight:700;
                          color:{"#4CAF50" if winner=="A" else "#aaa"};'>
                {a_rate}%
              </div>
              <div style='color:#888;font-size:0.8rem;'>Variant A reply rate</div>
            </div>
            <div style='flex:1;text-align:center;'>
              <div style='font-size:1.4rem;font-weight:700;
                          color:{"#4CAF50" if winner=="B" else "#aaa"};'>
                {b_rate}%
              </div>
              <div style='color:#888;font-size:0.8rem;'>Variant B reply rate</div>
            </div>
          </div>
          {f'<div style="text-align:center;margin-top:8px;color:#4CAF50;font-weight:600;">🏆 Variant {winner} is winning!</div>' if winner else '<div style="text-align:center;margin-top:8px;color:#888;font-size:0.85rem;">Still testing — too close to call</div>'}
        </div>"""

    # ── Platform Breakdown ──────────────────
    platform_items = "".join(
        f"<span style='background:#2E3440;border-radius:8px;padding:4px 12px;"
        f"margin:3px;display:inline-block;font-size:0.82rem;'>"
        f"{p}: <strong style='color:#4CAF50;'>{c}</strong></span>"
        for p, c in wishes["by_platform"].items()
    ) if wishes["by_platform"] else "<span style='color:#555;'>No platform data</span>"

    # ── Full HTML ───────────────────────────
    html = f"""
<!DOCTYPE html>
<html>
<body style='font-family:"Segoe UI",sans-serif;max-width:680px;margin:auto;
             background:#0E1117;color:#FAFAFA;padding:20px;'>

  <!-- HEADER -->
  <div style='background:linear-gradient(135deg,#1a237e,#4CAF50);
              padding:28px;border-radius:12px;text-align:center;'>
    <h1 style='margin:0;font-size:1.6rem;'>🎂 Weekly Digest</h1>
    <p style='margin:6px 0 0;opacity:0.85;font-size:0.9rem;'>{week_label}</p>
  </div>

  <!-- SUMMARY CARDS -->
  <div style='display:flex;gap:12px;margin:20px 0;flex-wrap:wrap;'>
    <div style='flex:1;background:#1E2329;border-radius:10px;
                padding:16px;text-align:center;min-width:120px;'>
      <div style='font-size:2rem;font-weight:700;color:#4CAF50;'>
        {wishes["total"]}
      </div>
      <div style='color:#888;font-size:0.82rem;'>Actions This Week</div>
    </div>
    <div style='flex:1;background:#1E2329;border-radius:10px;
                padding:16px;text-align:center;min-width:120px;'>
      <div style='font-size:2rem;font-weight:700;color:#FFC107;'>
        {len(upcoming)}
      </div>
      <div style='color:#888;font-size:0.82rem;'>Upcoming Birthdays</div>
    </div>
    <div style='flex:1;background:#1E2329;border-radius:10px;
                padding:16px;text-align:center;min-width:120px;'>
      <div style='font-size:2rem;font-weight:700;color:#F44336;'>
        {len(fading)}
      </div>
      <div style='color:#888;font-size:0.82rem;'>Fading Connections</div>
    </div>
    <div style='flex:1;background:#1E2329;border-radius:10px;
                padding:16px;text-align:center;min-width:120px;'>
      <div style='font-size:2rem;font-weight:700;color:#2196F3;'>
        {len(wishes["by_platform"])}
      </div>
      <div style='color:#888;font-size:0.82rem;'>Active Platforms</div>
    </div>
  </div>

  <!-- PLATFORM BREAKDOWN -->
  <div style='background:#1E2329;border-radius:8px;padding:14px;margin-bottom:8px;'>
    <span style='color:#888;font-size:0.82rem;margin-right:8px;'>Platforms:</span>
    {platform_items}
  </div>

  <!-- UPCOMING BIRTHDAYS -->
  {upcoming_section}

  <!-- FADING CONNECTIONS -->
  {fading_section}

  <!-- TOP CONTACTS + A/B -->
  <div style='display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:8px;'>
    <div>{top_section}</div>
    <div>{ab_section}</div>
  </div>

  <!-- FOOTER -->
  <p style='color:#333;font-size:0.78rem;text-align:center;margin-top:28px;'>
    🎂 Birthday Wishes Agent v5.0 — Weekly Digest<br>
    Generated {datetime.now().strftime("%B %d, %Y at %H:%M")}
  </p>

</body>
</html>"""

    return subject, html


# ──────────────────────────────────────────────
# SEND EMAIL
# ──────────────────────────────────────────────
def send_digest_email(subject: str, html: str) -> bool:
    """Send the weekly digest email."""
    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        logger.warning("⚠️  Email not configured. Skipping digest.")
        return False

    recipients = [r.strip() for r in DIGEST_RECIPIENTS.split(",") if r.strip()]
    if not recipients:
        recipients = [EMAIL_SENDER]

    try:
        msg            = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = EMAIL_SENDER
        msg["To"]      = ", ".join(recipients)
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, recipients, msg.as_string())

        logger.info("📧 Weekly digest sent to %s.", ", ".join(recipients))
        return True
    except Exception as e:
        logger.error("❌ Digest email failed: %s", e)
        return False


# ──────────────────────────────────────────────
# MAIN RUNNER
# ──────────────────────────────────────────────
async def send_weekly_digest(dry_run: bool = True) -> dict:
    """
    Collect all data and send the weekly digest email.

    Args:
        dry_run : If True, collect data but don't send email

    Returns:
        Dict with all collected data.
    """
    logger.info("=== Weekly Email Digest === [DRY RUN: %s]", dry_run)

    data = {
        "wishes":             get_weekly_wishes(),
        "upcoming_birthdays": get_upcoming_birthdays(7),
        "fading_connections": get_fading_connections(5),
        "top_contacts":       get_top_contacts(5),
        "ab_summary":         get_ab_summary(),
    }

    logger.info(
        "📊 Digest data: %d actions | %d upcoming | %d fading",
        data["wishes"]["total"],
        len(data["upcoming_birthdays"]),
        len(data["fading_connections"]),
    )

    subject, html = build_digest_email(data)

    if dry_run:
        logger.info("[DRY RUN] Would send digest: %s", subject)
    else:
        send_digest_email(subject, html)

    return data