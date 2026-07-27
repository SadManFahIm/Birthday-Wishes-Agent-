"""
Model Config -- Birthday Wishes Agent v10.0
Centralized model registry with speed/cost/quality tiers.
Automatically selects the best model for each task type.

Models supported:
  Claude:  claude-sonnet-4-6, claude-haiku-4-5 (fast/cheap)
  Gemini:  gemini-2.5-flash, gemini-2.5-pro
  OpenAI:  gpt-4o, gpt-4o-mini

Task routing:
  wish_generation  → claude-sonnet-4-6 (default) / gemini-2.5-flash (fast)
  consensus        → gemini-2.5-pro + gpt-4o (multi-model)
  scoring          → claude-haiku-4-5 / gemini-2.5-flash (cheap)
  summarization    → claude-haiku-4-5 / gemini-2.5-flash (cheapest)
  gift_suggestion  → gemini-2.5-flash (fast)
  self_improvement → claude-sonnet-4-6 (best reasoning)

Integrates with: ai/multi_model_consensus.py,
                 ai/self_improving_agent.py, langgraph_workflow.py
"""

import os
import time
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, Any

DB_PATH = Path("agent_history.db")

# ── Model registry ────────────────────────────────────────────────────────────

MODELS = {
    # ── Anthropic ─────────────────────────────────────────────────────────────
    "claude-sonnet-4-6": {
        "provider":      "anthropic",
        "label":         "Claude Sonnet 4.6",
        "tier":          "premium",
        "context_k":     200,
        "input_per_1m":  3.0,    # USD
        "output_per_1m": 15.0,
        "speed":         "medium",
        "strengths":     ["reasoning","writing","code","nuance"],
        "env_key":       "ANTHROPIC_API_KEY",
    },
    "claude-haiku-4-5": {
        "provider":      "anthropic",
        "label":         "Claude Haiku 4.5",
        "tier":          "fast",
        "context_k":     200,
        "input_per_1m":  0.80,
        "output_per_1m": 4.0,
        "speed":         "fast",
        "strengths":     ["classification","scoring","short_tasks"],
        "env_key":       "ANTHROPIC_API_KEY",
    },
    # ── Google ────────────────────────────────────────────────────────────────
    "gemini-2.5-flash": {
        "provider":      "google",
        "label":         "Gemini 2.5 Flash",
        "tier":          "fast",
        "context_k":     1000,
        "input_per_1m":  0.075,
        "output_per_1m": 0.30,
        "speed":         "fastest",
        "strengths":     ["speed","long_context","multilingual","cost"],
        "env_key":       "GOOGLE_API_KEY",
    },
    "gemini-2.5-pro": {
        "provider":      "google",
        "label":         "Gemini 2.5 Pro",
        "tier":          "premium",
        "context_k":     2000,
        "input_per_1m":  1.25,
        "output_per_1m": 10.0,
        "speed":         "medium",
        "strengths":     ["reasoning","long_context","multimodal","complex_tasks"],
        "env_key":       "GOOGLE_API_KEY",
    },
    # ── OpenAI ────────────────────────────────────────────────────────────────
    "gpt-4o": {
        "provider":      "openai",
        "label":         "GPT-4o",
        "tier":          "premium",
        "context_k":     128,
        "input_per_1m":  5.0,
        "output_per_1m": 15.0,
        "speed":         "medium",
        "strengths":     ["instruction_following","creativity","structured_output"],
        "env_key":       "OPENAI_API_KEY",
    },
    "gpt-4o-mini": {
        "provider":      "openai",
        "label":         "GPT-4o Mini",
        "tier":          "fast",
        "context_k":     128,
        "input_per_1m":  0.15,
        "output_per_1m": 0.60,
        "speed":         "fast",
        "strengths":     ["speed","cost","simple_tasks"],
        "env_key":       "OPENAI_API_KEY",
    },
}

# ── Task → model routing ──────────────────────────────────────────────────────

TASK_ROUTING = {
    "wish_generation":  {
        "default":  "claude-sonnet-4-6",
        "fast":     "gemini-2.5-flash",
        "cheap":    "gemini-2.5-flash",
        "premium":  "claude-sonnet-4-6",
    },
    "consensus_primary": {
        "default":  "gemini-2.5-pro",
        "fast":     "gemini-2.5-flash",
        "cheap":    "gemini-2.5-flash",
        "premium":  "gemini-2.5-pro",
    },
    "consensus_secondary": {
        "default":  "gpt-4o",
        "fast":     "gpt-4o-mini",
        "cheap":    "gpt-4o-mini",
        "premium":  "gpt-4o",
    },
    "scoring": {
        "default":  "claude-haiku-4-5",
        "fast":     "gemini-2.5-flash",
        "cheap":    "gemini-2.5-flash",
        "premium":  "claude-sonnet-4-6",
    },
    "summarization": {
        "default":  "claude-haiku-4-5",
        "fast":     "gemini-2.5-flash",
        "cheap":    "gemini-2.5-flash",
        "premium":  "claude-haiku-4-5",
    },
    "gift_suggestion": {
        "default":  "gemini-2.5-flash",
        "fast":     "gemini-2.5-flash",
        "cheap":    "gemini-2.5-flash",
        "premium":  "gpt-4o",
    },
    "self_improvement": {
        "default":  "claude-sonnet-4-6",
        "fast":     "gemini-2.5-flash",
        "cheap":    "gemini-2.5-flash",
        "premium":  "claude-sonnet-4-6",
    },
    "prompt_tuning": {
        "default":  "claude-sonnet-4-6",
        "fast":     "gemini-2.5-flash",
        "cheap":    "gemini-2.5-flash",
        "premium":  "claude-sonnet-4-6",
    },
}

MODE = os.getenv("MODEL_MODE", "default")   # default | fast | cheap | premium


# ── DB setup ──────────────────────────────────────────────────────────────────

def init_model_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS model_usage_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            task          TEXT NOT NULL,
            model_id      TEXT NOT NULL,
            provider      TEXT NOT NULL,
            input_tokens  INTEGER,
            output_tokens INTEGER,
            latency_ms    INTEGER,
            cost_usd      REAL,
            success       INTEGER NOT NULL DEFAULT 1,
            error_msg     TEXT,
            logged_at     TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── Model selection ───────────────────────────────────────────────────────────

def get_model(task: str, mode: Optional[str] = None) -> dict:
    """
    Return the best available model for a task + mode.

    Args:
        task: Task name from TASK_ROUTING keys.
        mode: override MODE env var (default/fast/cheap/premium).

    Returns:
        Model config dict including model_id and all metadata.
    """
    m         = mode or MODE
    routing   = TASK_ROUTING.get(task, TASK_ROUTING["wish_generation"])
    model_id  = routing.get(m, routing["default"])
    model_cfg = MODELS.get(model_id, MODELS["gemini-2.5-flash"])

    # Check if API key is available; fall back down the priority chain
    env_key = model_cfg.get("env_key", "")
    if env_key and not os.getenv(env_key):
        # Try fast tier fallback
        fallback_id  = routing.get("fast", routing["default"])
        fallback_cfg = MODELS.get(fallback_id, model_cfg)
        fb_key       = fallback_cfg.get("env_key", "")
        if fb_key and not os.getenv(fb_key):
            # Both unavailable — return mock
            return {**model_cfg, "model_id": model_id, "mock": True}
        model_id  = fallback_id
        model_cfg = fallback_cfg

    return {**model_cfg, "model_id": model_id, "mock": False}


def estimate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD for a generation."""
    m = MODELS.get(model_id, {})
    return round(
        (input_tokens  / 1_000_000) * m.get("input_per_1m",  1.0) +
        (output_tokens / 1_000_000) * m.get("output_per_1m", 5.0),
        6
    )


def log_usage(
    task:          str,
    model_id:      str,
    input_tokens:  int = 0,
    output_tokens: int = 0,
    latency_ms:    int = 0,
    success:       bool = True,
    error_msg:     str = "",
) -> None:
    """Log model usage for cost tracking and performance analytics."""
    init_model_tables()
    model  = MODELS.get(model_id, {})
    cost   = estimate_cost(model_id, input_tokens, output_tokens)
    conn   = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO model_usage_log
            (task, model_id, provider, input_tokens, output_tokens,
             latency_ms, cost_usd, success, error_msg, logged_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (task, model_id, model.get("provider","unknown"),
          input_tokens, output_tokens, latency_ms,
          cost, 1 if success else 0, error_msg,
          datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_usage_stats(days: int = 30) -> dict:
    """Return aggregated usage stats for the last N days."""
    init_model_tables()
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn   = sqlite3.connect(DB_PATH)
    rows   = conn.execute("""
        SELECT model_id, provider,
               COUNT(*)                as calls,
               SUM(input_tokens)       as total_input,
               SUM(output_tokens)      as total_output,
               SUM(cost_usd)           as total_cost,
               AVG(latency_ms)         as avg_latency,
               SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) as successes
        FROM model_usage_log
        WHERE logged_at >= ?
        GROUP BY model_id ORDER BY total_cost DESC
    """, (cutoff,)).fetchall()
    conn.close()
    total_cost = sum(r[5] or 0 for r in rows)
    return {
        "total_cost_usd": round(total_cost, 4),
        "total_calls":    sum(r[2] for r in rows),
        "models": [{
            "model_id":    r[0],
            "provider":    r[1],
            "calls":       r[2],
            "total_input": r[3] or 0,
            "total_output":r[4] or 0,
            "cost_usd":    round(r[5] or 0, 4),
            "avg_latency": round(r[6] or 0, 1),
            "success_rate":round((r[7] or 0) / (r[2] or 1), 2),
        } for r in rows],
    }


# ── Unified inference client ──────────────────────────────────────────────────

def generate(
    prompt:   str,
    task:     str = "wish_generation",
    mode:     Optional[str] = None,
    max_tokens:int = 300,
    system:   str = "",
) -> dict:
    """
    Unified inference function — auto-selects model, calls API, logs usage.

    Args:
        prompt:     User message / wish generation prompt.
        task:       Task type for model routing.
        mode:       Override: default / fast / cheap / premium.
        max_tokens: Max output tokens.
        system:     System prompt (optional).

    Returns:
        {
          text, model_id, provider, input_tokens, output_tokens,
          latency_ms, cost_usd, mock
        }
    """
    model_cfg = get_model(task, mode)
    model_id  = model_cfg["model_id"]
    provider  = model_cfg.get("provider", "unknown")
    t0        = time.time()

    if model_cfg.get("mock"):
        # No API key available — return graceful mock
        mock_text = (
            f"Happy Birthday! [mock — set {model_cfg.get('env_key','')} to use {model_id}]"
        )
        return {"text": mock_text, "model_id": model_id, "provider": provider,
                "input_tokens": 0, "output_tokens": 0, "latency_ms": 0,
                "cost_usd": 0.0, "mock": True}

    text        = ""
    input_tok   = 0
    output_tok  = 0
    success     = False
    error_msg   = ""

    try:
        if provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY",""))
            msgs   = [{"role": "user", "content": prompt}]
            kwargs: dict = {"model": model_id, "max_tokens": max_tokens,
                            "messages": msgs}
            if system:
                kwargs["system"] = system
            resp       = client.messages.create(**kwargs)
            text       = resp.content[0].text.strip()
            input_tok  = resp.usage.input_tokens
            output_tok = resp.usage.output_tokens
            success    = True

        elif provider == "google":
            import google.generativeai as genai  # type: ignore
            genai.configure(api_key=os.getenv("GOOGLE_API_KEY", ""))
            cfg   = genai.types.GenerationConfig(max_output_tokens=max_tokens)
            model = genai.GenerativeModel(model_id,
                                          generation_config=cfg,
                                          system_instruction=system or None)
            resp       = model.generate_content(prompt)
            text       = resp.text.strip()
            # Gemini doesn't always return token counts — estimate
            input_tok  = len(prompt.split()) * 4 // 3
            output_tok = len(text.split()) * 4 // 3
            success    = True

        elif provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
            msgs_  = []
            if system:
                msgs_.append({"role": "system", "content": system})
            msgs_.append({"role": "user", "content": prompt})
            resp       = client.chat.completions.create(
                model=model_id, messages=msgs_, max_tokens=max_tokens)
            text       = resp.choices[0].message.content.strip()
            input_tok  = resp.usage.prompt_tokens
            output_tok = resp.usage.completion_tokens
            success    = True

    except Exception as exc:
        error_msg = str(exc)[:200]
        text      = f"[Error: {error_msg}]"

    latency_ms = int((time.time() - t0) * 1000)
    cost_usd   = estimate_cost(model_id, input_tok, output_tok)

    log_usage(task, model_id, input_tok, output_tok,
              latency_ms, success, error_msg)

    return {
        "text":         text,
        "model_id":     model_id,
        "provider":     provider,
        "input_tokens": input_tok,
        "output_tokens":output_tok,
        "latency_ms":   latency_ms,
        "cost_usd":     cost_usd,
        "mock":         False,
        "success":      success,
        "error":        error_msg,
    }


# ── Cost comparison helper ────────────────────────────────────────────────────

def compare_models_for_task(task: str, sample_tokens: int = 500) -> list[dict]:
    """Show estimated cost for all available models for a task."""
    rows = []
    for mode in ["default", "fast", "cheap", "premium"]:
        cfg = get_model(task, mode)
        mid = cfg["model_id"]
        cost = estimate_cost(mid, sample_tokens, 150)
        rows.append({
            "mode":     mode,
            "model_id": mid,
            "label":    cfg["label"],
            "speed":    cfg["speed"],
            "cost_usd": cost,
            "tier":     cfg["tier"],
            "mock":     cfg.get("mock", False),
        })
    # deduplicate same model_id
    seen   = set()
    unique = []
    for r in rows:
        if r["model_id"] not in seen:
            seen.add(r["model_id"])
            unique.append(r)
    unique.sort(key=lambda x: x["cost_usd"])
    return unique


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Model Config", page_icon="🧠",
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
    .model-card{background:var(--surface);border:1px solid var(--border);
                border-radius:10px;padding:14px 16px;margin-bottom:8px;}
    .mini{background:#0d1117;border:1px solid #30363d;border-radius:8px;
          padding:10px;text-align:center;}
    .mini-val{font-size:1.3rem;font-weight:700;line-height:1;}
    .mini-lbl{font-size:0.58rem;color:#8b949e;text-transform:uppercase;
              letter-spacing:0.07em;margin-top:3px;}
    .usage-row{background:var(--surface);border:1px solid var(--border);
               border-radius:8px;padding:10px 14px;margin-bottom:6px;
               font-size:0.78rem;}
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

    init_model_tables()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">🧠</span>
      <h1>Model Config</h1>
      <span class="cc-badge">v10.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    PROVIDER_COLORS = {"anthropic":"#f78166","google":"#58a6ff","openai":"#3fb950"}
    SPEED_COLORS    = {"fastest":"#3fb950","fast":"#58a6ff",
                       "medium":"#d29922","slow":"#f85149"}

    # Check which keys are set
    keys = {
        "ANTHROPIC_API_KEY": bool(os.getenv("ANTHROPIC_API_KEY")),
        "GOOGLE_API_KEY":    bool(os.getenv("GOOGLE_API_KEY")),
        "OPENAI_API_KEY":    bool(os.getenv("OPENAI_API_KEY")),
    }
    available = sum(keys.values())

    m1, m2, m3, m4 = st.columns(4)
    for col, lbl, val, color in [
        (m1, "Models Available", len([m for m in MODELS.values()
                                      if os.getenv(m.get("env_key",""))]),
         "#3fb950"),
        (m2, "API Keys Set", available, "#58a6ff" if available else "#f85149"),
        (m3, "Current Mode",  MODE.upper(), "#d29922"),
        (m4, "Task Routes",   len(TASK_ROUTING), "#f78166"),
    ]:
        with col:
            st.markdown(f'<div class="mini"><div class="mini-val" style="color:{color}">'
                        f'{val}</div><div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1.2, 1], gap="large")

    with left:
        st.markdown('<div class="section-title">Model Registry</div>',
                    unsafe_allow_html=True)
        for mid, cfg in MODELS.items():
            key_ok = bool(os.getenv(cfg.get("env_key", "")))
            pcolor = PROVIDER_COLORS.get(cfg["provider"], "#8b949e")
            scolor = SPEED_COLORS.get(cfg["speed"], "#8b949e")
            st.markdown(f"""
            <div class="model-card" style="{'border-color:'+pcolor+'44;' if key_ok else 'opacity:0.55;'}">
              <div style="display:flex;align-items:center;justify-content:space-between">
                <div>
                  <div style="font-weight:700;font-size:0.86rem;
                              font-family:'JetBrains Mono',monospace">
                    {mid}
                  </div>
                  <div style="font-size:0.68rem;color:#8b949e;margin-top:2px">
                    {cfg['label']} · {cfg['context_k']}k ctx
                  </div>
                </div>
                <div style="text-align:right">
                  <div style="font-size:0.68rem;color:{scolor};font-weight:700">
                    {cfg['speed'].upper()}
                  </div>
                  <div style="font-size:0.65rem;color:#8b949e;margin-top:1px">
                    {'✅ key set' if key_ok else '⚠ no key'}
                  </div>
                </div>
              </div>
              <div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap">
                <span style="font-size:0.62rem;padding:2px 6px;border-radius:12px;
                             background:{pcolor}22;color:{pcolor};
                             border:1px solid {pcolor}44;font-weight:700">
                  {cfg['provider']}
                </span>
                <span style="font-size:0.62rem;padding:2px 6px;border-radius:12px;
                             background:#21262d;color:#8b949e">
                  in ${cfg['input_per_1m']}/M · out ${cfg['output_per_1m']}/M
                </span>
              </div>
            </div>
            """, unsafe_allow_html=True)

        # Live test
        st.markdown('<div class="section-title">Live Test</div>',
                    unsafe_allow_html=True)
        test_task = st.selectbox("Task", list(TASK_ROUTING.keys()),
                                 label_visibility="collapsed", key="tt")
        test_mode = st.selectbox("Mode", ["default","fast","cheap","premium"],
                                 label_visibility="collapsed", key="tm")
        test_prompt = st.text_input("Prompt", value="Generate a warm birthday wish for Rakib.",
                                    label_visibility="collapsed", key="tp")
        if st.button("⚡ Generate", type="primary", use_container_width=True):
            with st.spinner("Calling API..."):
                r = generate(test_prompt, task=test_task, mode=test_mode,
                             max_tokens=150)
            st.code(f"Model   : {r['model_id']}\n"
                    f"Latency : {r['latency_ms']}ms\n"
                    f"Cost    : ${r['cost_usd']:.6f}\n"
                    f"Mock    : {r['mock']}\n\n"
                    f"{r['text']}")

    with right:
        # Task routing table
        st.markdown('<div class="section-title">Task Routing</div>',
                    unsafe_allow_html=True)
        sel_task = st.selectbox("View task", list(TASK_ROUTING.keys()),
                                label_visibility="collapsed", key="vt")
        comparison = compare_models_for_task(sel_task)
        for c in comparison:
            key_ok = not c["mock"]
            color  = "#3fb950" if key_ok else "#f85149"
            st.markdown(f"""
            <div class="usage-row">
              <div style="display:flex;justify-content:space-between">
                <div style="font-weight:700;font-family:'JetBrains Mono',monospace;
                            font-size:0.82rem">{c['model_id']}</div>
                <div style="font-size:0.72rem;color:{color};font-weight:700">
                  {'✅' if key_ok else '⚠'} ${c['cost_usd']:.5f}
                </div>
              </div>
              <div style="font-size:0.65rem;color:#8b949e;margin-top:2px">
                {c['speed']} · {c['tier']}
              </div>
            </div>
            """, unsafe_allow_html=True)

        # Usage stats
        st.markdown('<div class="section-title">Usage Stats (30d)</div>',
                    unsafe_allow_html=True)
        stats = get_usage_stats(30)
        st.markdown(f"""
        <div style="font-size:0.82rem;margin-bottom:8px">
          Total cost: <strong style="color:#3fb950">
            ${stats['total_cost_usd']:.4f}
          </strong> ·
          Total calls: <strong>{stats['total_calls']}</strong>
        </div>
        """, unsafe_allow_html=True)
        for m in stats["models"]:
            sr    = m["success_rate"]
            color = "#3fb950" if sr > 0.9 else "#d29922" if sr > 0.7 else "#f85149"
            st.markdown(f"""
            <div class="usage-row">
              <div style="display:flex;justify-content:space-between">
                <span style="font-family:'JetBrains Mono',monospace;
                             font-size:0.8rem">{m['model_id']}</span>
                <span style="color:#3fb950;font-family:'JetBrains Mono',monospace;
                             font-size:0.8rem">${m['cost_usd']:.4f}</span>
              </div>
              <div style="font-size:0.65rem;color:#8b949e;margin-top:2px">
                {m['calls']} calls · {m['avg_latency']}ms avg ·
                <span style="color:{color}">{sr:.0%} ok</span>
              </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">10.0</code></span>
      <span>Model Config</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    init_model_tables()
    print("=== Model Config -- self test ===\n")
    print(f"MODE: {MODE}\n")

    print("Model routing per task:")
    for task in TASK_ROUTING:
        cfg  = get_model(task)
        cost = estimate_cost(cfg["model_id"], 500, 150)
        mock = "⚠ mock" if cfg.get("mock") else "✅"
        print(f"  {task:<22} → {cfg['model_id']:<22} "
              f"${cost:.5f}  {mock}")

    print("\nLive generation test (mock if no API keys):")
    result = generate(
        "Write a 1-sentence birthday wish for Rakib, a Python developer.",
        task="wish_generation", mode="fast", max_tokens=60,
    )
    print(f"  model    : {result['model_id']}")
    print(f"  latency  : {result['latency_ms']}ms")
    print(f"  cost     : ${result['cost_usd']:.6f}")
    print(f"  mock     : {result['mock']}")
    print(f"  text     : {result['text'][:80]}")
else:
    render_dashboard()
