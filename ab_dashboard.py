"""
ab_dashboard.py
───────────────
A/B Testing Dashboard for Birthday Wishes Agent.

Run with:
    streamlit run ab_dashboard.py

Shows:
  - Live A/B test results
  - Reply rates for Variant A vs B
  - Winner declaration
  - Recent sends table
"""

import sqlite3
from pathlib import Path
import streamlit as st
from ab_testing import get_ab_results, get_recent_ab_sends, AB_VARIANTS

st.set_page_config(
    page_title="A/B Wish Testing",
    page_icon="🧪",
    layout="wide",
)

st.title("🧪 Wish A/B Testing Dashboard")
st.caption("Track which wish style gets more replies.")
st.divider()

results = get_ab_results()
a       = results["variant_a"]
b       = results["variant_b"]
winner  = results["winner"]

# ── WINNER BANNER ──────────────────────────
if winner:
    st.success(
        f"🏆 **Winner: Variant {winner}** — "
        f"{AB_VARIANTS[winner]['name']} style! "
        f"Agent is now using this for all wishes."
    )
elif results["total_sends"] > 0:
    st.info(f"⏳ Test in progress — {results['conclusion_note']}")
else:
    st.info("📭 No test data yet. Run the agent with `AB_TESTING_ENABLED = True`.")

st.divider()

# ── METRICS ───────────────────────────────
col_a, col_b = st.columns(2)

with col_a:
    color_a = "#4CAF50" if winner == "A" else "#2196F3"
    st.markdown(
        f"<h3 style='color:{color_a};'>🅰️ Variant A — {a['name']}</h3>",
        unsafe_allow_html=True,
    )
    st.caption(AB_VARIANTS["A"]["description"])
    st.markdown(f"> *{AB_VARIANTS['A']['example']}*")
    m1, m2, m3 = st.columns(3)
    m1.metric("📤 Sends",      a["sends"])
    m2.metric("💬 Replies",    a["replies"])
    m3.metric("📊 Reply Rate", f"{a['reply_rate']}%")
    if a["sends"] > 0:
        st.progress(
            min(100, int(a["reply_rate"])),
            text=f"Reply rate: {a['reply_rate']}%",
        )

with col_b:
    color_b = "#4CAF50" if winner == "B" else "#FF9800"
    st.markdown(
        f"<h3 style='color:{color_b};'>🅱️ Variant B — {b['name']}</h3>",
        unsafe_allow_html=True,
    )
    st.caption(AB_VARIANTS["B"]["description"])
    st.markdown(f"> *{AB_VARIANTS['B']['example']}*")
    m1, m2, m3 = st.columns(3)
    m1.metric("📤 Sends",      b["sends"])
    m2.metric("💬 Replies",    b["replies"])
    m3.metric("📊 Reply Rate", f"{b['reply_rate']}%")
    if b["sends"] > 0:
        st.progress(
            min(100, int(b["reply_rate"])),
            text=f"Reply rate: {b['reply_rate']}%",
        )

st.divider()

# ── CONCLUSION NOTE ────────────────────────
st.subheader("📋 Test Status")
st.write(results["conclusion_note"])
st.caption(
    f"Minimum sends required for winner: {results['min_for_winner']} per variant | "
    f"Total sends: {results['total_sends']}"
)

st.divider()

# ── RECENT SENDS TABLE ────────────────────
st.subheader("🕐 Recent Sends")
recent = get_recent_ab_sends(20)

if recent:
    for r in recent:
        replied_label = "✅ Replied" if r["replied"] else "⏳ No reply yet"
        variant_color = "#2196F3" if r["variant"] == "A" else "#FF9800"
        with st.expander(
            f"{'🅰️' if r['variant'] == 'A' else '🅱️'} "
            f"{r['contact']} — {r['date']} — {replied_label}"
        ):
            st.markdown(
                f"**Variant {r['variant']}** "
                f"({AB_VARIANTS[r['variant']]['name']})"
            )
            st.write(r["wish_text"])
else:
    st.info("No sends recorded yet.")

st.divider()
st.caption("🎂 Birthday Wishes Agent v5.0 — A/B Testing Dashboard")