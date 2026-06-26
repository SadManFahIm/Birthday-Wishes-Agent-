"""
Conditional Workflow Builder — Dashboard (Birthday Wishes Agent v8.0)
Visual IF-THEN-ELSE workflow builder. Create, edit, test, and manage
automation rules entirely from the dashboard — no code changes needed.
"""

import streamlit as st
import json
import uuid
from datetime import datetime

from workflow_builder import (
    TRIGGERS, CONDITIONS, ACTIONS,
    load_all_workflows, save_workflow, delete_workflow, toggle_workflow,
    run_workflow, get_run_log,
    init_workflow_tables, seed_builtin_workflows,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Workflow Builder",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

:root {
    --bg:#0d1117; --surface:#161b22; --border:#30363d;
    --accent:#f78166; --green:#3fb950; --yellow:#d29922;
    --red:#f85149; --blue:#58a6ff; --muted:#8b949e; --text:#e6edf3;
    --purple:#bc8cff;
}
.stApp { background: var(--bg); color: var(--text); }

.cc-header {
    display:flex; align-items:center; gap:14px;
    padding:18px 0 10px; border-bottom:1px solid var(--border); margin-bottom:24px;
}
.cc-header h1 { font-size:1.4rem; font-weight:700; letter-spacing:-0.02em; margin:0; }
.cc-badge {
    background:var(--accent); color:#fff; font-size:0.65rem; font-weight:700;
    padding:2px 8px; border-radius:20px; letter-spacing:0.08em; text-transform:uppercase;
}
.cc-version { margin-left:auto; font-size:0.75rem; color:var(--muted); font-family:'JetBrains Mono',monospace; }

.section-title {
    font-size:0.7rem; font-weight:700; text-transform:uppercase; letter-spacing:0.1em;
    color:var(--muted); margin:22px 0 10px; display:flex; align-items:center; gap:8px;
}
.section-title::after { content:''; flex:1; height:1px; background:var(--border); }

/* Workflow card */
.wf-card {
    background:var(--surface); border:1px solid var(--border); border-radius:12px;
    padding:16px 18px; margin-bottom:10px; transition:border-color 0.15s;
}
.wf-card:hover { border-color:#58a6ff44; }
.wf-card.active { border-left:3px solid var(--green); }
.wf-card.disabled { opacity:0.55; border-left:3px solid var(--border); }

.wf-title { font-size:0.92rem; font-weight:700; display:flex; align-items:center; gap:8px; }
.wf-desc  { font-size:0.75rem; color:var(--muted); margin-top:3px; }
.wf-meta  { font-size:0.68rem; color:var(--muted); margin-top:8px; font-family:'JetBrains Mono',monospace; }

/* Flow visualizer */
.flow-block {
    background:#0d1117; border:1px solid var(--border); border-radius:8px;
    padding:10px 14px; margin-bottom:6px; font-size:0.78rem;
}
.flow-trigger  { border-left:3px solid var(--blue); }
.flow-cond     { border-left:3px solid var(--yellow); margin-left:16px; }
.flow-action   { border-left:3px solid var(--green); margin-left:16px; }
.flow-else     { border-left:3px solid var(--red);   margin-left:16px; }
.flow-label    { font-size:0.62rem; font-weight:700; text-transform:uppercase;
                 letter-spacing:0.08em; margin-bottom:3px; }
.flow-label.trig { color:var(--blue); }
.flow-label.cond { color:var(--yellow); }
.flow-label.act  { color:var(--green); }
.flow-label.els  { color:var(--red); }

.arrow { text-align:center; color:var(--muted); font-size:0.8rem; margin:2px 0 2px 16px; }

/* Status chips */
.chip {
    display:inline-flex; align-items:center; gap:4px; font-size:0.68rem;
    font-weight:700; padding:2px 8px; border-radius:20px;
    text-transform:uppercase; letter-spacing:0.06em;
}
.chip-on  { background:#051a09; color:var(--green);  border:1px solid var(--green); }
.chip-off { background:#21262d; color:var(--muted);  border:1px solid var(--border); }
.chip-dry { background:#1a1500; color:var(--yellow); border:1px solid var(--yellow); }

/* Log terminal */
.log-terminal {
    background:#010409; border:1px solid var(--border); border-radius:10px;
    padding:12px 14px; font-family:'JetBrains Mono',monospace; font-size:0.72rem;
    max-height:220px; overflow-y:auto; color:#7ee787; line-height:1.6;
}
.log-error { color:var(--red); }
.log-warn  { color:var(--yellow); }
.log-info  { color:var(--blue); }

/* Streamlit overrides */
div[data-testid="stButton"] > button {
    background:var(--surface); border:1px solid var(--border); color:var(--text);
    border-radius:8px; font-size:0.8rem; font-weight:500; transition:all 0.15s;
}
div[data-testid="stButton"] > button:hover { border-color:var(--blue); background:#1c2128; }
div[data-testid="stButton"] > button[kind="primary"] {
    background:var(--accent); border-color:var(--accent); color:#fff;
}
div[data-testid="stButton"] > button[kind="primary"]:hover { background:#e56d55; }
div[data-testid="stTextInput"] input,
div[data-testid="stSelectbox"] > div,
div[data-testid="stNumberInput"] input {
    background:var(--surface) !important; border-color:var(--border) !important; color:var(--text) !important;
}
textarea { background:#0d1117 !important; color:#e6edf3 !important; border-color:var(--border) !important; }
::-webkit-scrollbar { width:6px; } ::-webkit-scrollbar-track { background:var(--bg); }
::-webkit-scrollbar-thumb { background:var(--border); border-radius:3px; }
</style>
""", unsafe_allow_html=True)

# ── Init ──────────────────────────────────────────────────────────────────────
init_workflow_tables()
seed_builtin_workflows()

def _init_state():
    defaults = {
        "view":          "list",      # list | create | edit | test
        "edit_wf":       None,
        "test_results":  None,
        "dry_run":       True,
        "new_wf": {
            "name": "", "description": "",
            "trigger": {"event": list(TRIGGERS.keys())[0], "platform": "all", "conditions": []},
            "actions": [], "else_actions": [], "enabled": True,
        },
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ── Helpers ───────────────────────────────────────────────────────────────────

def render_flow_visual(workflow: dict):
    """Render a compact visual flow of trigger → conditions → actions."""
    trigger = workflow.get("trigger", {})
    event   = trigger.get("event", "?")
    conds   = trigger.get("conditions", [])
    acts    = workflow.get("actions", [])
    elses   = workflow.get("else_actions", [])

    st.markdown(f"""
    <div class="flow-block flow-trigger">
      <div class="flow-label trig">⚡ Trigger</div>
      {TRIGGERS.get(event, event)}
    </div>
    """, unsafe_allow_html=True)

    for c in conds:
        cdef  = CONDITIONS.get(c.get("type",""), {})
        label = cdef.get("label", c.get("type",""))
        param = json.dumps(c.get("params", {})).strip("{}")
        st.markdown(f"""
        <div class="arrow">↓ if</div>
        <div class="flow-block flow-cond">
          <div class="flow-label cond">🔍 Condition</div>
          {label} {param}
        </div>
        """, unsafe_allow_html=True)

    if acts:
        st.markdown('<div class="arrow">↓ then</div>', unsafe_allow_html=True)
        for a in acts:
            alabel = ACTIONS.get(a.get("type",""), {}).get("label", a.get("type",""))
            st.markdown(f"""
            <div class="flow-block flow-action">
              <div class="flow-label act">✅ Action</div>
              {alabel}
            </div>
            """, unsafe_allow_html=True)

    if elses:
        st.markdown('<div class="arrow">↓ else</div>', unsafe_allow_html=True)
        for e in elses:
            elabel = ACTIONS.get(e.get("type",""), {}).get("label", e.get("type",""))
            st.markdown(f"""
            <div class="flow-block flow-else">
              <div class="flow-label els">↩ Else</div>
              {elabel}
            </div>
            """, unsafe_allow_html=True)


def render_workflow_builder_form(wf: dict, key_prefix: str = "new") -> dict:
    """Render the step-by-step form to build/edit a workflow. Returns updated wf dict."""

    wf["name"] = st.text_input("Workflow name", value=wf.get("name",""),
                                placeholder="e.g. Smart Follow-up Chain", key=f"{key_prefix}_name")
    wf["description"] = st.text_input("Description (optional)", value=wf.get("description",""),
                                       placeholder="What does this workflow do?", key=f"{key_prefix}_desc")

    # ── Step 1: Trigger ───────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Step 1 — Trigger</div>', unsafe_allow_html=True)
    trigger_keys   = list(TRIGGERS.keys())
    trigger_labels = [TRIGGERS[k] for k in trigger_keys]
    cur_trigger    = wf.get("trigger", {}).get("event", trigger_keys[0])
    t_idx          = trigger_keys.index(cur_trigger) if cur_trigger in trigger_keys else 0
    chosen_trigger = st.selectbox("When does this run?", trigger_labels, index=t_idx, key=f"{key_prefix}_trigger")
    trigger_event  = trigger_keys[trigger_labels.index(chosen_trigger)]
    if "trigger" not in wf:
        wf["trigger"] = {}
    wf["trigger"]["event"] = trigger_event

    # ── Step 2: Conditions ────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Step 2 — Conditions (all must be true)</div>', unsafe_allow_html=True)
    cond_keys   = list(CONDITIONS.keys())
    cond_labels = [CONDITIONS[k]["label"] for k in cond_keys]

    existing_conds = wf["trigger"].get("conditions", [])

    if st.button("➕ Add condition", key=f"{key_prefix}_add_cond"):
        existing_conds.append({"type": cond_keys[0], "params": {}})
    wf["trigger"]["conditions"] = existing_conds

    updated_conds = []
    for ci, cond in enumerate(existing_conds):
        with st.container():
            cc1, cc2, cc3 = st.columns([2, 2, 0.4])
            with cc1:
                cur_ci   = cond_keys.index(cond.get("type","")) if cond.get("type","") in cond_keys else 0
                new_type = st.selectbox("Condition", cond_labels, index=cur_ci, key=f"{key_prefix}_ctype_{ci}", label_visibility="collapsed")
                cond_key = cond_keys[cond_labels.index(new_type)]
                cdef     = CONDITIONS[cond_key]
            with cc2:
                param_val = cond.get("params", {})
                if cdef["type"] == "number":
                    v = st.number_input("Value", value=int(param_val.get(cdef["param"], 3)),
                                        min_value=0, key=f"{key_prefix}_cparam_{ci}", label_visibility="collapsed")
                    param_val = {cdef["param"]: v}
                elif cdef["type"] == "select":
                    opts = cdef.get("options", [])
                    cur  = param_val.get(cdef["param"], opts[0]) if opts else ""
                    idx  = opts.index(cur) if cur in opts else 0
                    sel  = st.selectbox("Value", opts, index=idx, key=f"{key_prefix}_csel_{ci}", label_visibility="collapsed")
                    param_val = {cdef["param"]: sel}
                else:
                    v = st.text_input("Value", value=param_val.get(cdef["param"],""),
                                      key=f"{key_prefix}_ctxt_{ci}", label_visibility="collapsed")
                    param_val = {cdef["param"]: v}
            with cc3:
                if st.button("✕", key=f"{key_prefix}_del_cond_{ci}", use_container_width=True):
                    continue  # skip this condition (delete)
            updated_conds.append({"type": cond_key, "params": param_val})
    wf["trigger"]["conditions"] = updated_conds

    # ── Step 3: THEN actions ──────────────────────────────────────────────────
    st.markdown('<div class="section-title">Step 3 — Then do this</div>', unsafe_allow_html=True)
    act_keys   = list(ACTIONS.keys())
    act_labels = [ACTIONS[k]["label"] for k in act_keys]

    existing_acts = wf.get("actions", [])
    if st.button("➕ Add action", key=f"{key_prefix}_add_act"):
        existing_acts.append({"type": act_keys[0], "params": dict(ACTIONS[act_keys[0]]["params"])})
    wf["actions"] = existing_acts

    updated_acts = []
    for ai, act in enumerate(existing_acts):
        ac1, ac2 = st.columns([3, 0.4])
        with ac1:
            cur_ai   = act_keys.index(act.get("type","")) if act.get("type","") in act_keys else 0
            new_atype= st.selectbox("Action", act_labels, index=cur_ai,
                                    key=f"{key_prefix}_atype_{ai}", label_visibility="collapsed")
            act_key  = act_keys[act_labels.index(new_atype)]
        with ac2:
            if st.button("✕", key=f"{key_prefix}_del_act_{ai}", use_container_width=True):
                continue
        updated_acts.append({"type": act_key, "params": dict(ACTIONS[act_key]["params"])})
    wf["actions"] = updated_acts

    # ── Step 4: ELSE actions ──────────────────────────────────────────────────
    st.markdown('<div class="section-title">Step 4 — Else do this (optional)</div>', unsafe_allow_html=True)
    existing_else = wf.get("else_actions", [])
    if st.button("➕ Add else action", key=f"{key_prefix}_add_else"):
        existing_else.append({"type": act_keys[-1], "params": {}})
    wf["else_actions"] = existing_else

    updated_else = []
    for ei, ea in enumerate(existing_else):
        ec1, ec2 = st.columns([3, 0.4])
        with ec1:
            cur_ei   = act_keys.index(ea.get("type","")) if ea.get("type","") in act_keys else 0
            new_etype= st.selectbox("Else action", act_labels, index=cur_ei,
                                    key=f"{key_prefix}_etype_{ei}", label_visibility="collapsed")
            else_key = act_keys[act_labels.index(new_etype)]
        with ec2:
            if st.button("✕", key=f"{key_prefix}_del_else_{ei}", use_container_width=True):
                continue
        updated_else.append({"type": else_key, "params": dict(ACTIONS[else_key]["params"])})
    wf["else_actions"] = updated_else

    return wf


# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="cc-header">
  <span style="font-size:1.6rem">⚡</span>
  <h1>Conditional Workflow Builder</h1>
  <span class="cc-badge">v8.0</span>
  <span class="cc-version">Birthday Wishes Agent</span>
</div>
""", unsafe_allow_html=True)

# ── Top controls ──────────────────────────────────────────────────────────────
tc1, tc2, tc3, tc4 = st.columns([2, 1, 1, 1])
with tc1:
    dry = st.toggle("🧪 Dry Run Mode", value=st.session_state.dry_run)
    st.session_state.dry_run = dry
    mode_html = '<span class="chip chip-dry">● Dry Run</span>' if dry else '<span class="chip chip-on">● Live</span>'
    st.markdown(mode_html, unsafe_allow_html=True)
with tc2:
    if st.button("➕ New Workflow", type="primary", use_container_width=True):
        st.session_state.view = "create"
        st.session_state.new_wf = {
            "name":"","description":"",
            "trigger":{"event":list(TRIGGERS.keys())[0],"platform":"all","conditions":[]},
            "actions":[],"else_actions":[],"enabled":True,
        }
        st.rerun()
with tc3:
    if st.button("📋 All Workflows", use_container_width=True):
        st.session_state.view = "list"
        st.rerun()
with tc4:
    if st.button("📜 Run Log", use_container_width=True):
        st.session_state.view = "log"
        st.rerun()

st.markdown("---")

# ─────────────────────────────────────────────────────────────────────────────
# VIEW: LIST
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.view == "list":
    workflows = load_all_workflows()
    left, right = st.columns([1.4, 1], gap="large")

    with left:
        st.markdown(f'<div class="section-title">Workflows ({len(workflows)})</div>', unsafe_allow_html=True)
        if not workflows:
            st.info("No workflows yet. Click **New Workflow** to create one.")

        for wf in workflows:
            card_cls = "wf-card active" if wf["enabled"] else "wf-card disabled"
            status   = "✅ Active" if wf["enabled"] else "⏸ Paused"
            acts_n   = len(wf["actions"])
            else_n   = len(wf["else_actions"])
            last_run = wf.get("last_run","Never") or "Never"
            if last_run != "Never":
                last_run = last_run[:16].replace("T"," ")

            st.markdown(f"""
            <div class="{card_cls}">
              <div class="wf-title">
                {wf['name']}
              </div>
              <div class="wf-desc">{wf.get('description','')}</div>
              <div class="wf-meta">
                Trigger: {TRIGGERS.get(wf['trigger'].get('event',''),'?')[:40]} ·
                {acts_n} action{'s' if acts_n!=1 else ''} + {else_n} else ·
                Runs: {wf['run_count']} · Last: {last_run}
              </div>
            </div>
            """, unsafe_allow_html=True)

            btn1, btn2, btn3, btn4, btn5 = st.columns(5)
            with btn1:
                tog_label = "⏸ Pause" if wf["enabled"] else "▶ Enable"
                if st.button(tog_label, key=f"tog_{wf['id']}", use_container_width=True):
                    toggle_workflow(wf["id"], not wf["enabled"])
                    st.rerun()
            with btn2:
                if st.button("✏️ Edit", key=f"edit_{wf['id']}", use_container_width=True):
                    st.session_state.view    = "edit"
                    st.session_state.edit_wf = wf
                    st.rerun()
            with btn3:
                if st.button("▶ Test", key=f"test_{wf['id']}", use_container_width=True):
                    st.session_state.view    = "test"
                    st.session_state.edit_wf = wf
                    st.rerun()
            with btn4:
                if st.button("👁 View", key=f"view_{wf['id']}", use_container_width=True):
                    st.session_state.view    = "view_single"
                    st.session_state.edit_wf = wf
                    st.rerun()
            with btn5:
                if st.button("🗑", key=f"del_{wf['id']}", use_container_width=True,
                             help="Delete this workflow"):
                    delete_workflow(wf["id"])
                    st.rerun()

    with right:
        st.markdown('<div class="section-title">Quick Stats</div>', unsafe_allow_html=True)
        active  = sum(1 for w in workflows if w["enabled"])
        paused  = len(workflows) - active
        total_runs = sum(w["run_count"] for w in workflows)

        mc1, mc2, mc3 = st.columns(3)
        for col, label, val, color in [
            (mc1, "Active",     active,     "#3fb950"),
            (mc2, "Paused",     paused,     "#8b949e"),
            (mc3, "Total Runs", total_runs, "#58a6ff"),
        ]:
            with col:
                st.markdown(f"""
                <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;
                            padding:14px;text-align:center;">
                  <div style="font-size:0.65rem;color:#8b949e;text-transform:uppercase;
                              letter-spacing:0.08em">{label}</div>
                  <div style="font-size:1.6rem;font-weight:700;color:{color}">{val}</div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown('<div class="section-title" style="margin-top:20px">Available Triggers</div>', unsafe_allow_html=True)
        for key, label in TRIGGERS.items():
            st.markdown(f'<div style="font-size:0.75rem;padding:4px 0;color:#c9d1d9;">⚡ {label}</div>', unsafe_allow_html=True)

        st.markdown('<div class="section-title">Available Actions</div>', unsafe_allow_html=True)
        for key, meta in ACTIONS.items():
            st.markdown(f'<div style="font-size:0.75rem;padding:4px 0;color:#c9d1d9;">✅ {meta["label"]}</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# VIEW: CREATE
# ─────────────────────────────────────────────────────────────────────────────
elif st.session_state.view == "create":
    form_col, preview_col = st.columns([1.5, 1], gap="large")

    with form_col:
        st.markdown('<div class="section-title">Build New Workflow</div>', unsafe_allow_html=True)
        st.session_state.new_wf = render_workflow_builder_form(st.session_state.new_wf, key_prefix="new")

        st.markdown("<br>", unsafe_allow_html=True)
        s1, s2 = st.columns(2)
        with s1:
            if st.button("💾 Save Workflow", type="primary", use_container_width=True):
                wf = st.session_state.new_wf
                if not wf.get("name","").strip():
                    st.error("Give the workflow a name first.")
                elif not wf.get("actions"):
                    st.error("Add at least one action.")
                else:
                    wf["id"] = str(uuid.uuid4())
                    wf["created_at"] = datetime.now().isoformat()
                    save_workflow(wf)
                    st.success(f"Workflow \"{wf['name']}\" saved! ✅")
                    st.session_state.view = "list"
                    st.rerun()
        with s2:
            if st.button("✕ Cancel", use_container_width=True):
                st.session_state.view = "list"
                st.rerun()

    with preview_col:
        st.markdown('<div class="section-title">Live Preview</div>', unsafe_allow_html=True)
        if st.session_state.new_wf.get("name") or st.session_state.new_wf.get("actions"):
            render_flow_visual(st.session_state.new_wf)
        else:
            st.markdown('<div style="color:#8b949e;font-size:0.8rem;padding:20px 0">Fill in the form to see the flow preview here.</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# VIEW: EDIT
# ─────────────────────────────────────────────────────────────────────────────
elif st.session_state.view == "edit" and st.session_state.edit_wf:
    wf = st.session_state.edit_wf
    form_col, preview_col = st.columns([1.5, 1], gap="large")

    with form_col:
        st.markdown(f'<div class="section-title">Editing: {wf["name"]}</div>', unsafe_allow_html=True)
        updated = render_workflow_builder_form(wf, key_prefix="edit")
        st.session_state.edit_wf = updated
        st.markdown("<br>", unsafe_allow_html=True)
        s1, s2 = st.columns(2)
        with s1:
            if st.button("💾 Save Changes", type="primary", use_container_width=True):
                save_workflow(updated)
                st.success("Changes saved! ✅")
                st.session_state.view = "list"
                st.rerun()
        with s2:
            if st.button("✕ Cancel", use_container_width=True):
                st.session_state.view = "list"
                st.rerun()

    with preview_col:
        st.markdown('<div class="section-title">Live Preview</div>', unsafe_allow_html=True)
        render_flow_visual(updated)

# ─────────────────────────────────────────────────────────────────────────────
# VIEW: VIEW SINGLE
# ─────────────────────────────────────────────────────────────────────────────
elif st.session_state.view == "view_single" and st.session_state.edit_wf:
    wf = st.session_state.edit_wf
    st.markdown(f'<div class="section-title">{wf["name"]}</div>', unsafe_allow_html=True)
    v1, v2 = st.columns([1, 1.5], gap="large")
    with v1:
        render_flow_visual(wf)
    with v2:
        log_entries = get_run_log(wf["id"], limit=20)
        st.markdown('<div class="section-title">Run History</div>', unsafe_allow_html=True)
        if not log_entries:
            st.caption("No runs yet.")
        else:
            lines = []
            for e in log_entries:
                ts = (e.get("ran_at","")[:16]).replace("T"," ")
                contact = e.get("contact_name","Unknown")
                result  = e.get("result","?")
                lines.append(f'<span class="log-info">[{ts}] {contact} → {result}</span>')
                for a in e.get("actions_taken",[]):
                    lines.append(f'<span style="color:#8b949e">  {a[:80]}</span>')
            st.markdown(f'<div class="log-terminal">{"<br>".join(lines)}</div>', unsafe_allow_html=True)
    if st.button("← Back"):
        st.session_state.view = "list"
        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# VIEW: TEST
# ─────────────────────────────────────────────────────────────────────────────
elif st.session_state.view == "test" and st.session_state.edit_wf:
    wf = st.session_state.edit_wf
    st.markdown(f'<div class="section-title">Test: {wf["name"]}</div>', unsafe_allow_html=True)

    t1, t2 = st.columns([1.2, 1], gap="large")
    with t1:
        st.markdown("**Simulated context**")
        ctx_platform    = st.selectbox("Platform", ["LinkedIn","WhatsApp","Facebook","Instagram","Twitter/X","Slack"])
        ctx_days_wish   = st.number_input("Days since wish sent", min_value=0, value=4)
        ctx_days_reply  = st.number_input("Days since last reply", min_value=0, value=4)
        ctx_rel         = st.selectbox("Relationship type", ["Close Friend","Colleague","Acquaintance"])
        ctx_score       = st.number_input("Personalization score", min_value=0, max_value=10, value=5)
        ctx_decay       = st.number_input("Days without interaction", min_value=0, value=65)
        ctx_tags        = st.text_input("Contact tags (comma-separated)", value="")
        ctx_sentiment   = st.selectbox("Reply sentiment", ["positive","neutral","negative","sad","stressed"])
        ctx_contact     = st.text_input("Contact name (for log)", value="Test Contact")

        test_context = {
            "contact_id":       "test_001",
            "contact_name":     ctx_contact,
            "platform":         ctx_platform,
            "days_since_wish":  ctx_days_wish,
            "days_since_reply": ctx_days_reply,
            "relationship_type":ctx_rel,
            "wish_score":       ctx_score,
            "decay_days":       ctx_decay,
            "tags":             [t.strip() for t in ctx_tags.split(",") if t.strip()],
            "reply_sentiment":  ctx_sentiment,
        }

        mode_label = "🧪 Run (Dry)" if st.session_state.dry_run else "▶ Run (Live)"
        if st.button(mode_label, type="primary", use_container_width=True):
            result = run_workflow(wf, test_context, dry_run=st.session_state.dry_run)
            st.session_state.test_results = result
            st.rerun()

        if st.button("← Back to list", use_container_width=True):
            st.session_state.view = "list"
            st.session_state.test_results = None
            st.rerun()

    with t2:
        st.markdown('<div class="section-title">Flow</div>', unsafe_allow_html=True)
        render_flow_visual(wf)

        if st.session_state.test_results:
            r = st.session_state.test_results
            st.markdown('<div class="section-title">Result</div>', unsafe_allow_html=True)
            branch_color = "#3fb950" if r["branch"] == "actions" else "#f85149"
            st.markdown(f"""
            <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:14px;">
              <div style="font-size:0.7rem;color:#8b949e;text-transform:uppercase;letter-spacing:0.08em">Branch taken</div>
              <div style="font-size:1rem;font-weight:700;color:{branch_color};margin:4px 0">
                {"✅ THEN" if r["branch"]=="actions" else "↩ ELSE"}
              </div>
              <div style="font-size:0.75rem;color:#8b949e">
                {"DRY RUN — no real actions taken" if r.get("dry_run") else "LIVE — actions executed"}
              </div>
            </div>
            """, unsafe_allow_html=True)

            if r["actions_taken"]:
                lines = [f'<span class="log-info">{a}</span>' for a in r["actions_taken"]]
                st.markdown(f'<div class="log-terminal" style="margin-top:10px">{"<br>".join(lines)}</div>',
                            unsafe_allow_html=True)
            else:
                st.caption("No actions in selected branch.")

# ─────────────────────────────────────────────────────────────────────────────
# VIEW: LOG
# ─────────────────────────────────────────────────────────────────────────────
elif st.session_state.view == "log":
    st.markdown('<div class="section-title">Workflow Run Log</div>', unsafe_allow_html=True)
    log_entries = get_run_log(limit=100)
    if not log_entries:
        st.info("No workflow runs yet. Test a workflow to see logs here.")
    else:
        lines = []
        for e in log_entries:
            ts      = (e.get("ran_at","")[:16]).replace("T"," ")
            wid     = e.get("workflow_id","")[:8]
            contact = e.get("contact_name","?")
            result  = e.get("result","?")
            color   = "#3fb950" if result == "ok" else "#f85149"
            lines.append(f'<span style="color:{color}">[{ts}] [{wid}…] {contact} → {result}</span>')
            for a in e.get("actions_taken",[]):
                lines.append(f'<span style="color:#8b949e">  {a[:100]}</span>')
        st.markdown(f'<div class="log-terminal">{"<br>".join(lines)}</div>', unsafe_allow_html=True)
    if st.button("← Back"):
        st.session_state.view = "list"
        st.rerun()

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(f"""
<div style="display:flex;justify-content:space-between;font-size:0.7rem;color:#8b949e;padding:4px 0 10px;">
  <span>Birthday Wishes Agent · branch <code style="background:#161b22;padding:1px 5px;border-radius:4px">8.0</code></span>
  <span>Conditional Workflow Builder</span>
  <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
</div>
""", unsafe_allow_html=True)
