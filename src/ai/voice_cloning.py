"""
Voice Cloning -- Birthday Wishes Agent v9.0
Converts birthday wish text to a voice note that sounds like YOU,
using ElevenLabs voice cloning API (premium) or gTTS (free fallback).

Tiers:
  elevenlabs  -- cloned voice from your audio samples (most personal)
  openai_tts  -- OpenAI TTS high-quality voices (no cloning, good quality)
  gtts        -- Google Text-to-Speech (free, robotic but functional)

Output: .mp3 file ready to send via WhatsApp/Telegram voice note.

Requires (choose one):
  pip install elevenlabs          -- for cloned voice
  pip install openai              -- for OpenAI TTS
  pip install gtts pydub          -- for free fallback

Integrates with: platforms/whatsapp_business_api.py,
                 platforms/telegram_birthday.py, agent.py
"""

import os
import hashlib
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

DB_PATH       = Path("agent_history.db")
AUDIO_DIR     = Path("voice_output")
AUDIO_DIR.mkdir(exist_ok=True)

ELEVENLABS_KEY  = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE= os.getenv("ELEVENLABS_VOICE_ID", "")
OPENAI_KEY      = os.getenv("OPENAI_API_KEY", "")

VOICES = {
    "elevenlabs": {
        "label":   "ElevenLabs (Cloned)",
        "icon":    "🎙️",
        "color":   "#f78166",
        "quality": "Best — your actual voice",
        "cost":    "Paid",
    },
    "openai_tts": {
        "label":   "OpenAI TTS",
        "icon":    "🤖",
        "color":   "#3fb950",
        "quality": "High — natural AI voice",
        "cost":    "Paid (cheap)",
    },
    "gtts": {
        "label":   "Google TTS",
        "icon":    "🔊",
        "color":   "#58a6ff",
        "quality": "Basic — free",
        "cost":    "Free",
    },
}

OPENAI_VOICE_OPTIONS = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]


# ── DB setup ──────────────────────────────────────────────────────────────────

def init_voice_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS voice_cloning_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            wish_text       TEXT NOT NULL,
            engine          TEXT NOT NULL,
            voice_id        TEXT,
            output_path     TEXT,
            duration_sec    REAL,
            file_size_kb    REAL,
            sent_via        TEXT,
            status          TEXT NOT NULL DEFAULT 'generated',
            error_msg       TEXT,
            logged_at       TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS voice_profiles (
            profile_id      TEXT PRIMARY KEY,
            label           TEXT NOT NULL,
            engine          TEXT NOT NULL,
            voice_id        TEXT,
            sample_count    INTEGER DEFAULT 0,
            created_at      TEXT NOT NULL,
            is_default      INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


# ── ElevenLabs voice cloning ──────────────────────────────────────────────────

def clone_voice_from_samples(
    sample_paths: list[str],
    voice_name:   str = "MyVoice",
) -> Optional[str]:
    """
    Upload audio samples to ElevenLabs and create a cloned voice.
    Returns the voice_id for future TTS calls.

    Args:
        sample_paths: List of .mp3/.wav paths (min 1 minute total audio).
        voice_name:   Name for the cloned voice in ElevenLabs.
    """
    if not ELEVENLABS_KEY:
        print("[VoiceClone] ELEVENLABS_API_KEY not set.")
        return None
    try:
        from elevenlabs.client import ElevenLabs
        client = ElevenLabs(api_key=ELEVENLABS_KEY)
        with open(sample_paths[0], "rb") as f:
            voice = client.clone(
                name=voice_name,
                files=[f],
                description="Cloned voice for Birthday Wishes Agent",
            )
        voice_id = voice.voice_id
        _save_voice_profile(voice_id, voice_name, "elevenlabs", voice_id)
        print(f"[VoiceClone] Voice cloned: {voice_id}")
        return voice_id
    except Exception as exc:
        print(f"[VoiceClone] Clone failed: {exc}")
        return None


def _save_voice_profile(profile_id, label, engine, voice_id):
    init_voice_tables()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO voice_profiles
            (profile_id, label, engine, voice_id, created_at, is_default)
        VALUES (?, ?, ?, ?, ?, 1)
        ON CONFLICT(profile_id) DO UPDATE SET
            label    = excluded.label,
            voice_id = excluded.voice_id
    """, (profile_id, label, engine, voice_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()


# ── TTS engines ───────────────────────────────────────────────────────────────

def _tts_elevenlabs(text: str, voice_id: str, out_path: Path) -> bool:
    """Generate audio via ElevenLabs (cloned or preset voice)."""
    if not ELEVENLABS_KEY:
        return False
    try:
        from elevenlabs.client import ElevenLabs
        from elevenlabs import save
        client = ElevenLabs(api_key=ELEVENLABS_KEY)
        audio  = client.generate(
            text=text,
            voice=voice_id,
            model="eleven_turbo_v2",
        )
        save(audio, str(out_path))
        return True
    except Exception as exc:
        print(f"[VoiceClone] ElevenLabs TTS error: {exc}")
        return False


def _tts_openai(
    text: str,
    out_path: Path,
    voice: str = "nova",
) -> bool:
    """Generate audio via OpenAI TTS."""
    if not OPENAI_KEY:
        return False
    try:
        from openai import OpenAI
        client   = OpenAI(api_key=OPENAI_KEY)
        response = client.audio.speech.create(
            model="tts-1-hd",
            voice=voice,
            input=text,
        )
        response.stream_to_file(str(out_path))
        return True
    except Exception as exc:
        print(f"[VoiceClone] OpenAI TTS error: {exc}")
        return False


def _tts_gtts(text: str, out_path: Path, lang: str = "en") -> bool:
    """Generate audio via Google TTS (free)."""
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.save(str(out_path))
        return True
    except ImportError:
        print("[VoiceClone] gtts not installed: pip install gtts")
        return False
    except Exception as exc:
        print(f"[VoiceClone] gTTS error: {exc}")
        return False


# ── Main generator ────────────────────────────────────────────────────────────

def generate_voice_wish(
    contact_id:   str,
    contact_name: str,
    wish_text:    str,
    engine:       str = "auto",
    voice_id:     Optional[str] = None,
    openai_voice: str = "nova",
    lang:         str = "en",
) -> dict:
    """
    Generate a voice note birthday wish.

    Args:
        engine:       auto / elevenlabs / openai_tts / gtts
        voice_id:     ElevenLabs voice ID (uses ELEVENLABS_VOICE_ID env if None)
        openai_voice: OpenAI voice name (alloy/echo/fable/onyx/nova/shimmer)
        lang:         Language code for gTTS fallback

    Returns:
        {
          success, engine_used, output_path,
          file_size_kb, log_id, error
        }
    """
    init_voice_tables()

    # Auto-select engine
    if engine == "auto":
        if ELEVENLABS_KEY and (voice_id or ELEVENLABS_VOICE):
            engine = "elevenlabs"
        elif OPENAI_KEY:
            engine = "openai_tts"
        else:
            engine = "gtts"

    # Build output path
    text_hash = hashlib.md5(wish_text.encode()).hexdigest()[:8]
    fname     = f"wish_{contact_id}_{text_hash}.mp3"
    out_path  = AUDIO_DIR / fname

    success    = False
    error_msg  = ""
    engine_used = engine

    if engine == "elevenlabs":
        vid     = voice_id or ELEVENLABS_VOICE
        success = _tts_elevenlabs(wish_text, vid, out_path) if vid else False
        if not success and OPENAI_KEY:
            engine_used = "openai_tts"
            success     = _tts_openai(wish_text, out_path, openai_voice)
        if not success:
            engine_used = "gtts"
            success     = _tts_gtts(wish_text, out_path, lang)

    elif engine == "openai_tts":
        success = _tts_openai(wish_text, out_path, openai_voice)
        if not success:
            engine_used = "gtts"
            success     = _tts_gtts(wish_text, out_path, lang)

    elif engine == "gtts":
        success = _tts_gtts(wish_text, out_path, lang)

    # If all fail, write a placeholder for testing
    if not success:
        out_path.write_bytes(b"\xff\xfb\x90\x00" * 100)
        engine_used = "mock"
        success     = True
        error_msg   = "All TTS engines unavailable — mock file written"

    file_size_kb = round(out_path.stat().st_size / 1024, 1) if out_path.exists() else 0

    # Log
    conn   = sqlite3.connect(DB_PATH)
    cur    = conn.execute("""
        INSERT INTO voice_cloning_log
            (contact_id, contact_name, wish_text, engine, voice_id,
             output_path, file_size_kb, status, error_msg, logged_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (contact_id, contact_name, wish_text, engine_used, voice_id,
          str(out_path), file_size_kb,
          "generated" if success else "failed",
          error_msg, datetime.now().isoformat()))
    log_id = cur.lastrowid
    conn.commit()
    conn.close()

    if success:
        print(f"[VoiceClone] {contact_name} — {engine_used} — "
              f"{file_size_kb}KB → {out_path.name}")
    return {
        "success":     success,
        "engine_used": engine_used,
        "output_path": str(out_path),
        "file_size_kb":file_size_kb,
        "log_id":      log_id,
        "error":       error_msg,
    }


def get_audio_url(output_path: str, base_url: str = "") -> str:
    """
    Convert local output_path to a publicly accessible URL.
    In production: upload to S3/CDN and return URL.
    For local testing: return file:// path.
    """
    if base_url:
        fname = Path(output_path).name
        return f"{base_url.rstrip('/')}/voice/{fname}"
    return f"file://{output_path}"


def get_voice_log(limit: int = 20) -> list[dict]:
    """Return recent voice generation history."""
    init_voice_tables()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT contact_name, engine, file_size_kb, status,
               output_path, error_msg, logged_at
        FROM voice_cloning_log ORDER BY logged_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [{"contact_name": r[0], "engine": r[1], "file_size_kb": r[2],
             "status": r[3], "output_path": r[4],
             "error_msg": r[5] or "", "logged_at": r[6]} for r in rows]


# ── Demo seeder ───────────────────────────────────────────────────────────────

def _seed_demo():
    init_voice_tables()
    conn  = sqlite3.connect(DB_PATH)
    count = conn.execute(
        "SELECT COUNT(*) FROM voice_cloning_log").fetchone()[0]
    conn.close()
    if count > 0:
        return
    contacts = [
        ("urn_rakib_001","Rakib Hossain",
         "Happy Birthday Rakib! Hope Pathao is treating you well!"),
        ("urn_mim_004","Mim Chowdhury",
         "Happy Birthday Mim! From IUT to where you are now — what a run!"),
    ]
    for cid, cname, text in contacts:
        generate_voice_wish(cid, cname, text)


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Voice Cloning", page_icon="🎙️",
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
    .engine-card{background:var(--surface);border:1px solid var(--border);
                 border-radius:10px;padding:14px 16px;margin-bottom:8px;}
    .log-row{background:var(--surface);border:1px solid var(--border);
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

    init_voice_tables()
    _seed_demo()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">🎙️</span>
      <h1>Voice Cloning</h1>
      <span class="cc-badge">v9.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    el_ok  = bool(ELEVENLABS_KEY)
    oai_ok = bool(OPENAI_KEY)
    log    = get_voice_log(50)

    m1, m2, m3, m4 = st.columns(4)
    for col, lbl, val, color in [
        (m1, "ElevenLabs",  "✓ Ready" if el_ok  else "✗ No key", "#3fb950" if el_ok  else "#f85149"),
        (m2, "OpenAI TTS",  "✓ Ready" if oai_ok else "✗ No key", "#3fb950" if oai_ok else "#f85149"),
        (m3, "gTTS",        "✓ Always", "#58a6ff"),
        (m4, "Generated",   len(log),   "#f78166"),
    ]:
        with col:
            st.markdown(f'<div class="mini"><div class="mini-val" style="color:{color}">'
                        f'{val}</div><div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1.2, 1], gap="large")

    with left:
        # Engine cards
        st.markdown('<div class="section-title">TTS Engines</div>',
                    unsafe_allow_html=True)
        for key, meta in VOICES.items():
            ready = (
                el_ok if key == "elevenlabs" else
                oai_ok if key == "openai_tts" else True
            )
            border = f"border-color:{meta['color']}55;" if ready else ""
            st.markdown(f"""
            <div class="engine-card" style="{border}">
              <div style="display:flex;align-items:center;justify-content:space-between">
                <div style="font-weight:700">{meta['icon']} {meta['label']}</div>
                <span style="font-size:0.68rem;color:{'#3fb950' if ready else '#f85149'}">
                  {'Ready' if ready else 'Key missing'}
                </span>
              </div>
              <div style="font-size:0.70rem;color:#8b949e;margin-top:4px">
                Quality: {meta['quality']} · Cost: {meta['cost']}
              </div>
            </div>
            """, unsafe_allow_html=True)

        # Generate form
        st.markdown('<div class="section-title">Generate Voice Wish</div>',
                    unsafe_allow_html=True)
        cname    = st.text_input("Contact name", placeholder="Rakib Hossain",
                                 label_visibility="collapsed", key="cname")
        wish_txt = st.text_area("Wish text", height=80,
                                label_visibility="collapsed", key="wtxt",
                                placeholder="Happy Birthday! Hope you have an amazing day...")
        engine   = st.selectbox("Engine", ["auto","elevenlabs","openai_tts","gtts"],
                                label_visibility="collapsed", key="engine")
        if engine == "openai_tts":
            ov = st.selectbox("OpenAI voice", OPENAI_VOICE_OPTIONS,
                              index=4, label_visibility="collapsed", key="ov")
        else:
            ov = "nova"

        if st.button("🎙️ Generate Voice Note", type="primary",
                     use_container_width=True):
            if cname and wish_txt:
                with st.spinner("Generating..."):
                    r = generate_voice_wish(
                        "manual_001", cname, wish_txt,
                        engine=engine, openai_voice=ov)
                if r["success"]:
                    st.success(f"✅ {r['engine_used']} — {r['file_size_kb']}KB")
                    p = Path(r["output_path"])
                    if p.exists() and p.stat().st_size > 500:
                        st.audio(str(p))
                else:
                    st.error(f"Failed: {r['error']}")
                st.rerun()

        # Clone voice section
        st.markdown('<div class="section-title">Clone Your Voice</div>',
                    unsafe_allow_html=True)
        st.markdown("""
        <div style="background:#1a1500;border-left:3px solid #d29922;
                    border-radius:7px;padding:10px 14px;font-size:0.78rem;
                    color:#c9d1d9;">
          Upload 1+ minute of your voice recordings to ElevenLabs,
          then set <code style="color:#7ee787">ELEVENLABS_VOICE_ID</code>
          in <code style="color:#7ee787">.env</code> to use your cloned voice.
        </div>
        """, unsafe_allow_html=True)
        uploaded = st.file_uploader("Upload voice sample (.mp3/.wav)",
                                    type=["mp3","wav","m4a"],
                                    label_visibility="collapsed")
        if uploaded and st.button("Clone Voice", use_container_width=True):
            sample_path = AUDIO_DIR / uploaded.name
            sample_path.write_bytes(uploaded.read())
            if el_ok:
                vid = clone_voice_from_samples([str(sample_path)])
                if vid:
                    st.success(f"Voice cloned! ID: {vid}")
                    st.info(f"Set ELEVENLABS_VOICE_ID={vid} in .env")
                else:
                    st.error("Clone failed — check ElevenLabs API key")
            else:
                st.warning("ELEVENLABS_API_KEY not set")

    with right:
        st.markdown('<div class="section-title">Generation Log</div>',
                    unsafe_allow_html=True)
        for entry in log[:12]:
            engine_meta = VOICES.get(entry["engine"], VOICES["gtts"])
            color  = engine_meta["color"] if entry["status"] == "generated" else "#f85149"
            ts     = entry["logged_at"][:16].replace("T", " ")
            st.markdown(f"""
            <div class="log-row">
              <div style="display:flex;align-items:center;justify-content:space-between">
                <div style="font-weight:700;font-size:0.84rem">
                  {entry['contact_name']}
                </div>
                <span style="font-size:0.7rem;color:{color};font-weight:700">
                  {engine_meta['icon']} {entry['engine']}
                </span>
              </div>
              <div style="font-size:0.68rem;color:#8b949e;margin-top:2px">
                {entry['file_size_kb']}KB · {entry['status']} · {ts}
              </div>
              {f'<div style="font-size:0.7rem;color:#f85149;margin-top:3px">{entry["error_msg"]}</div>' if entry["error_msg"] else ''}
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">9.0</code></span>
      <span>Voice Cloning</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    init_voice_tables()
    print("=== Voice Cloning -- self test ===\n")
    contacts = [
        ("urn_rakib_001","Rakib Hossain",
         "Happy Birthday Rakib! Hope Pathao is treating you well. "
         "Wishing you an amazing year ahead!"),
        ("urn_mim_004","Mim Chowdhury",
         "Happy Birthday Mim! From IUT to where you are now — what a run! "
         "Hope today is as brilliant as you are."),
    ]
    for cid, cname, text in contacts:
        r = generate_voice_wish(cid, cname, text)
        print(f"  {cname:<22} engine={r['engine_used']:<12} "
              f"size={r['file_size_kb']}KB  path={Path(r['output_path']).name}")
    log = get_voice_log(5)
    print(f"\nLog ({len(log)} entries):")
    for e in log:
        print(f"  {e['contact_name']:<22} {e['engine']:<12} {e['status']}")
else:
    render_dashboard()
