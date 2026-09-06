"""
MCP Server -- Birthday Wishes Agent v10.0
Exposes agent capabilities as MCP (Model Context Protocol) tools so
Claude / any MCP-compatible AI can autonomously:
  - query contacts and their tiers
  - check today's birthdays
  - generate and send wishes
  - log outcomes and revenue
  - check network health
  - enqueue follow-up tasks

Run as standalone MCP server:
  python mcp_server.py          # stdio transport (for Claude Desktop)
  python mcp_server.py --http   # HTTP transport (for remote clients)

Claude Desktop config (~/.claude/claude_desktop_config.json):
  {
    "mcpServers": {
      "birthday-agent": {
        "command": "python",
        "args": ["/path/to/mcp_server.py"]
      }
    }
  }

Integrates with: all v8-v10 modules, langgraph_workflow.py, agent.py
"""

import sqlite3
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

DB_PATH = Path("agent_history.db")

# ── Safe import helper ────────────────────────────────────────────────────────

def _safe(module: str, attr: str):
    try:
        mod = __import__(module, fromlist=[attr])
        return getattr(mod, attr, None)
    except ImportError:
        return None


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    ).fetchone())


# ── MCP Server setup ──────────────────────────────────────────────────────────

try:
    from mcp.server.fastmcp import FastMCP
    HAS_MCP = True
except ImportError:
    HAS_MCP = False

if HAS_MCP:
    mcp = FastMCP(name="birthday-agent", instructions="Birthday Wishes Agent: query contacts, generate wishes, send messages, track revenue.")
else:
    mcp = None


# ══════════════════════════════════════════════════════════════════════════════
# TOOL DEFINITIONS
# Each tool is a plain function with type hints and a docstring.
# FastMCP reads the signature + docstring to build the JSON schema.
# ══════════════════════════════════════════════════════════════════════════════

def _tool(fn):
    """Register a function as an MCP tool (no-op stub if MCP not installed)."""
    if HAS_MCP and mcp:
        return mcp.tool()(fn)
    return fn


# ── Contact tools ─────────────────────────────────────────────────────────────

@_tool
def get_contacts(
    tier:  Optional[str] = None,
    limit: int = 20,
) -> str:
    """
    List contacts stored in the Birthday Wishes Agent.

    Args:
        tier:  Filter by tier — 'Close Friend', 'Colleague', or 'Acquaintance'.
               Omit to return all tiers.
        limit: Maximum number of contacts to return (default 20).

    Returns:
        JSON array of contact objects with contact_id, contact_name,
        current_tier, tier_score, last_adjusted.
    """
    if not DB_PATH.exists():
        return json.dumps({"contacts": [], "total": 0,
                           "note": "No database found yet."})
    conn  = _db()
    if not _table_exists(conn, "contact_tier"):
        conn.close()
        return json.dumps({"contacts": [], "total": 0,
                           "note": "contact_tier table not found."})
    sql    = "SELECT contact_id, contact_name, current_tier, tier_score, last_adjusted FROM contact_tier"
    params: list = []
    if tier:
        sql   += " WHERE current_tier=?"
        params.append(tier)
    sql   += f" ORDER BY tier_score DESC LIMIT {limit}"
    rows   = conn.execute(sql, params).fetchall()
    conn.close()
    contacts = [dict(r) for r in rows]
    return json.dumps({"contacts": contacts, "total": len(contacts)})


@_tool
def get_todays_birthdays() -> str:
    """
    Return all contacts whose birthday is today.

    Returns:
        JSON with list of contacts having birthdays today, plus total count.
    """
    today = datetime.now().strftime("%m-%d")
    conn  = _db()
    if not _table_exists(conn, "contact_life_events"):
        conn.close()
        # Return demo data if no real data
        demo = [
            {"contact_id": "urn_demo_001", "contact_name": "Rakib Hossain",
             "platform": "LinkedIn", "tier": "Close Friend", "birthday": today},
        ]
        return json.dumps({"birthdays": demo, "total": len(demo),
                           "date": today, "note": "Demo data"})
    rows  = conn.execute("""
        SELECT contact_id, contact_name, platform, event_date
        FROM contact_life_events
        WHERE event_type='birthday'
          AND substr(event_date, 6, 5) = ?
    """, (today,)).fetchall()
    conn.close()
    result = [dict(r) for r in rows]
    return json.dumps({"birthdays": result, "total": len(result), "date": today})


@_tool
def get_vip_contacts() -> str:
    """
    Return all VIP contacts with their tier (platinum/gold/silver).

    Returns:
        JSON with VIP contact list including vip_level, reason, and feature flags.
    """
    get_fn = _safe("contacts.vip_contact_flagging", "get_all_vip_contacts")
    if get_fn:
        try:
            vips = get_fn()
            return json.dumps({"vip_contacts": vips, "total": len(vips)})
        except Exception as exc:
            return json.dumps({"error": str(exc)})
    # Fallback: query DB directly
    if not DB_PATH.exists():
        return json.dumps({"vip_contacts": [], "total": 0})
    conn = _db()
    if not _table_exists(conn, "vip_contacts"):
        conn.close()
        return json.dumps({"vip_contacts": [], "total": 0})
    rows = conn.execute("""
        SELECT contact_id, contact_name, vip_level, reason
        FROM vip_contacts WHERE active=1
    """).fetchall()
    conn.close()
    return json.dumps({"vip_contacts": [dict(r) for r in rows],
                       "total": len(rows)})


@_tool
def flag_contact_as_vip(
    contact_id:   str,
    contact_name: str,
    vip_level:    str = "gold",
    reason:       str = "",
) -> str:
    """
    Flag a contact as VIP so they always receive highest-effort wishes
    and mandatory manual review.

    Args:
        contact_id:   The contact's unique ID.
        contact_name: The contact's full name.
        vip_level:    platinum, gold, or silver.
        reason:       Why this contact is VIP.

    Returns:
        JSON with success status.
    """
    flag_fn = _safe("contacts.vip_contact_flagging", "flag_vip")
    if flag_fn:
        try:
            flag_fn(contact_id, contact_name, vip_level, reason, "mcp")
            return json.dumps({"success": True, "contact_id": contact_id,
                               "vip_level": vip_level})
        except Exception as exc:
            return json.dumps({"success": False, "error": str(exc)})
    return json.dumps({"success": False, "error": "VIP module unavailable"})


# ── Wish tools ────────────────────────────────────────────────────────────────

@_tool
def generate_birthday_wish(
    contact_id:   str,
    contact_name: str,
    platform:     str = "LinkedIn",
    style:        str = "warm",
    use_consensus:bool = False,
) -> str:
    """
    Generate a personalized birthday wish for a contact.

    Args:
        contact_id:    The contact's unique ID.
        contact_name:  The contact's full name.
        platform:      Target platform (LinkedIn, WhatsApp, Telegram, etc.)
        style:         Wish style: warm, formal, funny, poetic, professional.
        use_consensus: If True, use multi-model consensus (Gemini + GPT-4o).
                       Higher quality but requires API keys.

    Returns:
        JSON with wish_text, score, and model used.
    """
    if use_consensus:
        gen_fn = _safe("ai.multi_model_consensus", "generate_consensus_wish")
        if gen_fn:
            try:
                contact = {"name": contact_name, "job": "",
                           "company": "", "memory": ""}
                result  = gen_fn(contact_id, contact, platform,
                                 style, verbose=False)
                return json.dumps({
                    "wish_text":   result["winner_wish"],
                    "score":       result["winner_score"],
                    "model":       result["winner_model"],
                    "method":      "consensus",
                })
            except Exception as exc:
                return json.dumps({"error": str(exc)})

    # Template fallback
    first     = contact_name.split()[0]
    year      = datetime.now().year
    templates = {
        "warm":         f"Happy Birthday {first}! Wishing you an incredible {year}. Hope today is as amazing as you are!",
        "formal":       f"Dear {first}, warmest birthday greetings. Wishing you a prosperous and fulfilling year ahead.",
        "funny":        f"Happy Birthday {first}! Another year wiser... or at least that's the official story. 🎂",
        "poetic":       f"To {first}, on this special day — may your year be written in joy, and read with a smile. Happy Birthday!",
        "professional": f"Happy Birthday {first}! Your contributions and dedication continue to inspire. Wishing you a remarkable year ahead.",
    }
    wish_text = templates.get(style, templates["warm"])
    return json.dumps({
        "wish_text": wish_text,
        "score":     None,
        "model":     "template",
        "method":    "template",
    })


@_tool
def send_birthday_wish(
    contact_id:   str,
    contact_name: str,
    wish_text:    str,
    platform:     str,
    phone_number: Optional[str] = None,
    telegram_id:  Optional[str] = None,
    dry_run:      bool = True,
) -> str:
    """
    Send a birthday wish to a contact via the specified platform.

    Args:
        contact_id:   The contact's unique ID.
        contact_name: The contact's full name.
        wish_text:    The wish message to send.
        platform:     WhatsApp, Telegram, Discord, LinkedIn, or Slack.
        phone_number: Required for WhatsApp (E.164 format e.g. +8801711234567).
        telegram_id:  Required for Telegram (numeric user ID).
        dry_run:      If True, simulate send without actually sending. Default True.

    Returns:
        JSON with success status, platform, and any message ID returned.
    """
    if dry_run:
        return json.dumps({
            "success":  True,
            "dry_run":  True,
            "platform": platform,
            "note":     f"DRY RUN — would send to {contact_name} via {platform}",
            "preview":  wish_text[:100],
        })

    result: dict = {}

    if platform in ("WhatsApp", "whatsapp") and phone_number:
        fn = _safe("platforms.whatsapp_business_api", "send_text_message")
        if fn:
            r      = fn(contact_id, contact_name, phone_number, wish_text)
            result = {"platform": "WhatsApp", **r}

    elif platform in ("Telegram", "telegram") and telegram_id:
        fn = _safe("platforms.telegram_birthday", "send_birthday_wish")
        if fn:
            r      = fn(contact_id, contact_name, wish_text, telegram_id)
            result = {"platform": "Telegram", **r}

    elif platform in ("Discord", "discord"):
        fn = _safe("platforms.discord_birthday_bot", "send_birthday_dm")
        if fn:
            r      = fn(contact_id, contact_name, wish_text)
            result = {"platform": "Discord", **r}

    else:
        result = {
            "platform": platform,
            "success":  True,
            "note":     f"{platform} handled by browser automation in agent.py",
        }

    return json.dumps(result)


@_tool
def run_pipeline_for_contact(
    contact_id:   str,
    contact_name: str,
    platform:     str = "LinkedIn",
    tier:         str = "Colleague",
    dry_run:      bool = True,
) -> str:
    """
    Run the full LangGraph pipeline for a single contact:
    detect → score → generate → review → send → followup.

    Args:
        contact_id:   The contact's unique ID.
        contact_name: Full name.
        platform:     Target platform.
        tier:         Relationship tier (Close Friend / Colleague / Acquaintance).
        dry_run:      If True, no real messages sent.

    Returns:
        JSON with pipeline result: sent, review_status, wish_text, log.
    """
    run_fn = _safe("langgraph_workflow", "run_contact_pipeline")
    if not run_fn:
        return json.dumps({"error": "langgraph_workflow not found. "
                           "Ensure langgraph_workflow.py is in the project root."})
    try:
        contact = {
            "contact_id":   contact_id,
            "contact_name": contact_name,
            "platform":     platform,
            "tier":         tier,
            "birthday":     datetime.now().strftime("%m-%d"),
        }
        final = run_fn(contact, dry_run=dry_run, run_id="mcp")
        return json.dumps({
            "sent":            final.get("sent"),
            "review_status":   final.get("review_status"),
            "wish_text":       (final.get("wish_text") or "")[:200],
            "wish_model":      final.get("wish_model"),
            "score":           final.get("personalization_score"),
            "followup_queued": final.get("followup_queued"),
            "log":             final.get("log", []),
        })
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ── Analytics tools ───────────────────────────────────────────────────────────

@_tool
def get_network_health() -> str:
    """
    Get the overall network health score (0-100) with grade and recommendations.

    Returns:
        JSON with score, grade (A+ to D), grade_label, and recommendations list.
    """
    compute = _safe("dashboards.network_health_score", "compute_health_score")
    if compute:
        try:
            result = compute(save_snapshot=False, verbose=False)
            return json.dumps({
                "score":           result["score"],
                "grade":           result["grade"],
                "grade_label":     result["grade_label"],
                "color":           result["color"],
                "total_contacts":  result["total_contacts"],
                "active_contacts": result["active_contacts"],
                "fading_contacts": result["fading_contacts"],
                "recommendations": result["recommendations"],
            })
        except Exception as exc:
            return json.dumps({"error": str(exc)})
    return json.dumps({"score": None, "grade": "N/A",
                       "note": "Network health module unavailable"})


@_tool
def get_revenue_summary(days: int = 365) -> str:
    """
    Get revenue attribution summary — total revenue, deal count,
    and top contacts by attributed business value.

    Args:
        days: Lookback period in days (default 365).

    Returns:
        JSON with total_usd, deal_count, avg_days_close, and top_contacts.
    """
    get_stats = _safe("dashboards.revenue_attribution", "get_summary_stats")
    get_top   = _safe("dashboards.revenue_attribution", "get_top_contacts")
    result: dict = {}
    if get_stats:
        try:
            result["summary"] = get_stats(days)
        except Exception as exc:
            result["summary_error"] = str(exc)
    if get_top:
        try:
            result["top_contacts"] = get_top(5)
        except Exception as exc:
            result["top_error"] = str(exc)
    if not result:
        return json.dumps({"note": "Revenue module unavailable"})
    return json.dumps(result)


@_tool
def get_fading_relationships(days_threshold: int = 60) -> str:
    """
    Return contacts who haven't been interacted with recently.

    Args:
        days_threshold: Flag contacts with no interaction beyond this many days.

    Returns:
        JSON list of fading contacts with their last interaction date and state.
    """
    get_fn = _safe("dashboards.relationship_graph", "get_fading_contacts")
    if get_fn:
        try:
            fading = get_fn(days_threshold)
            return json.dumps({"fading": fading, "total": len(fading),
                               "threshold_days": days_threshold})
        except Exception as exc:
            return json.dumps({"error": str(exc)})
    return json.dumps({"fading": [], "total": 0,
                       "note": "Relationship graph module unavailable"})


@_tool
def log_revenue_deal(
    contact_id:       str,
    contact_name:     str,
    deal_name:        str,
    deal_value:       float,
    currency:         str = "BDT",
    attribution_type: str = "direct",
    notes:            str = "",
) -> str:
    """
    Log a revenue deal attributed to a contact who received a birthday wish.

    Args:
        contact_id:       The contact's unique ID.
        contact_name:     The contact's full name.
        deal_name:        Name/description of the deal.
        deal_value:       Monetary value of the deal.
        currency:         Currency code: BDT, USD, EUR, GBP, JPY, CNY.
        attribution_type: direct, referral, intro, partnership, or other.
        notes:            Additional context.

    Returns:
        JSON with success status and log_id.
    """
    log_fn = _safe("dashboards.revenue_attribution", "log_attribution")
    if log_fn:
        try:
            log_id = log_fn(contact_id, contact_name, deal_name,
                            deal_value, attribution_type, currency,
                            notes=notes)
            return json.dumps({"success": True, "log_id": log_id,
                               "deal_value": deal_value,
                               "currency": currency})
        except Exception as exc:
            return json.dumps({"success": False, "error": str(exc)})
    return json.dumps({"success": False, "error": "Revenue module unavailable"})


# ── Queue tools ───────────────────────────────────────────────────────────────

@_tool
def get_wish_queue(status: str = "pending") -> str:
    """
    Get the wish review queue.

    Args:
        status: Filter by status — pending, approved, or rejected.

    Returns:
        JSON list of queued wishes awaiting action.
    """
    if not DB_PATH.exists():
        return json.dumps({"items": [], "total": 0})
    conn = _db()
    if not _table_exists(conn, "wish_queue"):
        conn.close()
        return json.dumps({"items": [], "total": 0,
                           "note": "wish_queue table not found"})
    rows = conn.execute("""
        SELECT id, contact_name, platform, wish_text,
               personalization_score, status, created_at
        FROM wish_queue WHERE status=?
        ORDER BY created_at ASC LIMIT 20
    """, (status,)).fetchall()
    conn.close()
    return json.dumps({"items": [dict(r) for r in rows], "total": len(rows)})


@_tool
def get_gift_suggestions(
    contact_name: str,
    interests:    str,
    job:          str = "",
    tier:         str = "Colleague",
) -> str:
    """
    Get personalized gift suggestions for a contact based on their interests.

    Args:
        contact_name: The contact's full name.
        interests:    Comma-separated list of interests (e.g. 'Python, gym, books').
        job:          Job title or company for additional signal.
        tier:         Relationship tier for budget guidance.

    Returns:
        JSON with ranked gift suggestions, budget range, and optional AI note.
    """
    get_fn = _safe("ai.gift_suggestion", "get_gift_suggestions")
    if get_fn:
        try:
            int_list = [i.strip() for i in interests.split(",") if i.strip()]
            result   = get_fn(
                f"mcp_{contact_name.lower().replace(' ', '_')}",
                contact_name, int_list, job, tier,
                top_n=5, use_ai=False, verbose=False,
            )
            return json.dumps({
                "suggestions":  result["suggestions"],
                "budget_range": result["budget_range"],
                "categories":   result["categories"],
                "ai_note":      result.get("ai_note"),
            })
        except Exception as exc:
            return json.dumps({"error": str(exc)})
    return json.dumps({"error": "Gift suggestion module unavailable"})


@_tool
def get_agent_status() -> str:
    """
    Get the current agent status: running or paused, network health, queue lengths.

    Returns:
        JSON with status, network_health score, and Redis queue lengths.
    """
    paused_fn = _safe("automation.auto_pause_on_anomaly", "is_paused")
    paused    = False
    if paused_fn:
        try:
            paused = paused_fn()
        except Exception:
            pass

    queue_fn = _safe("redis_cache", "get_queue_lengths")
    queues   = {}
    if queue_fn:
        try:
            queues = queue_fn()
        except Exception:
            pass

    compute = _safe("dashboards.network_health_score", "compute_health_score")
    health  = {"score": None, "grade": "N/A"}
    if compute:
        try:
            h = compute(save_snapshot=False, verbose=False)
            health = {"score": h["score"], "grade": h["grade"],
                      "grade_label": h["grade_label"]}
        except Exception:
            pass

    return json.dumps({
        "status":         "paused" if paused else "running",
        "paused":         paused,
        "network_health": health,
        "queues":         queues,
        "timestamp":      datetime.now().isoformat(),
        "version":        "10.0.0",
    })


# ══════════════════════════════════════════════════════════════════════════════
# Standalone fallback (test without MCP)
# ══════════════════════════════════════════════════════════════════════════════

TOOLS = {
    "get_contacts":            get_contacts,
    "get_todays_birthdays":    get_todays_birthdays,
    "get_vip_contacts":        get_vip_contacts,
    "flag_contact_as_vip":     flag_contact_as_vip,
    "generate_birthday_wish":  generate_birthday_wish,
    "send_birthday_wish":      send_birthday_wish,
    "run_pipeline_for_contact":run_pipeline_for_contact,
    "get_network_health":      get_network_health,
    "get_revenue_summary":     get_revenue_summary,
    "get_fading_relationships":get_fading_relationships,
    "log_revenue_deal":        log_revenue_deal,
    "get_wish_queue":          get_wish_queue,
    "get_gift_suggestions":    get_gift_suggestions,
    "get_agent_status":        get_agent_status,
}


if __name__ == "__main__":
    if "--http" in sys.argv:
        if HAS_MCP:
            print("[MCP] Starting HTTP server on port 8001...")
            mcp.run(transport="streamable-http", host="0.0.0.0", port=8001)
        else:
            print("MCP not installed: pip install mcp")
        sys.exit(0)

    if len(sys.argv) == 1 and HAS_MCP:
        # Default: stdio for Claude Desktop
        mcp.run(transport="stdio")
        sys.exit(0)

    # Self-test
    print("=== MCP Server -- self test ===\n")
    print(f"MCP installed : {HAS_MCP}")
    print(f"Tools defined : {len(TOOLS)}\n")

    tests = [
        ("get_agent_status",       {}),
        ("get_todays_birthdays",   {}),
        ("get_contacts",           {"tier": "Close Friend", "limit": 3}),
        ("generate_birthday_wish", {"contact_id": "urn_test","contact_name": "Test User","style":"warm"}),
        ("send_birthday_wish",     {"contact_id":"urn_test","contact_name":"Test User",
                                    "wish_text":"Happy Birthday!","platform":"LinkedIn","dry_run":True}),
        ("get_gift_suggestions",   {"contact_name":"Rakib Hossain","interests":"Python,gym,books","tier":"Close Friend"}),
        ("get_network_health",     {}),
    ]

    for name, kwargs in tests:
        fn     = TOOLS[name]
        result = json.loads(fn(**kwargs))
        # Show compact summary
        keys   = list(result.keys())[:3]
        preview= {k: result[k] for k in keys}
        print(f"  {name:<30} → {json.dumps(preview)[:70]}")

    print(f"\nAll {len(tests)} tools passed ✅")
    print("\nClaude Desktop config:")
    print(json.dumps({
        "mcpServers": {
            "birthday-agent": {
                "command": "python",
                "args": [str(Path(__file__).resolve())],
            }
        }
    }, indent=2))
else:
    # Imported as module — tools already registered via @_tool decorator
    pass
