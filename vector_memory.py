"""
Long-term Vector Memory v2 -- Birthday Wishes Agent v10.0
Production-ready semantic memory using pgvector (PostgreSQL extension)
with automatic fallback to SQLite + cosine similarity for dev.

What gets stored:
  - Contact interaction summaries (wish sent, reply, sentiment)
  - Conversation context (what was discussed, topics)
  - Relationship notes (preferences, interests, triggers)
  - Occasion memory (what worked last birthday, gift given)

How it works:
  1. Text → embedding via sentence-transformers or OpenAI
  2. Embedding stored in pgvector (prod) or SQLite JSON (dev)
  3. Query with natural language → cosine similarity search
  4. Returns ranked relevant memories for wish personalization

Requires (prod):
  pip install pgvector psycopg2-binary sentence-transformers

Integrates with: langgraph_workflow.py (generate node),
                 ai/multi_model_consensus.py,
                 ai/self_improving_agent.py, agent.py
"""

import os
import json
import sqlite3
import hashlib
import math
from pathlib import Path
from datetime import datetime
from typing import Optional

DB_PATH      = Path("agent_history.db")
DATABASE_URL = os.getenv("DATABASE_URL", "")
IS_POSTGRES  = DATABASE_URL.startswith("postgresql")
OPENAI_KEY   = os.getenv("OPENAI_API_KEY", "")

EMBEDDING_DIM   = 384    # all-MiniLM-L6-v2 default
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

MEMORY_TYPES = {
    "interaction": {"label": "Interaction",  "icon": "💬", "color": "#58a6ff"},
    "preference":  {"label": "Preference",   "icon": "⭐", "color": "#d29922"},
    "occasion":    {"label": "Occasion",     "icon": "🎂", "color": "#f78166"},
    "note":        {"label": "Note",         "icon": "📝", "color": "#3fb950"},
    "topic":       {"label": "Topic",        "icon": "💡", "color": "#bc8cff"},
}


# ── DB setup ──────────────────────────────────────────────────────────────────

def init_memory_tables():
    """Create memory tables in SQLite (dev) or PostgreSQL (prod)."""
    if IS_POSTGRES:
        _init_pgvector()
    else:
        _init_sqlite()


def _init_sqlite():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vector_memories (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            memory_type     TEXT NOT NULL DEFAULT 'note',
            content         TEXT NOT NULL,
            embedding_json  TEXT,
            metadata_json   TEXT,
            importance      REAL NOT NULL DEFAULT 0.5,
            created_at      TEXT NOT NULL,
            accessed_at     TEXT NOT NULL,
            access_count    INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_vm_contact
        ON vector_memories(contact_id)
    """)
    conn.commit()
    conn.close()


def _init_pgvector():
    try:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
        cur  = conn.cursor()
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS vector_memories (
                id              BIGSERIAL PRIMARY KEY,
                contact_id      TEXT NOT NULL,
                memory_type     TEXT NOT NULL DEFAULT 'note',
                content         TEXT NOT NULL,
                embedding       vector({EMBEDDING_DIM}),
                metadata_json   TEXT,
                importance      DOUBLE PRECISION NOT NULL DEFAULT 0.5,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                accessed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                access_count    INTEGER NOT NULL DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_vm_contact
            ON vector_memories(contact_id)
        """)
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_vm_embedding
            ON vector_memories
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 10)
        """)
        conn.commit()
        conn.close()
    except Exception as exc:
        print(f"[VectorMem] pgvector init failed: {exc}")
        print("[VectorMem] Falling back to SQLite")


# ── Embedding generation ──────────────────────────────────────────────────────

_local_model = None


def _get_embedding(text: str) -> list[float]:
    """Generate embedding vector for text."""
    # Try sentence-transformers first (local, free)
    global _local_model
    try:
        if _local_model is None:
            from sentence_transformers import SentenceTransformer
            _local_model = SentenceTransformer(EMBEDDING_MODEL)
        vec = _local_model.encode(text, normalize_embeddings=True)
        return vec.tolist()
    except ImportError:
        pass

    # Try OpenAI embeddings
    if OPENAI_KEY:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_KEY)
            resp   = client.embeddings.create(
                model="text-embedding-3-small", input=text)
            return resp.data[0].embedding[:EMBEDDING_DIM]
        except Exception:
            pass

    # Fallback: deterministic hash-based pseudo-embedding (dev only)
    return _hash_embedding(text)


def _hash_embedding(text: str) -> list[float]:
    """Deterministic pseudo-embedding for dev/testing (no ML model needed)."""
    h    = hashlib.sha256(text.encode()).hexdigest()
    vec  = []
    for i in range(0, min(len(h), EMBEDDING_DIM * 2), 2):
        val = (int(h[i:i+2], 16) - 128) / 128.0
        vec.append(round(val, 6))
    while len(vec) < EMBEDDING_DIM:
        vec.append(0.0)
    # Normalize
    norm = math.sqrt(sum(v*v for v in vec)) or 1.0
    return [round(v / norm, 6) for v in vec]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot  = sum(x*y for x, y in zip(a, b))
    na   = math.sqrt(sum(x*x for x in a)) or 1.0
    nb   = math.sqrt(sum(x*x for x in b)) or 1.0
    return dot / (na * nb)


# ── Memory CRUD ───────────────────────────────────────────────────────────────

def store_memory(
    contact_id:  str,
    content:     str,
    memory_type: str = "note",
    metadata:    Optional[dict] = None,
    importance:  float = 0.5,
) -> int:
    """
    Store a memory with its embedding vector.

    Args:
        contact_id:  Contact this memory belongs to.
        content:     Natural language memory text.
        memory_type: interaction / preference / occasion / note / topic.
        metadata:    Extra structured data (platform, date, etc.)
        importance:  0.0-1.0 weight for retrieval ranking.

    Returns:
        Memory row ID.
    """
    init_memory_tables()
    embedding = _get_embedding(content)
    now       = datetime.now().isoformat()

    if IS_POSTGRES:
        return _store_pg(contact_id, content, memory_type,
                         embedding, metadata, importance, now)
    return _store_sqlite(contact_id, content, memory_type,
                         embedding, metadata, importance, now)


def _store_sqlite(cid, content, mtype, embedding, metadata, importance, now):
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.execute("""
        INSERT INTO vector_memories
            (contact_id, memory_type, content, embedding_json,
             metadata_json, importance, created_at, accessed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (cid, mtype, content, json.dumps(embedding),
          json.dumps(metadata or {}), importance, now, now))
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def _store_pg(cid, content, mtype, embedding, metadata, importance, now):
    try:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO vector_memories
                (contact_id, memory_type, content, embedding,
                 metadata_json, importance, created_at, accessed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (cid, mtype, content, embedding,
              json.dumps(metadata or {}), importance, now, now))
        row_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        return row_id
    except Exception as exc:
        print(f"[VectorMem] PG store failed: {exc}")
        return _store_sqlite(cid, content, mtype, embedding,
                             metadata, importance, now)


# ── Retrieval ─────────────────────────────────────────────────────────────────

def recall(
    query:       str,
    contact_id:  Optional[str] = None,
    top_k:       int = 5,
    memory_type: Optional[str] = None,
    min_score:   float = 0.3,
) -> list[dict]:
    """
    Retrieve relevant memories by semantic similarity.

    Args:
        query:       Natural language query.
        contact_id:  Limit to one contact (None = search all).
        top_k:       Max results to return.
        memory_type: Filter by type (None = all types).
        min_score:   Minimum cosine similarity threshold.

    Returns:
        List of { content, memory_type, similarity, importance,
                  contact_id, metadata, created_at }
    """
    init_memory_tables()
    query_vec = _get_embedding(query)

    if IS_POSTGRES:
        return _recall_pg(query_vec, contact_id, top_k,
                          memory_type, min_score)
    return _recall_sqlite(query_vec, contact_id, top_k,
                          memory_type, min_score)


def _recall_sqlite(query_vec, contact_id, top_k, memory_type, min_score):
    conn = sqlite3.connect(DB_PATH)
    sql  = "SELECT id, contact_id, memory_type, content, embedding_json, metadata_json, importance, created_at FROM vector_memories WHERE 1=1"
    params = []
    if contact_id:
        sql   += " AND contact_id=?"
        params.append(contact_id)
    if memory_type:
        sql   += " AND memory_type=?"
        params.append(memory_type)

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    scored = []
    for r in rows:
        try:
            emb = json.loads(r[4] or "[]")
        except (json.JSONDecodeError, TypeError):
            continue
        if not emb:
            continue
        sim = _cosine_similarity(query_vec, emb)
        if sim >= min_score:
            scored.append({
                "id":          r[0],
                "contact_id":  r[1],
                "memory_type": r[2],
                "content":     r[3],
                "similarity":  round(sim, 4),
                "importance":  r[6],
                "metadata":    json.loads(r[5] or "{}"),
                "created_at":  r[7],
                "icon":        MEMORY_TYPES.get(r[2],{}).get("icon","📝"),
                "color":       MEMORY_TYPES.get(r[2],{}).get("color","#8b949e"),
            })

    # Rank by similarity * importance
    scored.sort(key=lambda x: -(x["similarity"] * 0.7 + x["importance"] * 0.3))

    # Update access counts
    conn = sqlite3.connect(DB_PATH)
    now  = datetime.now().isoformat()
    for s in scored[:top_k]:
        conn.execute("""
            UPDATE vector_memories SET access_count = access_count + 1,
            accessed_at = ? WHERE id = ?
        """, (now, s["id"]))
    conn.commit()
    conn.close()

    return scored[:top_k]


def _recall_pg(query_vec, contact_id, top_k, memory_type, min_score):
    try:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
        cur  = conn.cursor()
        sql  = """
            SELECT id, contact_id, memory_type, content,
                   1 - (embedding <=> %s::vector) as similarity,
                   importance, metadata_json, created_at
            FROM vector_memories WHERE 1=1
        """
        params = [query_vec]
        if contact_id:
            sql   += " AND contact_id=%s"
            params.append(contact_id)
        if memory_type:
            sql   += " AND memory_type=%s"
            params.append(memory_type)
        sql += f" ORDER BY embedding <=> %s::vector LIMIT {top_k}"
        params.append(query_vec)

        cur.execute(sql, params)
        rows = cur.fetchall()
        conn.close()

        results = []
        for r in rows:
            sim = float(r[4])
            if sim >= min_score:
                results.append({
                    "id":          r[0],
                    "contact_id":  r[1],
                    "memory_type": r[2],
                    "content":     r[3],
                    "similarity":  round(sim, 4),
                    "importance":  r[5],
                    "metadata":    json.loads(r[6] or "{}"),
                    "created_at":  str(r[7]),
                    "icon":        MEMORY_TYPES.get(r[2],{}).get("icon","📝"),
                    "color":       MEMORY_TYPES.get(r[2],{}).get("color","#8b949e"),
                })
        return results
    except Exception as exc:
        print(f"[VectorMem] PG recall failed: {exc}, falling back to SQLite")
        return _recall_sqlite(
            _get_embedding(""), contact_id, top_k, memory_type, min_score)


# ── Context builder ───────────────────────────────────────────────────────────

def get_contact_context(
    contact_id:   str,
    query:        str = "",
    max_memories: int = 5,
) -> str:
    """
    Build a context string from a contact's memories for prompt injection.
    Used by the generate node in langgraph_workflow.py.

    Returns:
        Multi-line string of relevant memories, ready to paste into a prompt.
    """
    if not query:
        query = f"birthday wish personalization context"

    memories = recall(query, contact_id=contact_id, top_k=max_memories)
    if not memories:
        return "(No memories stored for this contact yet.)"

    lines = []
    for m in memories:
        lines.append(f"- [{m['memory_type']}] {m['content']}")
    return "\n".join(lines)


# ── Bulk operations ───────────────────────────────────────────────────────────

def store_interaction_memory(
    contact_id:   str,
    contact_name: str,
    platform:     str,
    wish_text:    str,
    replied:      bool = False,
    sentiment:    Optional[float] = None,
) -> int:
    """Convenience: store a wish interaction as a memory."""
    reply_note = f"replied (sentiment {sentiment}/5)" if replied else "no reply"
    content    = (f"Sent birthday wish to {contact_name} via {platform}. "
                  f"Wish: \"{wish_text[:80]}...\". Outcome: {reply_note}.")
    return store_memory(
        contact_id, content, "interaction",
        metadata={"platform": platform, "replied": replied,
                  "sentiment": sentiment},
        importance=0.6 if replied else 0.4)


def store_preference(
    contact_id:   str,
    contact_name: str,
    preference:   str,
) -> int:
    """Store a discovered preference/interest for a contact."""
    content = f"{contact_name}: {preference}"
    return store_memory(contact_id, content, "preference",
                        importance=0.7)


def store_occasion_note(
    contact_id:   str,
    contact_name: str,
    occasion:     str,
    note:         str,
) -> int:
    """Store what worked/didn't for a specific occasion."""
    content = f"{contact_name} — {occasion}: {note}"
    return store_memory(contact_id, content, "occasion",
                        importance=0.8)


def get_memory_stats() -> dict:
    """Return memory store statistics."""
    init_memory_tables()
    conn   = sqlite3.connect(DB_PATH)
    total  = conn.execute(
        "SELECT COUNT(*) FROM vector_memories").fetchone()[0]
    by_type = conn.execute("""
        SELECT memory_type, COUNT(*) FROM vector_memories
        GROUP BY memory_type ORDER BY COUNT(*) DESC
    """).fetchall()
    contacts = conn.execute("""
        SELECT COUNT(DISTINCT contact_id) FROM vector_memories
    """).fetchone()[0]
    conn.close()
    return {
        "total_memories": total,
        "contacts":       contacts,
        "backend":        "pgvector" if IS_POSTGRES else "sqlite",
        "embedding_dim":  EMBEDDING_DIM,
        "by_type":        {r[0]: r[1] for r in by_type},
    }


# ── Demo seeder ───────────────────────────────────────────────────────────────

def _seed_demo():
    init_memory_tables()
    conn  = sqlite3.connect(DB_PATH)
    count = conn.execute(
        "SELECT COUNT(*) FROM vector_memories").fetchone()[0]
    conn.close()
    if count > 0:
        return

    memories = [
        ("urn_rakib_001", "interaction",
         "Sent birthday wish to Rakib via LinkedIn. He replied within 2 hours with a grateful message. Sentiment was very positive (4.5/5).",
         0.7),
        ("urn_rakib_001", "preference",
         "Rakib Hossain: Prefers concise, professional wishes. Responds well to tech references and career milestone acknowledgments.",
         0.8),
        ("urn_rakib_001", "occasion",
         "Rakib Hossain — Birthday 2025: Warm wish with career reference worked well. He forwarded it to his team. Avoid overly casual tone.",
         0.9),
        ("urn_nadia_002", "interaction",
         "Sent birthday wish to Nadia via WhatsApp. She replied with heart emoji and a thank you voice note. Very warm response.",
         0.6),
        ("urn_nadia_002", "preference",
         "Nadia Islam: Loves creative, emoji-rich wishes. Responds to visual/design references. Prefers WhatsApp over email.",
         0.8),
        ("urn_mim_004", "preference",
         "Mim Chowdhury: Values thoughtful, personal messages. Mention her ML research or IUT days for best engagement.",
         0.7),
        ("urn_mim_004", "topic",
         "Mim is working on a new recommendation engine at Brain Station 23. Interested in NLP and transformer models.",
         0.5),
    ]
    for cid, mtype, content, imp in memories:
        store_memory(cid, content, mtype, importance=imp)


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Vector Memory", page_icon="🧠",
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
    .mem-card{background:var(--surface);border:1px solid var(--border);
              border-radius:10px;padding:12px 16px;margin-bottom:8px;}
    .mini{background:#0d1117;border:1px solid #30363d;border-radius:8px;
          padding:10px;text-align:center;}
    .mini-val{font-size:1.3rem;font-weight:700;line-height:1;}
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

    init_memory_tables()
    _seed_demo()
    stats = get_memory_stats()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">🧠</span>
      <h1>Vector Memory v2</h1>
      <span class="cc-badge">v10.0</span>
      <span class="cc-version">pgvector / SQLite</span>
    </div>
    """, unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    for col, lbl, val, color in [
        (m1, "Memories",    stats["total_memories"], "#f78166"),
        (m2, "Contacts",    stats["contacts"],       "#58a6ff"),
        (m3, "Backend",     stats["backend"],        "#3fb950"),
        (m4, "Embed Dim",   stats["embedding_dim"],  "#d29922"),
    ]:
        with col:
            st.markdown(f'<div class="mini"><div class="mini-val" '
                        f'style="color:{color};font-size:0.95rem">'
                        f'{val}</div><div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1, 1.5], gap="large")

    with left:
        st.markdown('<div class="section-title">Semantic Search</div>',
                    unsafe_allow_html=True)
        query   = st.text_input("Query", placeholder="What does Rakib prefer?",
                                label_visibility="collapsed", key="q")
        cid_flt = st.text_input("Contact ID filter (optional)",
                                placeholder="urn_rakib_001",
                                label_visibility="collapsed", key="cf")
        if st.button("🔍 Search", type="primary", use_container_width=True):
            if query:
                with st.spinner("Searching..."):
                    results = recall(query, cid_flt or None, top_k=5)
                st.session_state["mem_results"] = results
                st.rerun()

        st.markdown('<div class="section-title">Store Memory</div>',
                    unsafe_allow_html=True)
        s_cid     = st.text_input("Contact ID", placeholder="urn_rakib_001",
                                  label_visibility="collapsed", key="scid")
        s_content = st.text_area("Memory content", height=60,
                                 label_visibility="collapsed", key="sc",
                                 placeholder="Rakib prefers professional tone...")
        s_type    = st.selectbox("Type", list(MEMORY_TYPES.keys()),
                                 label_visibility="collapsed", key="st")
        if st.button("💾 Store", use_container_width=True):
            if s_cid and s_content:
                mid = store_memory(s_cid, s_content, s_type)
                st.success(f"Memory #{mid} stored")
                st.rerun()

        # Type breakdown
        st.markdown('<div class="section-title">By Type</div>',
                    unsafe_allow_html=True)
        for mtype, count in stats["by_type"].items():
            meta  = MEMORY_TYPES.get(mtype, MEMORY_TYPES["note"])
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:8px;
                        padding:4px 0;border-bottom:1px solid #21262d">
              <span>{meta['icon']}</span>
              <span style="flex:1;font-size:0.78rem">{meta['label']}</span>
              <span style="font-weight:700;color:{meta['color']};
                          font-size:0.82rem">{count}</span>
            </div>
            """, unsafe_allow_html=True)

    with right:
        st.markdown('<div class="section-title">Search Results</div>',
                    unsafe_allow_html=True)
        results = st.session_state.get("mem_results", [])
        if not results:
            st.caption("Enter a query and click Search.")
        for r in results:
            sim_pct = int(r["similarity"] * 100)
            st.markdown(f"""
            <div class="mem-card" style="border-left:3px solid {r['color']}">
              <div style="display:flex;align-items:center;
                          justify-content:space-between;margin-bottom:6px">
                <span style="font-size:0.68rem;color:{r['color']};
                             font-weight:700">
                  {r['icon']} {r['memory_type'].upper()}
                </span>
                <span style="font-family:'JetBrains Mono',monospace;
                             font-size:0.75rem;color:#3fb950">
                  {sim_pct}% match
                </span>
              </div>
              <div style="font-size:0.80rem;color:#c9d1d9;line-height:1.5">
                {r['content'][:200]}{'...' if len(r['content'])>200 else ''}
              </div>
              <div style="font-size:0.65rem;color:#8b949e;margin-top:6px">
                {r['contact_id']} · imp {r['importance']} ·
                {r['created_at'][:16]}
              </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">10.0</code></span>
      <span>Vector Memory v2</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    init_memory_tables()
    _seed_demo()
    print("=== Vector Memory v2 -- self test ===\n")

    stats = get_memory_stats()
    print(f"Backend    : {stats['backend']}")
    print(f"Memories   : {stats['total_memories']}")
    print(f"Contacts   : {stats['contacts']}")
    print(f"Embed dim  : {stats['embedding_dim']}")
    print(f"By type    : {stats['by_type']}")

    print("\nSemantic search: 'What does Rakib prefer?'")
    results = recall("What does Rakib prefer?", top_k=3)
    for r in results:
        print(f"  {r['icon']} [{r['similarity']:.0%}] {r['content'][:70]}...")

    print("\nContext builder for Rakib:")
    ctx = get_contact_context("urn_rakib_001")
    for line in ctx.split("\n"):
        print(f"  {line}")

    print("\nStore test:")
    mid = store_memory("urn_test_001", "Test user likes Python and coffee.",
                       "preference", importance=0.6)
    print(f"  Stored memory #{mid}")

    results2 = recall("Python coffee", contact_id="urn_test_001", top_k=1)
    if results2:
        print(f"  Recall: [{results2[0]['similarity']:.0%}] {results2[0]['content']}")
else:
    render_dashboard()
