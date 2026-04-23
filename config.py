"""
Configuration File - Sab kuch .env file se load hoga
Koi bhi secret yahan MAT likho!
"""

import os
import sys
from dotenv import load_dotenv

# .env file load karo
load_dotenv()

# ════════════════════════════════════════════════════════════════
#          ENVIRONMENT VARIABLES SE LOAD HOGA (NO SECRETS HERE)
# ════════════════════════════════════════════════════════════════

# 1. Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN")

# 2. Grok API Key
GROK_API_KEY = os.getenv("GROK_API_KEY")

# 3. Admin IDs - comma separated in .env  e.g. "123456,789012"
_admin_ids_raw = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(i.strip()) for i in _admin_ids_raw.split(",") if i.strip().isdigit()]

# ════════════════════════════════════════════════════════════════
#              BOT SETTINGS (Safe to keep here)
# ════════════════════════════════════════════════════════════════

GROK_MODEL            = os.getenv("GROK_MODEL", "grok-3-mini")
BOT_NAME              = os.getenv("BOT_NAME", "AI Guard Bot")
MAX_WARNINGS          = int(os.getenv("MAX_WARNINGS", "3"))
MUTE_DURATION_MINUTES = int(os.getenv("MUTE_DURATION_MINUTES", "10"))
MAX_MESSAGES_PER_MINUTE = int(os.getenv("MAX_MESSAGES_PER_MINUTE", "10"))
AUTO_ANSWER_QUESTIONS = os.getenv("AUTO_ANSWER_QUESTIONS", "true").lower() == "true"
WELCOME_LANGUAGE      = os.getenv("WELCOME_LANGUAGE", "hinglish")
SPAM_SENSITIVITY      = int(os.getenv("SPAM_SENSITIVITY", "3"))

# Log channel (optional)
_log_ch = os.getenv("LOG_CHANNEL_ID", "")
LOG_CHANNEL_ID = int(_log_ch) if _log_ch.lstrip("-").isdigit() else None

# ════════════════════════════════════════════════════════════════
#              STARTUP VALIDATION
# ════════════════════════════════════════════════════════════════

_errors = []

if not BOT_TOKEN:
    _errors.append("❌ BOT_TOKEN missing! .env mein add karo.")

if not GROK_API_KEY:
    _errors.append("❌ GROK_API_KEY missing! .env mein add karo.")

if not ADMIN_IDS:
    _errors.append("⚠️  ADMIN_IDS missing! .env mein apna Telegram ID daalo.")

if _errors:
    print("\n" + "="*50)
    print("  CONFIGURATION ERRORS FOUND:")
    print("="*50)
    for err in _errors:
        print(f"  {err}")
    print("="*50)
    print("  .env file check karo! (sample: .env.example)")
    print("="*50 + "\n")
    if not BOT_TOKEN or not GROK_API_KEY:
        sys.exit(1)   # Critical vars missing - bot start mat karo
else:
    print(f"✅ Config loaded | Bot: {BOT_NAME} | Admins: {ADMIN_IDS}")
