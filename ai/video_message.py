"""
Video Message -- Birthday Wishes Agent v9.0
Generates a short AI birthday video combining:
  - Animated text overlay on a background
  - TTS audio (from voice_cloning.py)
  - Optional AI image background (via DALL-E or Stable Diffusion)

Output: .mp4 ready to send via WhatsApp / Telegram

Tiers:
  full    -- AI background image + TTS audio + animated text (MoviePy + OpenAI)
  simple  -- Solid color background + TTS audio + text (MoviePy only)
  card    -- Pillow-rendered static image card (no video, no dependencies)

Requires (optional):
  pip install moviepy pillow gtts
  pip install openai          (for DALL-E background)

Integrates with: ai/voice_cloning.py,
                 platforms/whatsapp_business_api.py,
                 platforms/telegram_birthday.py, agent.py
"""

import os
import json
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional

DB_PATH   = Path("agent_history.db")
VIDEO_DIR = Path("video_output")
VIDEO_DIR.mkdir(exist_ok=True)

OPENAI_KEY   = os.getenv("OPENAI_API_KEY", "")
STABILITY_KEY= os.getenv("STABILITY_API_KEY", "")

TIERS = {
    "full":   {"label": "Full AI Video",  "icon": "🎬", "color": "#f78166"},
    "simple": {"label": "Simple Video",   "icon": "📹", "color": "#58a6ff"},
    "card":   {"label": "Image Card",     "icon": "🎴", "color": "#3fb950"},
}

BG_COLORS = {
    "birthday": "#1a0a2e",
    "warm":     "#1a0d00",
    "elegant":  "#0a0a14",
    "fresh":    "#001a0d",
}

FONTS_FALLBACK = ["DejaVu-Sans", "Arial", "FreeSans", "LiberationSans"]


# ── DB setup ──────────────────────────────────────────────────────────────────

def init_video_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS video_message_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            wish_text       TEXT NOT NULL,
            tier            TEXT NOT NULL,
            bg_style        TEXT,
            output_path     TEXT,
            duration_sec    REAL,
            file_size_kb    REAL,
            sent_via        TEXT,
            status          TEXT NOT NULL DEFAULT 'generated',
            error_msg       TEXT,
            logged_at       TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── Background generators ─────────────────────────────────────────────────────

def _generate_ai_background(
    contact_name: str,
    style:        str = "birthday",
) -> Optional[str]:
    """
    Generate a background image via DALL-E 3.
    Returns local path or None on failure.
    """
    if not OPENAI_KEY:
        return None
    try:
        import urllib.request
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_KEY)
        prompt = (
            f"Abstract {style} celebration background for a birthday card. "
            "Soft bokeh lights, pastel gradients, no text, no faces. "
            "Cinematic, elegant, dark mood. 16:9 ratio."
        )
        resp     = client.images.generate(
            model="dall-e-3", prompt=prompt,
            size="1792x1024", quality="standard", n=1,
        )
        img_url  = resp.data[0].url
        bg_path  = VIDEO_DIR / f"bg_{hashlib.md5(contact_name.encode()).hexdigest()[:8]}.png"
        urllib.request.urlretrieve(img_url, str(bg_path))
        return str(bg_path)
    except Exception as exc:
        print(f"[VideoMsg] DALL-E background failed: {exc}")
        return None


def _generate_gradient_background(
    width: int, height: int, style: str = "birthday"
) -> Optional[str]:
    """Generate a gradient background using Pillow."""
    try:
        from PIL import Image, ImageDraw
        import colorsys

        COLOR_MAP = {
            "birthday": [(26, 10, 46),  (80, 20, 120)],
            "warm":     [(26, 13, 0),   (100, 50, 10)],
            "elegant":  [(10, 10, 20),  (30, 30, 60)],
            "fresh":    [(0,  26, 13),  (10, 80, 40)],
        }
        c1, c2 = COLOR_MAP.get(style, COLOR_MAP["birthday"])
        img    = Image.new("RGB", (width, height))
        draw   = ImageDraw.Draw(img)
        for y in range(height):
            t = y / height
            r = int(c1[0] + (c2[0] - c1[0]) * t)
            g = int(c1[1] + (c2[1] - c1[1]) * t)
            b = int(c1[2] + (c2[2] - c1[2]) * t)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        bg_path = VIDEO_DIR / f"bg_gradient_{style}.png"
        img.save(str(bg_path))
        return str(bg_path)
    except ImportError:
        return None


# ── Image card (no video, Pillow only) ───────────────────────────────────────

def generate_card(
    contact_id:   str,
    contact_name: str,
    wish_text:    str,
    style:        str = "birthday",
    width:        int = 1280,
    height:       int = 720,
) -> dict:
    """
    Generate a static birthday card image (.png).
    Works with only Pillow installed.
    """
    init_video_tables()
    out_path = VIDEO_DIR / f"card_{contact_id}_{hashlib.md5(wish_text.encode()).hexdigest()[:8]}.png"

    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return _log_and_return(
            contact_id, contact_name, wish_text, "card", style,
            str(out_path), success=False,
            error="Pillow not installed: pip install pillow")

    try:
        # Background
        img  = Image.new("RGB", (width, height), color=(26, 10, 46))
        draw = ImageDraw.Draw(img)

        # Gradient overlay
        for y in range(height):
            t = y / height
            r = int(26  + (80  - 26)  * t)
            g = int(10  + (20  - 10)  * t)
            b = int(46  + (120 - 46)  * t)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # Decorative circles
        for cx, cy, cr, alpha in [
            (100, 100, 80,  40), (width-120, 80,  60, 30),
            (80,  height-100, 50, 25), (width-80, height-80, 70, 35),
        ]:
            overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            od      = ImageDraw.Draw(overlay)
            od.ellipse([cx-cr, cy-cr, cx+cr, cy+cr],
                       fill=(247, 129, 102, alpha))
            img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
            draw = ImageDraw.Draw(img)

        # Try to load a font, fall back to default
        font_large = font_small = None
        for fname in ["DejaVuSans-Bold.ttf", "Arial Bold.ttf",
                      "FreeSansBold.ttf", "LiberationSans-Bold.ttf"]:
            try:
                font_large = ImageFont.truetype(fname, 64)
                font_small = ImageFont.truetype(fname.replace("Bold", ""), 32)
                break
            except (IOError, OSError):
                continue
        if font_large is None:
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()

        # 🎂 emoji substitute (text)
        draw.text((width // 2, height // 2 - 140),
                  "Happy Birthday!", font=font_large,
                  fill=(247, 129, 102), anchor="mm")

        # Contact name
        first = contact_name.split()[0]
        draw.text((width // 2, height // 2 - 60),
                  first, font=font_large,
                  fill=(230, 237, 243), anchor="mm")

        # Wish text (word-wrap)
        words  = wish_text.split()
        lines  = []
        line   = ""
        for w in words:
            test = f"{line} {w}".strip()
            if len(test) > 55:
                lines.append(line)
                line = w
            else:
                line = test
        if line:
            lines.append(line)

        y_text = height // 2 + 20
        for ln in lines[:4]:
            draw.text((width // 2, y_text), ln, font=font_small,
                      fill=(201, 209, 217), anchor="mm")
            y_text += 44

        # Footer
        draw.text((width // 2, height - 40),
                  "Birthday Wishes Agent v9.0",
                  font=font_small, fill=(139, 148, 158), anchor="mm")

        img.save(str(out_path), "PNG")
        size_kb = round(out_path.stat().st_size / 1024, 1)
        return _log_and_return(contact_id, contact_name, wish_text,
                               "card", style, str(out_path),
                               success=True, file_size_kb=size_kb)

    except Exception as exc:
        return _log_and_return(contact_id, contact_name, wish_text,
                               "card", style, str(out_path),
                               success=False, error=str(exc))


# ── Simple video (MoviePy + gradient) ────────────────────────────────────────

def generate_simple_video(
    contact_id:   str,
    contact_name: str,
    wish_text:    str,
    style:        str = "birthday",
    duration:     int = 8,
    audio_path:   Optional[str] = None,
) -> dict:
    """
    Generate a simple video with gradient background + text overlay + audio.
    Requires: pip install moviepy pillow
    """
    init_video_tables()
    out_path = VIDEO_DIR / f"video_{contact_id}_{hashlib.md5(wish_text.encode()).hexdigest()[:8]}.mp4"

    try:
        from moviepy.editor import (
            ColorClip, TextClip, CompositeVideoClip, AudioFileClip,
            concatenate_videoclips,
        )
    except ImportError:
        # Fall back to card if moviepy not available
        print("[VideoMsg] moviepy not installed — generating card instead")
        return generate_card(contact_id, contact_name, wish_text, style)

    try:
        W, H    = 1280, 720
        bg_hex  = BG_COLORS.get(style, BG_COLORS["birthday"])
        r, g, b = tuple(int(bg_hex.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))

        bg      = ColorClip(size=(W, H), color=(r, g, b), duration=duration)

        # Title clip
        title   = TextClip(
            f"Happy Birthday\n{contact_name.split()[0]}!",
            fontsize=72, color="white", font="DejaVu-Sans-Bold",
            method="caption", size=(W - 100, None),
        ).set_position("center").set_duration(duration).crossfadein(1.0)

        # Wish text clip
        body    = TextClip(
            wish_text[:200],
            fontsize=36, color="#c9d1d9", font="DejaVu-Sans",
            method="caption", size=(W - 160, None),
        ).set_position(("center", H // 2 + 60)).set_duration(duration).crossfadein(1.5)

        clips   = [bg, title, body]

        # Add audio if available
        if audio_path and Path(audio_path).exists():
            audio   = AudioFileClip(audio_path).subclip(0, duration)
            video   = CompositeVideoClip(clips).set_audio(audio)
        else:
            video   = CompositeVideoClip(clips)

        video.write_videofile(
            str(out_path), fps=24, codec="libx264",
            audio_codec="aac", logger=None,
        )
        size_kb = round(out_path.stat().st_size / 1024, 1)
        return _log_and_return(contact_id, contact_name, wish_text,
                               "simple", style, str(out_path),
                               success=True, file_size_kb=size_kb,
                               duration=duration)

    except Exception as exc:
        return _log_and_return(contact_id, contact_name, wish_text,
                               "simple", style, str(out_path),
                               success=False, error=str(exc))


# ── Full AI video ─────────────────────────────────────────────────────────────

def generate_full_video(
    contact_id:   str,
    contact_name: str,
    wish_text:    str,
    style:        str = "birthday",
    duration:     int = 10,
    audio_path:   Optional[str] = None,
) -> dict:
    """
    Generate a full AI video:
      1. DALL-E 3 background image
      2. TTS audio (from voice_cloning if available)
      3. Animated text overlay with MoviePy

    Falls back to simple video if DALL-E unavailable.
    """
    # Step 1: AI background
    bg_path = _generate_ai_background(contact_name, style)
    if not bg_path:
        bg_path = _generate_gradient_background(1280, 720, style)

    try:
        from moviepy.editor import (
            ImageClip, TextClip, CompositeVideoClip, AudioFileClip,
        )
    except ImportError:
        return generate_card(contact_id, contact_name, wish_text, style)

    out_path = VIDEO_DIR / f"full_{contact_id}_{hashlib.md5(wish_text.encode()).hexdigest()[:8]}.mp4"

    try:
        W, H  = 1280, 720
        clips = []

        if bg_path and Path(bg_path).exists():
            bg = ImageClip(bg_path).set_duration(duration).resize((W, H))
        else:
            from moviepy.editor import ColorClip
            bg = ColorClip(size=(W, H), color=(26, 10, 46), duration=duration)
        clips.append(bg)

        # Animated title (fade in + zoom)
        title = TextClip(
            f"Happy Birthday\n{contact_name.split()[0]}!",
            fontsize=80, color="#f78166", font="DejaVu-Sans-Bold",
            method="caption", size=(W - 80, None),
        ).set_position("center").set_duration(duration).crossfadein(1.2)
        clips.append(title)

        # Body text
        body = TextClip(
            wish_text[:200],
            fontsize=38, color="white", font="DejaVu-Sans",
            method="caption", size=(W - 160, None),
        ).set_position(("center", H * 0.65)).set_duration(duration).crossfadein(2.0)
        clips.append(body)

        video = CompositeVideoClip(clips)

        if audio_path and Path(audio_path).exists():
            audio = AudioFileClip(audio_path).subclip(0, duration)
            video = video.set_audio(audio)

        video.write_videofile(
            str(out_path), fps=24, codec="libx264",
            audio_codec="aac", logger=None,
        )
        size_kb = round(out_path.stat().st_size / 1024, 1)
        return _log_and_return(contact_id, contact_name, wish_text,
                               "full", style, str(out_path),
                               success=True, file_size_kb=size_kb,
                               duration=duration)

    except Exception as exc:
        return _log_and_return(contact_id, contact_name, wish_text,
                               "full", style, str(out_path),
                               success=False, error=str(exc))


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_video_wish(
    contact_id:   str,
    contact_name: str,
    wish_text:    str,
    tier:         str = "auto",
    style:        str = "birthday",
    audio_path:   Optional[str] = None,
) -> dict:
    """
    Generate a birthday video wish. Auto-selects tier based on available deps.

    Args:
        tier:       auto / full / simple / card
        style:      birthday / warm / elegant / fresh
        audio_path: Path to .mp3 voice note (from voice_cloning.py)

    Returns:
        { success, tier_used, output_path, file_size_kb, log_id, error }
    """
    if tier == "auto":
        try:
            import moviepy  # noqa: F401
            tier = "full" if OPENAI_KEY else "simple"
        except ImportError:
            tier = "card"

    if tier == "full":
        return generate_full_video(
            contact_id, contact_name, wish_text, style,
            audio_path=audio_path)
    if tier == "simple":
        return generate_simple_video(
            contact_id, contact_name, wish_text, style,
            audio_path=audio_path)
    return generate_card(contact_id, contact_name, wish_text, style)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log_and_return(
    contact_id, contact_name, wish_text, tier, style,
    output_path, success, file_size_kb=0.0, duration=None, error=""
) -> dict:
    init_video_tables()
    conn   = sqlite3.connect(DB_PATH)
    cur    = conn.execute("""
        INSERT INTO video_message_log
            (contact_id, contact_name, wish_text, tier, bg_style,
             output_path, duration_sec, file_size_kb,
             status, error_msg, logged_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (contact_id, contact_name, wish_text, tier, style,
          output_path, duration, file_size_kb,
          "generated" if success else "failed",
          error, datetime.now().isoformat()))
    log_id = cur.lastrowid
    conn.commit()
    conn.close()

    tier_meta = TIERS.get(tier, TIERS["card"])
    if success:
        print(f"[VideoMsg] {contact_name} — {tier_meta['icon']} {tier} "
              f"— {file_size_kb}KB → {Path(output_path).name}")
    return {
        "success":     success,
        "tier_used":   tier,
        "output_path": output_path,
        "file_size_kb":file_size_kb,
        "log_id":      log_id,
        "error":       error,
    }


def get_video_log(limit: int = 20) -> list[dict]:
    """Return recent video generation history."""
    init_video_tables()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT contact_name, tier, file_size_kb, duration_sec,
               status, output_path, error_msg, logged_at
        FROM video_message_log ORDER BY logged_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [{"contact_name": r[0], "tier": r[1], "file_size_kb": r[2] or 0,
             "duration_sec": r[3], "status": r[4], "output_path": r[5],
             "error_msg": r[6] or "", "logged_at": r[7]} for r in rows]


# ── Demo seeder ───────────────────────────────────────────────────────────────

def _seed_demo():
    init_video_tables()
    conn  = sqlite3.connect(DB_PATH)
    count = conn.execute(
        "SELECT COUNT(*) FROM video_message_log").fetchone()[0]
    conn.close()
    if count > 0:
        return
    contacts = [
        ("urn_rakib_001","Rakib Hossain",
         "Happy Birthday Rakib! Hope Pathao is treating you well."),
        ("urn_mim_004","Mim Chowdhury",
         "Happy Birthday Mim! From IUT to where you are — what a run!"),
    ]
    for cid, cname, text in contacts:
        generate_video_wish(cid, cname, text)


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Video Message", page_icon="🎬",
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
    .tier-card{background:var(--surface);border:1px solid var(--border);
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

    init_video_tables()
    _seed_demo()

    try:
        import moviepy  # noqa: F401
        has_moviepy = True
    except ImportError:
        has_moviepy = False

    try:
        from PIL import Image  # noqa: F401
        has_pillow = True
    except ImportError:
        has_pillow = False

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">🎬</span>
      <h1>Video Message</h1>
      <span class="cc-badge">v9.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    log   = get_video_log(50)
    m1, m2, m3, m4 = st.columns(4)
    for col, lbl, val, color in [
        (m1, "MoviePy",   "✓ Ready" if has_moviepy else "✗ Not installed",
         "#3fb950" if has_moviepy else "#f85149"),
        (m2, "Pillow",    "✓ Ready" if has_pillow else "✗ Not installed",
         "#3fb950" if has_pillow else "#f85149"),
        (m3, "DALL-E",    "✓ Ready" if OPENAI_KEY else "✗ No key",
         "#3fb950" if OPENAI_KEY else "#d29922"),
        (m4, "Generated", len(log), "#f78166"),
    ]:
        with col:
            st.markdown(f'<div class="mini"><div class="mini-val" style="color:{color}">'
                        f'{val}</div><div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1.2, 1], gap="large")

    with left:
        st.markdown('<div class="section-title">Video Tiers</div>',
                    unsafe_allow_html=True)
        tier_descs = {
            "full":   ("DALL-E background + TTS audio + animated text",
                       has_moviepy and bool(OPENAI_KEY)),
            "simple": ("Gradient background + animated text",
                       has_moviepy),
            "card":   ("Static PNG birthday card",
                       has_pillow),
        }
        for key, meta in TIERS.items():
            desc, ready = tier_descs[key]
            st.markdown(f"""
            <div class="tier-card" style="{'border-color:'+meta['color']+'55' if ready else ''}">
              <div style="display:flex;align-items:center;justify-content:space-between">
                <div style="font-weight:700">{meta['icon']} {meta['label']}</div>
                <span style="font-size:0.68rem;
                             color:{'#3fb950' if ready else '#f85149'}">
                  {'Ready' if ready else 'Deps missing'}
                </span>
              </div>
              <div style="font-size:0.70rem;color:#8b949e;margin-top:4px">
                {desc}
              </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown('<div class="section-title">Generate Video</div>',
                    unsafe_allow_html=True)
        cname    = st.text_input("Contact name", placeholder="Rakib Hossain",
                                 label_visibility="collapsed", key="cname")
        wish_txt = st.text_area("Wish text", height=80,
                                label_visibility="collapsed", key="wtxt",
                                placeholder="Happy Birthday! Wishing you an amazing year...")
        tier_sel = st.selectbox("Tier",
                                ["auto","full","simple","card"],
                                label_visibility="collapsed", key="tier")
        style_sel= st.selectbox("Style",
                                list(BG_COLORS.keys()),
                                label_visibility="collapsed", key="style")

        if st.button("🎬 Generate Video", type="primary",
                     use_container_width=True):
            if cname and wish_txt:
                with st.spinner("Generating..."):
                    r = generate_video_wish(
                        "manual_001", cname, wish_txt,
                        tier=tier_sel, style=style_sel)
                if r["success"]:
                    st.success(f"✅ {r['tier_used']} — {r['file_size_kb']}KB")
                    p = Path(r["output_path"])
                    if p.exists():
                        if p.suffix == ".mp4":
                            st.video(str(p))
                        else:
                            st.image(str(p))
                else:
                    st.error(f"Failed: {r['error']}")
                st.rerun()

        st.markdown('<div class="section-title">Install Dependencies</div>',
                    unsafe_allow_html=True)
        st.code("pip install moviepy pillow gtts\npip install openai  # for DALL-E background")

    with right:
        st.markdown('<div class="section-title">Generation Log</div>',
                    unsafe_allow_html=True)
        for entry in log[:12]:
            meta  = TIERS.get(entry["tier"], TIERS["card"])
            color = meta["color"] if entry["status"] == "generated" else "#f85149"
            ts    = entry["logged_at"][:16].replace("T", " ")
            size  = f"{entry['file_size_kb']:.1f}KB" if entry["file_size_kb"] else "–"
            dur   = f"{entry['duration_sec']}s" if entry["duration_sec"] else "–"
            st.markdown(f"""
            <div class="log-row">
              <div style="display:flex;align-items:center;
                          justify-content:space-between">
                <div style="font-weight:700;font-size:0.84rem">
                  {entry['contact_name']}
                </div>
                <span style="font-size:0.7rem;color:{color};font-weight:700">
                  {meta['icon']} {entry['tier']}
                </span>
              </div>
              <div style="font-size:0.68rem;color:#8b949e;margin-top:2px">
                {size} · {dur} · {entry['status']} · {ts}
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
      <span>Video Message</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    init_video_tables()
    print("=== Video Message -- self test ===\n")
    contacts = [
        ("urn_rakib_001","Rakib Hossain",
         "Happy Birthday Rakib! Hope Pathao is treating you well. "
         "Wishing you an amazing year ahead!"),
        ("urn_mim_004","Mim Chowdhury",
         "Happy Birthday Mim! From IUT to where you are — what a run!"),
    ]
    for cid, cname, text in contacts:
        r = generate_video_wish(cid, cname, text)
        icon = TIERS.get(r["tier_used"], TIERS["card"])["icon"]
        print(f"  {cname:<22} {icon} tier={r['tier_used']:<8} "
              f"size={r['file_size_kb']}KB  ok={r['success']}")
    log = get_video_log(5)
    print(f"\nLog ({len(log)} entries):")
    for e in log:
        print(f"  {e['contact_name']:<22} {e['tier']:<8} {e['status']}")
else:
    render_dashboard()
