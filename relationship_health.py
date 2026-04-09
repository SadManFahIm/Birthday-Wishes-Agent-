"""
relationship_health.py
──────────────────────
Relationship Health Score module for Birthday Wishes Agent.

Analyzes the health of each LinkedIn relationship on a weekly basis
and generates a detailed report with actionable recommendations.

Health Score is based on:
  - Interaction frequency (wishes, replies, comments, likes)
  - Recency of last interaction
  - Response rate (do they reply to your wishes?)
  - Relationship depth (DMs vs likes)
  - Connection strength trend (growing/stable/fading)

Health Levels:
  🟢 Healthy     (75-100) : Regular, meaningful interactions
  🟡 Neutral     (50-74)  : Occasional interactions, room to improve
  🟠 At Risk     (25-49)  : Infrequent contact, relationship fading
  🔴 Critical    (0-24)   : No recent interaction, needs attention

Usage:
    from relationship_health import (
        calculate_health_score,
        generate_weekly_report,
        send_health_report_email
    )
"""

import json
import logging
import smtplib
import sqlite3
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import dotenv_values

logger  = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")
_env    = dotenv_values(".env")

EMAIL_SENDER        = _env.get("EMAIL_SENDER", "")
EMAIL_PASSWORD      = _env.get("EMAIL_PASSWORD", "")
REPORT_RECIPIENTS   = _env.get("REPORT_RECIPIENTS", _env.get("EMAIL_SENDER", ""))


# ──────────────────────────────────────────────
# DB SETUP
# ──────────────────────────────────────────────
def init_health_table():
    """Create the relationship health tracking table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS relationship_health (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                contact      TEXT    NOT NULL,
                week         TEXT    NOT NULL,
                health_score INTEGER NOT NULL,
                health_level TEXT    NOT NULL,
                details      TEXT,
                created_at   TEXT    NOT NULL,
                UNIQUE(contact, week)
            )
        """)
        conn.commit()
    logger.info("🗄️  Relationship health table ready.")


def save_health_score(
    contact: str,
    health_score: int,
    health_level: str,
    details: dict,
):
    """Save a health score calculation to the database."""
    week = date.today().strftime("%Y-W%V")
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO relationship_health
                (contact, week, health_score, health_level, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(contact, week) DO UPDATE SET
                health_score = excluded.health_score,
                health_level = excluded.health_level,
                details      = excluded.details
        """, (
            contact, week, health_score, health_level,
            json.dumps(details), datetime.now().isoformat(),
        ))
        conn.commit()


def get_health_history(contact: str, weeks: int = 8) -> list[dict]:
    """Get health score history for a contact."""
    if not DB_FILE.exists():
        return []
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(
            "SELECT week, health_score, health_level, created_at "
            "FROM relationship_health "
            "WHERE LOWER(contact) = LOWER(?) "
            "ORDER BY week DESC LIMIT ?",
            (contact, weeks),
        ).fetchall()
    return [
        {"week": r[0], "score": r[1], "level": r[2], "date": r[3]}
        for r in rows
    ]


# ──────────────────────────────────────────────
# HEALTH SCORE CALCULATOR
# ──────────────────────────────────────────────
def calculate_health_score(contact: str) -> dict:
    """
    Calculate relationship health score for a contact.

    Args:
        contact : Contact's name

    Returns:
        Dict with health_score, health_level, details, recommendations
    """
    if not DB_FILE.exists():
        return _empty_health(contact)

    today     = date.today()
    week_ago  = (today - timedelta(days=7)).isoformat()
    month_ago = (today - timedelta(days=30)).isoformat()
    year_ago  = (today - timedelta(days=365)).isoformat()

    with sqlite3.connect(DB_FILE) as conn:
        # Total interactions in last year
        total_interactions = conn.execute(
            "SELECT COUNT(*) FROM history "
            "WHERE LOWER(contact) = LOWER(?) AND date >= ? AND dry_run = 0",
            (contact, year_ago),
        ).fetchone()[0]

        # Interactions in last 30 days
        recent_interactions = conn.execute(
            "SELECT COUNT(*) FROM history "
            "WHERE LOWER(contact) = LOWER(?) AND date >= ? AND dry_run = 0",
            (contact, month_ago),
        ).fetchone()[0]

        # Last interaction date
        last_row = conn.execute(
            "SELECT date FROM history "
            "WHERE LOWER(contact) = LOWER(?) AND dry_run = 0 "
            "ORDER BY date DESC LIMIT 1",
            (contact,),
        ).fetchone()
        last_interaction = last_row[0] if last_row else None

        # Check follow-ups sent and responded
        try:
            followups_sent = conn.execute(
                "SELECT COUNT(*) FROM followups "
                "WHERE LOWER(contact) = LOWER(?) AND followup_sent = 1",
                (contact,),
            ).fetchone()[0]
        except Exception:
            followups_sent = 0

        # Check connection strength
        try:
            strength_count = conn.execute(
                "SELECT COUNT(*) FROM connection_interactions "
                "WHERE LOWER(contact) = LOWER(?)",
                (contact,),
            ).fetchone()[0]
        except Exception:
            strength_count = 0

    # ── SCORING ──────────────────────────────
    score = 0
    details = {}

    # 1. Interaction frequency (max 30 pts)
    if total_interactions >= 10:
        freq_score = 30
    elif total_interactions >= 5:
        freq_score = 20
    elif total_interactions >= 2:
        freq_score = 10
    elif total_interactions >= 1:
        freq_score = 5
    else:
        freq_score = 0
    score += freq_score
    details["interaction_frequency"] = {
        "score": freq_score, "total": total_interactions
    }

    # 2. Recency (max 30 pts)
    if last_interaction:
        try:
            days_since = (today - date.fromisoformat(last_interaction)).days
        except Exception:
            days_since = 999

        if days_since <= 7:
            recency_score = 30
        elif days_since <= 30:
            recency_score = 20
        elif days_since <= 90:
            recency_score = 10
        elif days_since <= 180:
            recency_score = 5
        else:
            recency_score = 0
    else:
        days_since    = 999
        recency_score = 0

    score += recency_score
    details["recency"] = {
        "score": recency_score, "days_since": days_since,
        "last_interaction": last_interaction,
    }

    # 3. Recent activity (max 20 pts)
    if recent_interactions >= 3:
        activity_score = 20
    elif recent_interactions >= 2:
        activity_score = 15
    elif recent_interactions >= 1:
        activity_score = 8
    else:
        activity_score = 0
    score += activity_score
    details["recent_activity"] = {
        "score": activity_score, "count_30d": recent_interactions
    }

    # 4. Follow-up engagement (max 10 pts)
    fu_score = min(10, followups_sent * 5)
    score   += fu_score
    details["followup_engagement"] = {
        "score": fu_score, "followups_sent": followups_sent
    }

    # 5. Connection depth (max 10 pts)
    depth_score = min(10, strength_count * 2)
    score      += depth_score
    details["connection_depth"] = {
        "score": depth_score, "interaction_types": strength_count
    }

    # Determine health level
    health_level = _get_health_level(score)

    # Generate recommendations
    recommendations = _get_recommendations(score, details, contact)

    result = {
        "contact":         contact,
        "health_score":    score,
        "health_level":    health_level,
        "details":         details,
        "recommendations": recommendations,
    }

    save_health_score(contact, score, health_level["name"], details)
    logger.info(
        "💚 Health score for %s: %d/100 (%s)",
        contact, score, health_level["name"],
    )
    return result


def _empty_health(contact: str) -> dict:
    return {
        "contact":         contact,
        "health_score":    0,
        "health_level":    _get_health_level(0),
        "details":         {},
        "recommendations": ["Start by sending a birthday wish or connection request."],
    }


def _get_health_level(score: int) -> dict:
    if score >= 75:
        return {"name": "Healthy",  "emoji": "🟢", "color": "#4CAF50"}
    elif score >= 50:
        return {"name": "Neutral",  "emoji": "🟡", "color": "#FFC107"}
    elif score >= 25:
        return {"name": "At Risk",  "emoji": "🟠", "color": "#FF9800"}
    else:
        return {"name": "Critical", "emoji": "🔴", "color": "#F44336"}


def _get_recommendations(score: int, details: dict, contact: str) -> list[str]:
    """Generate actionable recommendations based on health score."""
    recs = []

    days_since = details.get("recency", {}).get("days_since", 999)
    recent     = details.get("recent_activity", {}).get("count_30d", 0)
    followups  = details.get("followup_engagement", {}).get("followups_sent", 0)

    if days_since > 180:
        recs.append(f"⚠️  No contact with {contact} in {days_since} days — send a check-in message.")
    elif days_since > 90:
        recs.append(f"💬 It's been a while — consider liking or commenting on {contact}'s latest post.")

    if recent == 0:
        recs.append(f"📅 Schedule a touchpoint with {contact} this month.")

    if followups == 0:
        recs.append(f"🔔 Try sending a follow-up after your next birthday wish to {contact}.")

    if score >= 75:
        recs.append(f"✅ Great relationship with {contact} — keep it up!")
    elif score >= 50:
        recs.append(f"📈 Relationship with {contact} is stable — a little more engagement will strengthen it.")
    elif score < 25:
        recs.append(f"🚨 Relationship with {contact} is critical — reach out soon before it fades completely.")

    return recs


# ──────────────────────────────────────────────
# WEEKLY REPORT GENERATOR
# ──────────────────────────────────────────────
def generate_weekly_report() -> dict:
    """
    Generate a full weekly relationship health report
    for all contacts in the database.

    Returns:
        Dict with summary, contacts breakdown, and recommendations.
    """
    if not DB_FILE.exists():
        return {"error": "No database found. Run the agent first."}

    # Get all contacts
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(
            "SELECT DISTINCT contact FROM history WHERE dry_run = 0 ORDER BY contact"
        ).fetchall()
    contacts = [r[0] for r in rows]

    if not contacts:
        return {"error": "No contacts found in history."}

    logger.info("📊 Generating weekly health report for %d contacts...", len(contacts))

    results     = [calculate_health_score(c) for c in contacts]
    healthy     = [r for r in results if r["health_score"] >= 75]
    neutral     = [r for r in results if 50 <= r["health_score"] < 75]
    at_risk     = [r for r in results if 25 <= r["health_score"] < 50]
    critical    = [r for r in results if r["health_score"] < 25]

    avg_score   = sum(r["health_score"] for r in results) / len(results) if results else 0

    week_label  = date.today().strftime("Week of %B %d, %Y")

    report = {
        "week":           week_label,
        "total_contacts": len(contacts),
        "average_score":  round(avg_score, 1),
        "summary": {
            "healthy":  len(healthy),
            "neutral":  len(neutral),
            "at_risk":  len(at_risk),
            "critical": len(critical),
        },
        "healthy":  sorted(healthy,  key=lambda x: x["health_score"], reverse=True),
        "neutral":  sorted(neutral,  key=lambda x: x["health_score"], reverse=True),
        "at_risk":  sorted(at_risk,  key=lambda x: x["health_score"], reverse=True),
        "critical": sorted(critical, key=lambda x: x["health_score"], reverse=True),
        "top_recommendations": _get_top_recommendations(at_risk + critical),
    }

    logger.info(
        "📊 Report ready — Healthy: %d | Neutral: %d | At Risk: %d | Critical: %d",
        len(healthy), len(neutral), len(at_risk), len(critical),
    )
    return report


def _get_top_recommendations(contacts_needing_attention: list[dict]) -> list[str]:
    """Extract top 5 most important recommendations."""
    recs = []
    for c in contacts_needing_attention[:5]:
        recs.extend(c.get("recommendations", [])[:1])
    return recs[:5]


# ──────────────────────────────────────────────
# EMAIL REPORT BUILDER
# ──────────────────────────────────────────────
def build_report_email(report: dict) -> tuple[str, str]:
    """Build the weekly report email HTML."""
    if "error" in report:
        return "⚠️ Weekly Report Error", f"<p>{report['error']}</p>"

    week         = report["week"]
    total        = report["total_contacts"]
    avg          = report["average_score"]
    summary      = report["summary"]

    # Color for average score
    if avg >= 75:
        avg_color = "#4CAF50"
    elif avg >= 50:
        avg_color = "#FFC107"
    else:
        avg_color = "#F44336"

    subject = f"📊 Weekly Relationship Health Report — {week}"

    # Build contact rows for each level
    def build_rows(contacts, color):
        if not contacts:
            return "<tr><td colspan='3' style='color:#888;padding:8px;'>None</td></tr>"
        rows = ""
        for c in contacts[:8]:
            recs = c.get("recommendations", [""])
            rows += f"""
            <tr>
              <td style='padding:8px;color:#FAFAFA;'>{c['contact']}</td>
              <td style='padding:8px;text-align:center;'>
                <strong style='color:{color};'>{c['health_score']}/100</strong>
              </td>
              <td style='padding:8px;color:#aaa;font-size:0.85rem;'>
                {recs[0] if recs else ''}
              </td>
            </tr>"""
        return rows

    top_recs_html = "".join(
        f"<li style='margin:6px 0;color:#555;'>{r}</li>"
        for r in report.get("top_recommendations", [])
    )

    html = f"""
<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;max-width:700px;margin:auto;
             background:#0E1117;color:#FAFAFA;padding:20px;">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#1a237e,#4CAF50);
              padding:30px;border-radius:12px;text-align:center;">
    <h1 style="margin:0;font-size:1.8rem;">📊 Weekly Relationship Health Report</h1>
    <p style="margin:8px 0 0;opacity:0.85;">{week}</p>
  </div>

  <!-- Summary Cards -->
  <div style="display:flex;gap:12px;margin:20px 0;flex-wrap:wrap;">
    <div style="flex:1;background:#1E2329;border-radius:12px;
                padding:16px;text-align:center;min-width:120px;">
      <div style="font-size:1.8rem;font-weight:700;color:{avg_color};">{avg}</div>
      <div style="color:#888;font-size:0.85rem;">Avg Score</div>
    </div>
    <div style="flex:1;background:#1E2329;border-radius:12px;
                padding:16px;text-align:center;min-width:120px;">
      <div style="font-size:1.8rem;font-weight:700;color:#4CAF50;">
        {summary['healthy']}
      </div>
      <div style="color:#888;font-size:0.85rem;">🟢 Healthy</div>
    </div>
    <div style="flex:1;background:#1E2329;border-radius:12px;
                padding:16px;text-align:center;min-width:120px;">
      <div style="font-size:1.8rem;font-weight:700;color:#FFC107;">
        {summary['neutral']}
      </div>
      <div style="color:#888;font-size:0.85rem;">🟡 Neutral</div>
    </div>
    <div style="flex:1;background:#1E2329;border-radius:12px;
                padding:16px;text-align:center;min-width:120px;">
      <div style="font-size:1.8rem;font-weight:700;color:#FF9800;">
        {summary['at_risk']}
      </div>
      <div style="color:#888;font-size:0.85rem;">🟠 At Risk</div>
    </div>
    <div style="flex:1;background:#1E2329;border-radius:12px;
                padding:16px;text-align:center;min-width:120px;">
      <div style="font-size:1.8rem;font-weight:700;color:#F44336;">
        {summary['critical']}
      </div>
      <div style="color:#888;font-size:0.85rem;">🔴 Critical</div>
    </div>
  </div>

  <!-- Top Recommendations -->
  {"" if not top_recs_html else f'''
  <div style="background:#1a2a1a;border-left:4px solid #4CAF50;
              padding:16px;border-radius:8px;margin:16px 0;">
    <h3 style="margin:0 0 10px;color:#4CAF50;">🎯 Top Action Items This Week</h3>
    <ul style="margin:0;padding-left:20px;">{top_recs_html}</ul>
  </div>
  '''}

  <!-- At Risk Contacts -->
  {f"""
  <h3 style="color:#FF9800;margin-top:24px;">🟠 At Risk ({summary['at_risk']})</h3>
  <table style="width:100%;border-collapse:collapse;background:#1E2329;border-radius:8px;">
    <tr style="background:#2E3440;">
      <th style="padding:10px;text-align:left;color:#aaa;">Contact</th>
      <th style="padding:10px;color:#aaa;">Score</th>
      <th style="padding:10px;text-align:left;color:#aaa;">Recommendation</th>
    </tr>
    {build_rows(report['at_risk'], '#FF9800')}
  </table>
  """ if summary['at_risk'] > 0 else ""}

  <!-- Critical Contacts -->
  {f"""
  <h3 style="color:#F44336;margin-top:24px;">🔴 Critical ({summary['critical']})</h3>
  <table style="width:100%;border-collapse:collapse;background:#1E2329;border-radius:8px;">
    <tr style="background:#2E3440;">
      <th style="padding:10px;text-align:left;color:#aaa;">Contact</th>
      <th style="padding:10px;color:#aaa;">Score</th>
      <th style="padding:10px;text-align:left;color:#aaa;">Recommendation</th>
    </tr>
    {build_rows(report['critical'], '#F44336')}
  </table>
  """ if summary['critical'] > 0 else ""}

  <!-- Healthy Contacts -->
  {f"""
  <h3 style="color:#4CAF50;margin-top:24px;">🟢 Healthy ({summary['healthy']})</h3>
  <table style="width:100%;border-collapse:collapse;background:#1E2329;border-radius:8px;">
    <tr style="background:#2E3440;">
      <th style="padding:10px;text-align:left;color:#aaa;">Contact</th>
      <th style="padding:10px;color:#aaa;">Score</th>
      <th style="padding:10px;text-align:left;color:#aaa;">Note</th>
    </tr>
    {build_rows(report['healthy'], '#4CAF50')}
  </table>
  """ if summary['healthy'] > 0 else ""}

  <!-- Footer -->
  <p style="color:#555;font-size:0.8rem;text-align:center;margin-top:24px;">
    🎂 Birthday Wishes Agent v5.0 — Relationship Health Report<br>
    {total} contacts analyzed | Generated {datetime.now().strftime('%B %d, %Y at %H:%M')}
  </p>

</body>
</html>
"""
    return subject, html


# ──────────────────────────────────────────────
# SEND REPORT EMAIL
# ──────────────────────────────────────────────
def send_health_report_email(report: dict) -> bool:
    """Send the weekly health report via email."""
    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        logger.warning("⚠️  Email not configured. Skipping health report.")
        return False

    recipients = [r.strip() for r in REPORT_RECIPIENTS.split(",") if r.strip()]
    if not recipients:
        recipients = [EMAIL_SENDER]

    subject, html_body = build_report_email(report)

    try:
        msg            = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = EMAIL_SENDER
        msg["To"]      = ", ".join(recipients)
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, recipients, msg.as_string())

        logger.info("📧 Health report sent to %s.", ", ".join(recipients))
        return True

    except Exception as e:
        logger.error("❌ Health report email failed: %s", e)
        return False


# ──────────────────────────────────────────────
# MAIN RUNNER
# ──────────────────────────────────────────────
async def run_relationship_health_report(dry_run: bool = True) -> dict:
    """
    Generate and send the weekly relationship health report.

    Args:
        dry_run : If True, generate report but don't send email

    Returns:
        The full report dict.
    """
    logger.info("=== Weekly Relationship Health Report === [DRY RUN: %s]", dry_run)

    report = generate_weekly_report()

    if "error" in report:
        logger.error("❌ Report generation failed: %s", report["error"])
        return report

    logger.info(
        "📊 Report generated — %d contacts | Avg score: %.1f",
        report["total_contacts"], report["average_score"],
    )

    if dry_run:
        logger.info("[DRY RUN] Would send health report email.")
    else:
        send_health_report_email(report)

    return report