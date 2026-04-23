"""
AI Controller Bot v2.0 - Configuration
All values load from environment variables / Railway Variables
"""

import os, sys
from dotenv import load_dotenv
load_dotenv()

# ── Required ─────────────────────────────────────────────────────
BOT_TOKEN    = os.getenv("BOT_TOKEN")
GROK_API_KEY = os.getenv("GROK_API_KEY")

_raw = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(i.strip()) for i in _raw.split(",") if i.strip().isdigit()]

# ── Bot Identity ─────────────────────────────────────────────────
BOT_NAME        = os.getenv("BOT_NAME",        "AI Controller")
BOT_USERNAME    = os.getenv("BOT_USERNAME",     "YourBotUsername")   # without @
SUPPORT_CHANNEL = os.getenv("SUPPORT_CHANNEL",  "YourChannelUsername")  # without @
BANNER_IMAGE_URL= os.getenv("BANNER_IMAGE_URL", "")  # direct image URL for /start banner

# ── AI Settings ───────────────────────────────────────────────────
GROK_MODEL            = os.getenv("GROK_MODEL",            "llama-3.3-70b-versatile")
MAX_WARNINGS          = int(os.getenv("MAX_WARNINGS",       "3"))
MUTE_DURATION_MINUTES = int(os.getenv("MUTE_DURATION_MINUTES", "10"))
MAX_MESSAGES_PER_MIN  = int(os.getenv("MAX_MESSAGES_PER_MIN",  "10"))
SPAM_SENSITIVITY      = int(os.getenv("SPAM_SENSITIVITY",   "3"))
WELCOME_LANGUAGE      = os.getenv("WELCOME_LANGUAGE",       "english")

# ── Optional ─────────────────────────────────────────────────────
_lc = os.getenv("LOG_CHANNEL_ID", "")
LOG_CHANNEL_ID = int(_lc) if _lc.lstrip("-").isdigit() else None

# ── Validation ───────────────────────────────────────────────────
_err = []
if not BOT_TOKEN:    _err.append("BOT_TOKEN missing")
if not GROK_API_KEY: _err.append("GROK_API_KEY missing")
if not ADMIN_IDS:    _err.append("ADMIN_IDS missing")

if _err:
    print("\n" + "="*45)
    print("  CONFIG ERROR:")
    for e in _err: print(f"  - {e}")
    print("="*45 + "\n")
    if not BOT_TOKEN or not GROK_API_KEY:
        sys.exit(1)
else:
    print(f"[OK] Config loaded | {BOT_NAME} | Admins: {ADMIN_IDS}")
