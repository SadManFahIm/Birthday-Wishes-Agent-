"""
theme_toggle.py
───────────────
Theme helper for Birthday Wishes Agent dashboards.

Adds a Dark/Light mode toggle to any Streamlit dashboard.

Usage:
    from theme_toggle import apply_theme, render_theme_toggle

    # At the top of any dashboard:
    apply_theme()
    render_theme_toggle()
"""

import streamlit as st


# ──────────────────────────────────────────────
# THEME DEFINITIONS
# ──────────────────────────────────────────────
THEMES = {
    "dark": {
        "name":        "🌙 Dark",
        "bg":          "#0E1117",
        "secondary_bg": "#1E2329",
        "text":        "#FAFAFA",
        "border":      "#2E3440",
        "primary":     "#4CAF50",
        "card_bg":     "#1E2329",
        "input_bg":    "#2E3440",
        "muted":       "#888888",
    },
    "light": {
        "name":        "☀️ Light",
        "bg":          "#FFFFFF",
        "secondary_bg": "#F5F5F5",
        "text":        "#1a1a1a",
        "border":      "#E0E0E0",
        "primary":     "#2E7D32",
        "card_bg":     "#FFFFFF",
        "input_bg":    "#F5F5F5",
        "muted":       "#666666",
    },
}


# ──────────────────────────────────────────────
# APPLY THEME
# ──────────────────────────────────────────────
def apply_theme():
    """
    Apply the current theme based on session state.
    Call this at the top of every dashboard page.
    """
    if "theme" not in st.session_state:
        st.session_state.theme = "dark"

    theme = THEMES[st.session_state.theme]

    st.markdown(f"""
    <style>
      /* Main background */
      .stApp {{
        background-color: {theme['bg']};
        color: {theme['text']};
      }}

      /* Sidebar */
      [data-testid="stSidebar"] {{
        background-color: {theme['secondary_bg']};
        border-right: 1px solid {theme['border']};
      }}

      /* Cards and containers */
      [data-testid="stContainer"] {{
        background-color: {theme['card_bg']};
      }}

      /* Metrics */
      [data-testid="metric-container"] {{
        background-color: {theme['secondary_bg']};
        border: 1px solid {theme['border']};
        border-radius: 12px;
        padding: 1rem;
      }}

      /* Text inputs */
      .stTextInput > div > div > input,
      .stTextArea > div > div > textarea {{
        background-color: {theme['input_bg']};
        color: {theme['text']};
        border-color: {theme['border']};
      }}

      /* Buttons */
      .stButton > button {{
        border-radius: 10px;
        font-weight: 600;
      }}

      /* Expanders */
      [data-testid="stExpander"] {{
        background-color: {theme['secondary_bg']};
        border: 1px solid {theme['border']};
        border-radius: 10px;
      }}

      /* Dividers */
      hr {{
        border-color: {theme['border']};
      }}

      /* Captions */
      .stCaption {{
        color: {theme['muted']};
      }}

      /* Select boxes */
      .stSelectbox > div > div {{
        background-color: {theme['input_bg']};
        color: {theme['text']};
      }}

      /* Tabs */
      .stTabs [data-baseweb="tab"] {{
        background-color: {theme['secondary_bg']};
        color: {theme['text']};
        border-radius: 8px 8px 0 0;
      }}
      .stTabs [aria-selected="true"] {{
        background-color: {theme['primary']};
        color: white;
      }}
    </style>
    """, unsafe_allow_html=True)


# ──────────────────────────────────────────────
# RENDER TOGGLE BUTTON
# ──────────────────────────────────────────────
def render_theme_toggle(location: str = "sidebar"):
    """
    Render a Dark/Light mode toggle button.

    Args:
        location : "sidebar" or "header"
    """
    if "theme" not in st.session_state:
        st.session_state.theme = "dark"

    current = st.session_state.theme
    other   = "light" if current == "dark" else "dark"
    label   = THEMES[other]["name"]

    if location == "sidebar":
        with st.sidebar:
            if st.button(label, use_container_width=True, key="theme_toggle"):
                st.session_state.theme = other
                st.rerun()
    else:
        col = st.columns([6, 1])[1]
        with col:
            if st.button(label, key="theme_toggle_header"):
                st.session_state.theme = other
                st.rerun()


# ──────────────────────────────────────────────
# GET CURRENT THEME COLORS
# ──────────────────────────────────────────────
def get_theme() -> dict:
    """Get the current theme color dict."""
    if "theme" not in st.session_state:
        st.session_state.theme = "dark"
    return THEMES[st.session_state.theme]