# Birthday Wishes Agent — Browser Extension

## Installation

1. Open Chrome → `chrome://extensions/`
2. Enable **Developer mode** (top right toggle)
3. Click **Load unpacked**
4. Select the `extension/` folder

## Setup

1. Make sure the Birthday Agent web app is running:

   ```
   uvicorn webapp.main:app --port 8000
   ```

2. Click the 🎂 extension icon in Chrome toolbar
3. Enter:
   - API URL: `http://localhost:8000`
   - Username: `admin`
   - Password: `admin123`
4. Click **Sign In**

## Usage

- Open any LinkedIn profile
- The sidebar automatically appears on the right side
- Shows: contact info, relationship health, memory, wish history, notes
- Add notes directly from the sidebar

## Files

- `manifest.json` — Extension configuration
- `content.js` — LinkedIn page script (extracts profile, injects sidebar)
- `sidebar.css` — Sidebar styling
- `popup.html` — Extension popup (login)
