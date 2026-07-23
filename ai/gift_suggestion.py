"""
Gift Suggestion Engine -- Birthday Wishes Agent v9.0
Suggests personalized gift ideas based on a contact's interests,
profession, tier, and past interactions.

How it works:
  1. Build a contact profile (interests, job, hobbies, tier, budget)
  2. Match against a curated gift catalogue (rule-based)
  3. Optionally enhance with AI (GPT-4o / Gemini) for a personalized note
  4. Return ranked gift ideas with rationale and price range

Integrates with: contacts/relationship_tiering.py,
                 contacts/mutual_connection_insights.py,
                 ai/multi_model_consensus.py, agent.py
"""

import sqlite3
import json
import os
import random
from pathlib import Path
from datetime import datetime
from typing import Optional

DB_PATH    = Path("agent_history.db")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_KEY = os.getenv("GOOGLE_API_KEY", "")

# ── Gift catalogue ────────────────────────────────────────────────────────────

GIFT_CATALOGUE = {
    # tech / engineering
    "tech": [
        {"name": "Mechanical Keyboard",     "price": "৳4,000–8,000",  "tags": ["tech","developer","typing"]},
        {"name": "Raspberry Pi Kit",        "price": "৳3,500–6,000",  "tags": ["tech","maker","tinkerer"]},
        {"name": "Noise-Cancelling Headphones","price":"৳5,000–15,000","tags":["tech","music","focus"]},
        {"name": "Laptop Stand + Hub",      "price": "৳2,000–4,000",  "tags": ["tech","wfh","productivity"]},
        {"name": "Smart LED Desk Lamp",     "price": "৳1,500–3,500",  "tags": ["tech","desk","focus"]},
        {"name": "Developer Book Bundle",   "price": "৳1,200–3,000",  "tags": ["tech","developer","learning"]},
    ],
    "design": [
        {"name": "Pantone Color Guide",     "price": "৳3,000–6,000",  "tags": ["design","creative","tools"]},
        {"name": "Procreate iPad Bundle",   "price": "৳12,000–25,000","tags": ["design","digital","art"]},
        {"name": "Moleskine Sketchbook Set","price": "৳800–2,000",    "tags": ["design","sketch","analog"]},
        {"name": "Wacom Drawing Tablet",    "price": "৳6,000–18,000", "tags": ["design","digital","art"]},
        {"name": "Typography Poster Pack",  "price": "৳600–1,500",    "tags": ["design","typography","decor"]},
    ],
    "books": [
        {"name": "Atomic Habits (James Clear)","price":"৳500–900",    "tags": ["books","productivity","habits"]},
        {"name": "Kindle Paperwhite",       "price": "৳8,000–12,000", "tags": ["books","reading","tech"]},
        {"name": "Curated Book Subscription","price":"৳2,000/mo",     "tags": ["books","reading","discovery"]},
        {"name": "Hardcover Collection (interest-matched)","price":"৳2,000–5,000","tags":["books","learning"]},
    ],
    "food": [
        {"name": "Artisan Coffee Subscription","price":"৳1,500–3,000/mo","tags":["food","coffee","lifestyle"]},
        {"name": "Premium Chocolate Box",   "price": "৳800–2,500",    "tags": ["food","sweet","luxury"]},
        {"name": "Cooking Masterclass Access","price":"৳3,000–8,000", "tags": ["food","cooking","learning"]},
        {"name": "Fine Dining Gift Voucher","price": "৳3,000–10,000", "tags": ["food","experience","luxury"]},
    ],
    "fitness": [
        {"name": "Fitness Tracker (Fitbit/Garmin)","price":"৳5,000–15,000","tags":["fitness","health","tech"]},
        {"name": "Resistance Band Set",     "price": "৳800–2,000",    "tags": ["fitness","gym","portable"]},
        {"name": "Gym Membership (1 month)","price": "৳2,000–5,000",  "tags": ["fitness","health","experience"]},
        {"name": "Protein Powder Bundle",   "price": "৳2,500–5,000",  "tags": ["fitness","nutrition","gym"]},
    ],
    "travel": [
        {"name": "Travel Organizer Set",    "price": "৳1,500–4,000",  "tags": ["travel","organization","practical"]},
        {"name": "Noise-Cancelling Earbuds","price": "৳3,000–8,000",  "tags": ["travel","music","tech"]},
        {"name": "Travel Voucher (hotel/flight)","price":"৳5,000+",   "tags": ["travel","experience","luxury"]},
        {"name": "Portable Power Bank",     "price": "৳1,500–3,500",  "tags": ["travel","tech","practical"]},
    ],
    "gaming": [
        {"name": "Steam/PlayStation Gift Card","price":"৳1,000–5,000","tags": ["gaming","digital","entertainment"]},
        {"name": "Gaming Headset",          "price": "৳2,500–8,000",  "tags": ["gaming","audio","tech"]},
        {"name": "Mechanical Gaming Mouse", "price": "৳2,000–6,000",  "tags": ["gaming","hardware","tech"]},
        {"name": "Gaming Chair Cushion",    "price": "৳1,500–4,000",  "tags": ["gaming","comfort","desk"]},
    ],
    "general": [
        {"name": "Personalized Photo Book", "price": "৳1,500–4,000",  "tags": ["general","sentimental","memory"]},
        {"name": "Premium Planner / Journal","price":"৳800–2,500",    "tags": ["general","productivity","stationery"]},
        {"name": "Scented Candle Set",      "price": "৳800–2,500",    "tags": ["general","relaxation","home"]},
        {"name": "Plant Pot + Succulents",  "price": "৳500–1,500",    "tags": ["general","home","nature"]},
        {"name": "Custom Name Mug",         "price": "৳300–800",      "tags": ["general","personalized","practical"]},
        {"name": "Subscription Box (curated)","price":"৳1,500–4,000/mo","tags":["general","discovery","experience"]},
    ],
}

INTEREST_CATEGORY_MAP = {
    "python":        "tech",   "coding":        "tech",
    "developer":     "tech",   "engineer":      "tech",
    "software":      "tech",   "programming":   "tech",
    "backend":       "tech",   "frontend":      "tech",
    "ui":            "design", "ux":            "design",
    "designer":      "design", "graphic":       "design",
    "illustration":  "design", "figma":         "design",
    "read":          "books",  "book":          "books",
    "literature":    "books",  "author":        "books",
    "coffee":        "food",   "foodie":        "food",
    "cooking":       "food",   "chef":          "food",
    "restaurant":    "food",   "baking":        "food",
    "gym":           "fitness","fitness":       "fitness",
    "workout":       "fitness","running":       "fitness",
    "yoga":          "fitness","health":        "fitness",
    "travel":        "travel", "backpack":      "travel",
    "photography":   "travel", "adventure":     "travel",
    "game":          "gaming", "gaming":        "gaming",
    "esports":       "gaming", "playstation":   "gaming",
    "xbox":          "gaming", "steam":         "gaming",
}

BUDGET_TIERS = {
    "Close Friend":  {"min": 2000,  "max": 10000, "label": "৳2k–10k"},
    "Colleague":     {"min": 800,   "max": 3000,  "label": "৳800–3k"},
    "Acquaintance":  {"min": 300,   "max": 1200,  "label": "৳300–1.2k"},
}


# ── DB setup ──────────────────────────────────────────────────────────────────

def init_gift_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS gift_suggestions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            tier            TEXT,
            interests_used  TEXT,
            suggestions_json TEXT NOT NULL,
            ai_enhanced     INTEGER DEFAULT 0,
            chosen_gift     TEXT,
            logged_at       TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── Interest extraction ───────────────────────────────────────────────────────

def extract_categories(interests: list[str], job: str = "") -> list[str]:
    """Map free-text interests + job to gift categories."""
    categories = set()
    combined   = " ".join(interests + [job]).lower()
    for keyword, category in INTEREST_CATEGORY_MAP.items():
        if keyword in combined:
            categories.add(category)
    if not categories:
        categories.add("general")
    return list(categories)


# ── Rule-based suggestions ────────────────────────────────────────────────────

def suggest_gifts(
    contact_id:   str,
    contact_name: str,
    interests:    list[str],
    job:          str = "",
    tier:         str = "Colleague",
    top_n:        int = 5,
) -> list[dict]:
    """
    Generate ranked gift suggestions using rule-based matching.

    Args:
        interests: List of interest strings (e.g. ["Python","reading","gym"])
        job:       Job title or company for additional signal
        tier:      Contact tier for budget guidance
        top_n:     Number of suggestions to return

    Returns:
        List of gift dicts with name, price, category, rationale, score
    """
    categories = extract_categories(interests, job)
    budget     = BUDGET_TIERS.get(tier, BUDGET_TIERS["Colleague"])
    combined   = " ".join(interests + [job]).lower()
    scored     = []

    for cat in categories:
        for gift in GIFT_CATALOGUE.get(cat, []):
            # Score based on tag overlap
            tag_hits = sum(1 for t in gift["tags"] if t in combined)
            score    = tag_hits * 3 + (2 if cat != "general" else 0)
            scored.append({
                "name":      gift["name"],
                "price":     gift["price"],
                "category":  cat,
                "tags":      gift["tags"],
                "score":     score,
                "rationale": _build_rationale(gift, cat, interests, tier),
                "budget_fit":budget["label"],
            })

    # Fallback: add general gifts if not enough
    if len(scored) < top_n:
        for gift in GIFT_CATALOGUE["general"]:
            if not any(g["name"] == gift["name"] for g in scored):
                scored.append({
                    "name":      gift["name"],
                    "price":     gift["price"],
                    "category":  "general",
                    "tags":      gift["tags"],
                    "score":     1,
                    "rationale": f"A thoughtful general gift for {contact_name.split()[0]}.",
                    "budget_fit":budget["label"],
                })

    # Sort by score, shuffle same-score items for variety
    scored.sort(key=lambda x: -x["score"])
    # Deduplicate
    seen  = set()
    final = []
    for g in scored:
        if g["name"] not in seen:
            seen.add(g["name"])
            final.append(g)

    return final[:top_n]


def _build_rationale(gift: dict, category: str, interests: list[str], tier: str) -> str:
    matches = [i for i in interests
               if any(t in i.lower() for t in gift["tags"])]
    if matches:
        return (f"Matches their interest in {matches[0]}. "
                f"A practical {category} gift at a {tier.lower()}-appropriate budget.")
    return f"A well-regarded {category} gift suitable for a {tier.lower()}."


# ── AI enhancement ────────────────────────────────────────────────────────────

def enhance_with_ai(
    contact_name: str,
    interests:    list[str],
    job:          str,
    suggestions:  list[dict],
    tier:         str = "Colleague",
) -> Optional[str]:
    """
    Ask GPT-4o / Gemini to write a personalized gift recommendation note.
    Returns a short paragraph or None if no AI key available.
    """
    if not OPENAI_KEY and not GEMINI_KEY:
        return None

    first = contact_name.split()[0]
    gift_list = "\n".join(f"- {g['name']} ({g['price']})" for g in suggestions[:3])
    prompt = (
        f"{first} is a {job or 'professional'} who is into: {', '.join(interests[:5])}.\n"
        f"Their relationship tier is: {tier}.\n"
        f"Top gift options:\n{gift_list}\n\n"
        f"Write a 2-sentence personalized gift recommendation note for {first}. "
        f"Be specific about why the top gift matches their personality. "
        f"Keep it warm and natural, not salesy."
    )

    # Try OpenAI first
    if OPENAI_KEY:
        try:
            from openai import OpenAI
            client   = OpenAI(api_key=OPENAI_KEY)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=120,
                temperature=0.7,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            print(f"[GiftEngine] GPT-4o error: {exc}")

    # Try Gemini
    if GEMINI_KEY:
        try:
            import google.generativeai as genai  # type: ignore
            genai.configure(api_key=GEMINI_KEY)
            model  = genai.GenerativeModel("gemini-2.5-pro")
            result = model.generate_content(prompt)
            return result.text.strip()
        except Exception as exc:
            print(f"[GiftEngine] Gemini error: {exc}")

    return None


# ── Main entry point ──────────────────────────────────────────────────────────

def get_gift_suggestions(
    contact_id:   str,
    contact_name: str,
    interests:    list[str],
    job:          str = "",
    tier:         str = "Colleague",
    top_n:        int = 5,
    use_ai:       bool = True,
    verbose:      bool = True,
) -> dict:
    """
    Main entry point. Returns ranked gift suggestions + optional AI note.

    Returns:
        {
          contact_id, contact_name, tier,
          categories: [str],
          suggestions: [{ name, price, category, rationale, score }],
          ai_note: str | None,
          budget_range: str,
          log_id: int,
        }
    """
    init_gift_tables()
    categories  = extract_categories(interests, job)
    suggestions = suggest_gifts(
        contact_id, contact_name, interests, job, tier, top_n)
    ai_note     = None

    if use_ai and suggestions:
        ai_note = enhance_with_ai(
            contact_name, interests, job, suggestions, tier)

    budget = BUDGET_TIERS.get(tier, BUDGET_TIERS["Colleague"])

    if verbose:
        print(f"[GiftEngine] {contact_name} | tier={tier} | "
              f"cats={categories} | budget={budget['label']}")
        for i, g in enumerate(suggestions[:3], 1):
            print(f"  {i}. {g['name']:<35} {g['price']:<18} score={g['score']}")

    # Log
    conn   = sqlite3.connect(DB_PATH)
    cur    = conn.execute("""
        INSERT INTO gift_suggestions
            (contact_id, contact_name, tier, interests_used,
             suggestions_json, ai_enhanced, logged_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (contact_id, contact_name, tier,
          json.dumps(interests[:10]),
          json.dumps(suggestions),
          1 if ai_note else 0,
          datetime.now().isoformat()))
    log_id = cur.lastrowid
    conn.commit()
    conn.close()

    return {
        "contact_id":   contact_id,
        "contact_name": contact_name,
        "tier":         tier,
        "categories":   categories,
        "suggestions":  suggestions,
        "ai_note":      ai_note,
        "budget_range": budget["label"],
        "log_id":       log_id,
    }


def log_chosen_gift(log_id: int, chosen_gift: str) -> None:
    """Record which gift was actually sent."""
    init_gift_tables()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE gift_suggestions SET chosen_gift=? WHERE id=?",
                 (chosen_gift, log_id))
    conn.commit()
    conn.close()


def get_suggestion_history(limit: int = 20) -> list[dict]:
    """Return past gift suggestion sessions."""
    init_gift_tables()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT contact_name, tier, interests_used, suggestions_json,
               ai_enhanced, chosen_gift, logged_at
        FROM gift_suggestions ORDER BY logged_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [{
        "contact_name":  r[0],
        "tier":          r[1],
        "interests":     json.loads(r[2] or "[]"),
        "suggestions":   json.loads(r[3] or "[]"),
        "ai_enhanced":   bool(r[4]),
        "chosen_gift":   r[5],
        "logged_at":     r[6],
    } for r in rows]


# ── Demo seeder ───────────────────────────────────────────────────────────────

def _seed_demo():
    init_gift_tables()
    conn  = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM gift_suggestions").fetchone()[0]
    conn.close()
    if count > 0:
        return
    contacts = [
        ("urn_rakib_001","Rakib Hossain","Close Friend",
         ["Python","Distributed Systems","reading","gym"],
         "Senior Backend Engineer at Pathao"),
        ("urn_nadia_002","Nadia Islam","Colleague",
         ["UI","UX","Figma","coffee","design"],
         "Product Designer at bKash"),
        ("urn_mim_004","Mim Chowdhury","Close Friend",
         ["machine learning","Python","books","travel"],
         "Data Scientist at Brain Station 23"),
    ]
    for cid, cname, tier, interests, job in contacts:
        get_gift_suggestions(cid, cname, interests, job, tier,
                             use_ai=False, verbose=False)


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Gift Suggestions", page_icon="🎁",
                       layout="wide", initial_sidebar_state="collapsed")

    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    html,body,[class*="css"]{font-family:'Inter',sans-serif;}
    :root{--bg:#0d1117;--surface:#161b22;--border:#30363d;--accent:#f78166;
          --green:#3fb950;--yellow:#d29922;--red:#f85149;--blue:#58a6ff;
          --muted:#8b949e;--text:#e6edf3;}
    .stApp{background:var(--bg);color:var(--text);}
    .cc-header{display:flex;align-items:center;gap:14px;padding:18px 0 10px;
               border-bottom:1px solid var(--border);margin-bottom:24px;}
    .cc-header h1{font-size:1.4rem;font-weight:700;letter-spacing:-0.02em;margin:0;}
    .cc-badge{background:var(--accent);color:#fff;font-size:0.65rem;font-weight:700;
              padding:2px 8px;border-radius:20px;letter-spacing:0.08em;text-transform:uppercase;}
    .cc-version{margin-left:auto;font-size:0.75rem;color:var(--muted);
                font-family:'JetBrains Mono',monospace;}
    .section-title{font-size:0.7rem;font-weight:700;text-transform:uppercase;
                   letter-spacing:0.1em;color:var(--muted);margin:22px 0 10px;
                   display:flex;align-items:center;gap:8px;}
    .section-title::after{content:'';flex:1;height:1px;background:var(--border);}
    .gift-card{background:var(--surface);border:1px solid var(--border);
               border-radius:10px;padding:14px 16px;margin-bottom:8px;}
    .cat-pill{display:inline-flex;font-size:0.62rem;font-weight:700;
              padding:2px 8px;border-radius:20px;text-transform:uppercase;}
    .hist-row{background:var(--surface);border:1px solid var(--border);
              border-radius:8px;padding:10px 14px;margin-bottom:6px;}
    .mini{background:#0d1117;border:1px solid #30363d;border-radius:8px;
          padding:10px;text-align:center;}
    .mini-val{font-size:1.4rem;font-weight:700;line-height:1;}
    .mini-lbl{font-size:0.58rem;color:#8b949e;text-transform:uppercase;
              letter-spacing:0.07em;margin-top:3px;}
    div[data-testid="stButton"]>button{background:var(--surface);
        border:1px solid var(--border);color:var(--text);border-radius:8px;
        font-size:0.79rem;font-weight:500;}
    div[data-testid="stButton"]>button:hover{border-color:#58a6ff;background:#1c2128;}
    div[data-testid="stButton"]>button[kind="primary"]{background:var(--accent);
        border-color:var(--accent);color:#fff;}
    ::-webkit-scrollbar{width:5px;}::-webkit-scrollbar-track{background:var(--bg);}
    ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
    </style>
    """, unsafe_allow_html=True)

    init_gift_tables()
    _seed_demo()

    CAT_COLORS = {
        "tech":"#58a6ff","design":"#bc8cff","books":"#3fb950",
        "food":"#f78166","fitness":"#3fb950","travel":"#d29922",
        "gaming":"#4fc3f7","general":"#8b949e",
    }

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">🎁</span>
      <h1>Gift Suggestion Engine</h1>
      <span class="cc-badge">v9.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    history = get_suggestion_history(50)
    ai_ok   = bool(OPENAI_KEY or GEMINI_KEY)

    m1, m2, m3, m4 = st.columns(4)
    for col, lbl, val, color in [
        (m1, "AI Enhanced",  "✓ Ready" if ai_ok else "✗ No key",
         "#3fb950" if ai_ok else "#d29922"),
        (m2, "Gift Categories", len(GIFT_CATALOGUE),    "#58a6ff"),
        (m3, "Gift Items",      sum(len(v) for v in GIFT_CATALOGUE.values()), "#f78166"),
        (m4, "Past Sessions",   len(history),            "#d29922"),
    ]:
        with col:
            st.markdown(f'<div class="mini"><div class="mini-val" style="color:{color}">'
                        f'{val}</div><div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1.2, 1], gap="large")

    with left:
        st.markdown('<div class="section-title">Generate Gift Ideas</div>',
                    unsafe_allow_html=True)
        cname     = st.text_input("Contact name", placeholder="Rakib Hossain",
                                  label_visibility="collapsed", key="cname")
        job_inp   = st.text_input("Job / Role",   placeholder="Senior Backend Engineer at Pathao",
                                  label_visibility="collapsed", key="job")
        interests = st.text_input("Interests (comma-separated)",
                                  placeholder="Python, gym, books, travel",
                                  label_visibility="collapsed", key="interests")
        tier_sel  = st.selectbox("Relationship tier",
                                 ["Close Friend","Colleague","Acquaintance"],
                                 label_visibility="collapsed", key="tier")
        use_ai    = st.checkbox("Enhance with AI note", value=ai_ok, key="use_ai")

        if st.button("🎁 Suggest Gifts", type="primary",
                     use_container_width=True):
            if cname:
                int_list = [i.strip() for i in interests.split(",") if i.strip()]
                with st.spinner("Finding perfect gifts..."):
                    result = get_gift_suggestions(
                        "manual_001", cname, int_list,
                        job=job_inp, tier=tier_sel,
                        use_ai=use_ai, verbose=False)
                st.session_state["last_result"] = result
                st.rerun()

        result = st.session_state.get("last_result")
        if result:
            cats_str = " · ".join(result["categories"])
            st.markdown(f"""
            <div style="background:#161b22;border:1px solid #30363d;
                        border-radius:8px;padding:10px 14px;margin-bottom:12px;
                        font-size:0.76rem;color:#8b949e;">
              Categories: <strong style="color:#e6edf3">{cats_str}</strong> ·
              Budget: <strong style="color:#3fb950">{result['budget_range']}</strong>
            </div>
            """, unsafe_allow_html=True)

            for i, g in enumerate(result["suggestions"], 1):
                cat_color = CAT_COLORS.get(g["category"], "#8b949e")
                st.markdown(f"""
                <div class="gift-card">
                  <div style="display:flex;align-items:center;
                              justify-content:space-between;margin-bottom:6px">
                    <div style="font-weight:700;font-size:0.88rem">
                      #{i} {g['name']}
                    </div>
                    <div style="display:flex;align-items:center;gap:6px">
                      <span class="cat-pill"
                            style="background:{cat_color}22;color:{cat_color};
                                   border:1px solid {cat_color}44">
                        {g['category']}
                      </span>
                      <span style="font-family:'JetBrains Mono',monospace;
                                   font-size:0.78rem;color:#3fb950">
                        {g['price']}
                      </span>
                    </div>
                  </div>
                  <div style="font-size:0.72rem;color:#c9d1d9">
                    {g['rationale']}
                  </div>
                </div>
                """, unsafe_allow_html=True)

            if result.get("ai_note"):
                st.markdown(f"""
                <div style="background:#0a1a2a;border:1px solid #1f3a5a;
                            border-left:3px solid #58a6ff;border-radius:8px;
                            padding:12px 14px;margin-top:8px;
                            font-size:0.80rem;color:#c9d1d9;line-height:1.6;">
                  <div style="font-size:0.65rem;color:#58a6ff;font-weight:700;
                               margin-bottom:4px">AI RECOMMENDATION</div>
                  {result['ai_note']}
                </div>
                """, unsafe_allow_html=True)

    with right:
        st.markdown('<div class="section-title">Past Sessions</div>',
                    unsafe_allow_html=True)
        for h in history[:10]:
            ts      = h["logged_at"][:16].replace("T", " ")
            top_gift= h["suggestions"][0]["name"] if h["suggestions"] else "–"
            chosen  = h.get("chosen_gift")
            st.markdown(f"""
            <div class="hist-row">
              <div style="display:flex;justify-content:space-between;
                          align-items:center;margin-bottom:4px">
                <div style="font-weight:700;font-size:0.84rem">
                  {h['contact_name']}
                </div>
                <span style="font-size:0.66rem;color:#8b949e">{ts}</span>
              </div>
              <div style="font-size:0.70rem;color:#c9d1d9">
                Top: <strong>{top_gift}</strong>
                {f'→ Sent: <span style="color:#3fb950">{chosen}</span>' if chosen else ''}
              </div>
              <div style="font-size:0.65rem;color:#8b949e;margin-top:3px">
                {h['tier']} · {len(h['suggestions'])} suggestions
                {'· 🤖 AI' if h['ai_enhanced'] else ''}
              </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">9.0</code></span>
      <span>Gift Suggestion Engine</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    init_gift_tables()
    print("=== Gift Suggestion Engine -- self test ===\n")
    test_contacts = [
        ("urn_rakib_001","Rakib Hossain","Close Friend",
         ["Python","Distributed Systems","gym","reading"],
         "Senior Backend Engineer at Pathao"),
        ("urn_nadia_002","Nadia Islam","Colleague",
         ["UX","Figma","coffee","design"],
         "Product Designer at bKash"),
        ("urn_mim_004","Mim Chowdhury","Close Friend",
         ["machine learning","books","travel","Python"],
         "Data Scientist"),
    ]
    for cid, cname, tier, interests, job in test_contacts:
        result = get_gift_suggestions(
            cid, cname, interests, job, tier,
            top_n=3, use_ai=False, verbose=True)
        print()
