# 🤖 AI Guard Bot - Complete Setup Guide
## Telegram AI Controller Bot (Powered by Grok AI)

---

## ✅ Features List

| Feature | Description |
|---------|-------------|
| 🚫 Auto-Moderation | Adult words, gali automatically delete |
| ⚠️ Warning System | 3 warnings ke baad auto-ban |
| 🔇 Auto-Mute | 2nd warning pe temporary mute |
| 🚫 Auto-Ban | 3rd warning pe permanent ban |
| 👋 Welcome | Naye members ka AI-powered welcome |
| 🤖 AI Q&A | Group ke andar sawaal pucho, AI jawab dega |
| 👻 Ghost Removal | Deleted accounts auto-remove |
| 📊 Stats | Group ki moderation statistics |
| 📌 Pin | Messages pin karna |
| 📢 Broadcast | Group announcement |
| 🛡️ Admin Safe | Admins/Owners pe koi action nahi |
| 🔍 Spam Detection | Spam links auto-detect |

---

## 📋 STEP-BY-STEP SETUP

### STEP 1: Python Install Karo
```bash
# Python 3.10+ chahiye
python --version

# Agar nahi hai:
# Windows: https://python.org/downloads se download karo
# Linux: sudo apt install python3 python3-pip
```

### STEP 2: Bot Files Download Karo
```bash
# Telegram-ai-bot folder mein jao
cd telegram-ai-bot

# Dependencies install karo
pip install -r requirements.txt
```

### STEP 3: Telegram Bot Banao
1. Telegram mein **@BotFather** ko open karo
2. `/newbot` command send karo
3. Bot ka naam likho (e.g., "AI Guard Bot")
4. Username likho (e.g., "myaiguardbot")
5. **Token copy karo** - ye important hai!

### STEP 4: Grok API Key Lo
1. **https://console.x.ai** pe jao
2. Account banao ya login karo
3. API Keys section mein jao
4. "Create API Key" karo
5. **Key copy karo**

### STEP 5: Apna Telegram ID Pata Karo
1. Telegram mein **@userinfobot** ko open karo
2. `/start` bhejo
3. Tumhara ID number dikhega - note karo

### STEP 6: Config File Update Karo
`config.py` file kholo aur ye changes karo:

```python
BOT_TOKEN = "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"  # BotFather wala token
GROK_API_KEY = "xai-xxxxxxxxxxxxxxxxxxxx"  # Grok wali key
ADMIN_IDS = [123456789]  # Tumhara Telegram ID
BOT_NAME = "AI Guard"  # Jo naam chahiye
MAX_WARNINGS = 3  # Kitni warnings ke baad ban
```

### STEP 7: Bot Ko Group Mein Add Karo
1. Apne group/channel mein jao
2. "Add Member" karo
3. Apna bot username search karo
4. Bot add karo
5. **IMPORTANT: Bot ko Admin banao** with permissions:
   - ✅ Delete Messages
   - ✅ Ban Users
   - ✅ Restrict Members
   - ✅ Pin Messages
   - ✅ Invite Users (optional)

### STEP 8: Bot Start Karo
```bash
# Simple start
python bot.py

# Background mein chalane ke liye (Linux):
nohup python bot.py &

# Ya screen use karo:
screen -S mybot
python bot.py
# Ctrl+A, D to detach
```

---

## 🔧 Bot Commands Reference

### User Commands
| Command | Usage |
|---------|-------|
| `/start` | Bot intro |
| `/help` | Help menu |
| `/rules` | Group rules dekho |
| `/ai [sawaal]` | AI se kuch bhi pucho |
| `/warnings` | Apni warnings check karo |

### Admin Commands
| Command | Usage |
|---------|-------|
| `/ban` | Reply karke user ban karo |
| `/unban [id]` | User ID se unban |
| `/mute [mins]` | Reply karke mute (default 10 min) |
| `/unmute` | Reply karke unmute |
| `/kick` | Reply karke kick |
| `/warn` | Manual warning do |
| `/resetwarn` | Warnings reset karo |
| `/warnings` | Kisi ki warnings check karo |
| `/pin` | Message pin karo |
| `/stats` | Group statistics |
| `/setrules [text]` | Group rules set karo |
| `/broadcast [msg]` | Announcement bhejo |

---

## ☁️ 24/7 Chalane Ke Options

### Option A: VPS (Best)
```bash
# DigitalOcean, Hostinger, Contabo etc.
# $5/month se start
# Linux VPS lo, bot upload karo, run karo

# Systemd service banao:
sudo nano /etc/systemd/system/aibot.service

# Paste karo:
[Unit]
Description=Telegram AI Guard Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/telegram-ai-bot
ExecStart=/usr/bin/python3 bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target

# Enable karo:
sudo systemctl enable aibot
sudo systemctl start aibot
sudo systemctl status aibot
```

### Option B: Railway.app (Free)
1. https://railway.app pe jao
2. New Project > Deploy from GitHub
3. Apna code upload karo
4. Environment variables add karo (BOT_TOKEN, GROK_API_KEY)
5. Deploy!

### Option C: Render.com (Free)
1. https://render.com pe jao
2. New > Background Worker
3. Connect GitHub repo
4. Build command: `pip install -r requirements.txt`
5. Start command: `python bot.py`

### Option D: Local Computer (Testing)
```bash
python bot.py
# Jab tak computer on hai, bot chalega
```

---

## ⚙️ Environment Variables (Secure Method)

Config file mein direct keys mat daalo production mein.
`.env` file banao:

```env
BOT_TOKEN=your_token_here
GROK_API_KEY=your_grok_key_here
```

Ya command line mein:
```bash
BOT_TOKEN=xxx GROK_API_KEY=yyy python bot.py
```

---

## 🔍 Troubleshooting

**Bot respond nahi kar raha?**
- Check karo bot Admin hai group mein?
- Token sahi hai?
- bot.py run ho raha hai?

**AI response nahi de raha?**
- Grok API key sahi hai?
- Check karo: https://console.x.ai

**Permission error aa raha hai?**
- Bot ko group mein Admin banao
- Sab permissions do

**"Deleted Account" remove nahi ho raha?**
- Bot ka Admin status confirm karo
- "Ban Users" permission hai?

---

## 📞 Support
Bot ka log dekho: `cat bot.log`
Errors ke liye log file check karo!

---
*Made with ❤️ | Powered by Grok AI (xAI) + python-telegram-bot*
