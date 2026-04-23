"""
╔══════════════════════════════════════════════════════════╗
║         TELEGRAM AI CONTROLLER BOT - by Grok AI         ║
║   Full Group/Channel Moderation + AI Q&A + Auto-Admin   ║
╚══════════════════════════════════════════════════════════╝
"""

import logging
import json
import re
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict

from telegram import (
    Update, ChatPermissions, InlineKeyboardButton,
    InlineKeyboardMarkup, ChatMember
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ChatMemberHandler,
    ContextTypes, filters
)
from telegram.constants import ParseMode, ChatMemberStatus
from telegram.error import TelegramError

import httpx
from config import (
    BOT_TOKEN, GROK_API_KEY, GROK_MODEL,
    MAX_WARNINGS, MUTE_DURATION_MINUTES,
    ADMIN_IDS, BOT_NAME
)
from database import db
from ai_engine import AIEngine

# ─── Logging Setup ──────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ─── AI Engine Instance ──────────────────────────────────────────
ai = AIEngine(GROK_API_KEY, GROK_MODEL)

# ─── Helper: Check Admin/Owner ──────────────────────────────────
async def is_admin_or_owner(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """Check if user is admin or owner of the chat."""
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except TelegramError:
        return False

async def is_global_admin(user_id: int) -> bool:
    """Check if user is in global admin list."""
    return user_id in ADMIN_IDS

# ─── Helper: Safe Send Message ──────────────────────────────────
async def safe_send(context, chat_id, text, parse_mode=ParseMode.HTML, **kwargs):
    try:
        return await context.bot.send_message(
            chat_id=chat_id, text=text, parse_mode=parse_mode, **kwargs
        )
    except TelegramError as e:
        logger.error(f"Send error: {e}")

# ════════════════════════════════════════════════════════════════
#                     WELCOME SYSTEM
# ════════════════════════════════════════════════════════════════

async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new members joining the group."""
    chat = update.effective_chat
    
    for member in update.message.new_chat_members:
        user_id = member.id
        username = member.username or member.first_name
        
        # ── Auto-kick deleted accounts ──────────────────────────
        if member.is_deleted_account if hasattr(member, 'is_deleted_account') else False:
            try:
                await context.bot.ban_chat_member(chat.id, user_id)
                await context.bot.unban_chat_member(chat.id, user_id)
                await safe_send(context, chat.id, 
                    "🤖 <b>AI Guard:</b> Deleted account detected and removed automatically.")
                logger.info(f"Removed deleted account {user_id}")
                continue
            except TelegramError as e:
                logger.error(f"Could not remove deleted account: {e}")
        
        # ── Check if username is suspicious (deleted accounts show as "Deleted Account") ──
        if member.first_name and "Deleted Account" in member.first_name:
            try:
                await context.bot.ban_chat_member(chat.id, user_id)
                await context.bot.unban_chat_member(chat.id, user_id)
                await safe_send(context, chat.id,
                    "🤖 <b>AI Guard:</b> Deleted/ghost account removed!")
                continue
            except TelegramError as e:
                logger.error(f"Error removing ghost account: {e}")
        
        # ── Generate AI Welcome Message ─────────────────────────
        try:
            chat_title = chat.title or "this group"
            welcome_prompt = f"""Generate a warm, friendly welcome message for a new member joining a Telegram group.
Member name: {member.first_name}
Group name: {chat_title}
Keep it short (2-3 lines), friendly, and use 1-2 relevant emojis. 
Include: welcome greeting, brief intro about the group being a great community, 
and a note to read the rules. Write in a mix of Hindi and English (Hinglish) style."""

            ai_welcome = await ai.generate_response(welcome_prompt)
            
            # Add rules button
            keyboard = [[
                InlineKeyboardButton("📋 Rules", callback_data=f"rules_{chat.id}"),
                InlineKeyboardButton("❓ Help", callback_data="help_menu")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await safe_send(
                context, chat.id,
                f"👋 <b>Welcome, <a href='tg://user?id={user_id}'>{member.first_name}</a>!</b>\n\n"
                f"{ai_welcome}\n\n"
                f"🤖 <i>I'm {BOT_NAME}, your AI Group Manager!</i>",
                reply_markup=reply_markup
            )
            
            # Log new member
            db.log_event("member_join", chat.id, user_id, {"username": username})
            
        except Exception as e:
            logger.error(f"Welcome message error: {e}")
            await safe_send(
                context, chat.id,
                f"👋 Welcome <b>{member.first_name}</b>! Please read the group rules. 😊"
            )

# ════════════════════════════════════════════════════════════════
#                   MESSAGE MODERATION
# ════════════════════════════════════════════════════════════════

async def moderate_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main message handler - moderates content and answers questions."""
    message = update.message or update.edited_message
    if not message or not message.text:
        return
    
    chat = update.effective_chat
    user = update.effective_user
    
    if not user:
        return
    
    # ── Skip admins and owners ──────────────────────────────────
    if await is_admin_or_owner(update, context, user.id) or await is_global_admin(user.id):
        # Still handle AI questions from admins
        if f"@{context.bot.username}" in (message.text or ""):
            await handle_ai_question(update, context)
        return
    
    text = message.text
    
    # ── Step 1: Check for violations ────────────────────────────
    violation = await ai.check_content_violation(text)
    
    if violation["is_violation"]:
        await handle_violation(update, context, user, chat, message, violation)
        return
    
    # ── Step 2: Check if user is asking AI a question ───────────
    bot_username = f"@{context.bot.username}" if context.bot.username else ""
    is_question_to_bot = (
        bot_username and bot_username.lower() in text.lower()
    ) or (
        message.reply_to_message and 
        message.reply_to_message.from_user and
        message.reply_to_message.from_user.id == context.bot.id
    )
    
    if is_question_to_bot:
        await handle_ai_question(update, context)
        return
    
    # ── Step 3: Auto-detect questions and answer helpfully ──────
    if chat.type == "private":
        await handle_ai_question(update, context)
    elif await ai.is_question_needing_answer(text):
        # Only answer in groups if it seems like a genuine question
        await handle_ai_question(update, context)


async def handle_violation(update, context, user, chat, message, violation):
    """Handle content violations with warnings and bans."""
    user_id = user.id
    chat_id = chat.id
    
    try:
        # Delete the violating message
        await message.delete()
    except TelegramError:
        pass
    
    # Add warning
    warnings = db.add_warning(chat_id, user_id)
    remaining = MAX_WARNINGS - warnings
    
    violation_type = violation.get("type", "inappropriate content")
    reason = violation.get("reason", "Inappropriate content detected")
    
    if warnings >= MAX_WARNINGS:
        # BAN the user
        try:
            await context.bot.ban_chat_member(chat_id, user_id)
            await safe_send(
                context, chat_id,
                f"🚫 <b>AI Action: USER BANNED</b>\n\n"
                f"👤 User: <a href='tg://user?id={user_id}'>{user.first_name}</a>\n"
                f"❌ Reason: {reason}\n"
                f"⚠️ Warnings: {warnings}/{MAX_WARNINGS}\n\n"
                f"🤖 <i>{BOT_NAME} has banned this user after {MAX_WARNINGS} violations.</i>"
            )
            db.log_event("ban", chat_id, user_id, {"reason": reason, "warnings": warnings})
            db.reset_warnings(chat_id, user_id)
        except TelegramError as e:
            logger.error(f"Ban error: {e}")
    
    elif warnings == MAX_WARNINGS - 1:
        # Last warning - also mute temporarily
        mute_until = datetime.now() + timedelta(minutes=MUTE_DURATION_MINUTES)
        try:
            await context.bot.restrict_chat_member(
                chat_id, user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=mute_until
            )
            await safe_send(
                context, chat_id,
                f"🔇 <b>AI Action: MUTED + WARNING</b>\n\n"
                f"👤 User: <a href='tg://user?id={user_id}'>{user.first_name}</a>\n"
                f"❌ Violation: {violation_type}\n"
                f"⚠️ Warning {warnings}/{MAX_WARNINGS} — <b>FINAL WARNING!</b>\n"
                f"⏱ Muted for {MUTE_DURATION_MINUTES} minutes\n\n"
                f"🚨 <b>Next violation = PERMANENT BAN!</b>"
            )
            db.log_event("mute", chat_id, user_id, {"reason": reason, "duration": MUTE_DURATION_MINUTES})
        except TelegramError as e:
            logger.error(f"Mute error: {e}")
    
    else:
        # Regular warning
        keyboard = [[InlineKeyboardButton("📋 View Rules", callback_data=f"rules_{chat_id}")]]
        await safe_send(
            context, chat_id,
            f"⚠️ <b>AI Warning!</b>\n\n"
            f"👤 User: <a href='tg://user?id={user_id}'>{user.first_name}</a>\n"
            f"❌ Violation: {violation_type}\n"
            f"📝 {reason}\n\n"
            f"🔴 Warning <b>{warnings}/{MAX_WARNINGS}</b>\n"
            f"{'🚨 ' + str(remaining) + ' more warning(s) before ban!' if remaining > 0 else ''}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        db.log_event("warning", chat_id, user_id, {"reason": reason, "count": warnings})


async def handle_ai_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Answer user questions using Grok AI."""
    message = update.message
    user = update.effective_user
    chat = update.effective_chat
    
    if not message or not message.text:
        return
    
    text = message.text
    # Remove bot mention from question
    if context.bot.username:
        text = text.replace(f"@{context.bot.username}", "").strip()
    
    if len(text) < 2:
        return
    
    # Show typing indicator
    try:
        await context.bot.send_chat_action(chat.id, action="typing")
    except:
        pass
    
    try:
        answer = await ai.answer_question(text, user.first_name, chat.title)
        
        await message.reply_text(
            f"🤖 <b>{BOT_NAME}:</b>\n\n{answer}",
            parse_mode=ParseMode.HTML
        )
        
        db.log_event("ai_answer", chat.id, user.id, {"question": text[:100]})
        
    except Exception as e:
        logger.error(f"AI answer error: {e}")
        await message.reply_text(
            "⚠️ Kuch technical issue aa gaya! Thodi der baad try karo. 🙏"
        )

# ════════════════════════════════════════════════════════════════
#                    ADMIN COMMANDS
# ════════════════════════════════════════════════════════════════

async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ban a user. Usage: /ban @username reason"""
    if not await is_admin_or_owner(update, context, update.effective_user.id):
        await update.message.reply_text("❌ Sirf admins ye command use kar sakte hain!")
        return
    
    target_user = None
    reason = "Admin ban"
    
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        if context.args:
            reason = " ".join(context.args)
    elif context.args:
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else reason
    
    if not target_user:
        await update.message.reply_text("❌ Reply karke use karo ya username mention karo!\nUsage: /ban (reply) [reason]")
        return
    
    if await is_admin_or_owner(update, context, target_user.id):
        await update.message.reply_text("❌ Admin ko ban nahi kar sakte!")
        return
    
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target_user.id)
        await update.message.reply_text(
            f"✅ <b>Banned!</b>\n"
            f"👤 User: <a href='tg://user?id={target_user.id}'>{target_user.first_name}</a>\n"
            f"📝 Reason: {reason}\n"
            f"👮 By: {update.effective_user.first_name}"
        )
        db.log_event("admin_ban", update.effective_chat.id, target_user.id, {"reason": reason})
    except TelegramError as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unban a user."""
    if not await is_admin_or_owner(update, context, update.effective_user.id):
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /unban [user_id]")
        return
    
    try:
        user_id = int(context.args[0])
        await context.bot.unban_chat_member(update.effective_chat.id, user_id)
        await update.message.reply_text(f"✅ User <code>{user_id}</code> unbanned successfully!")
        db.reset_warnings(update.effective_chat.id, user_id)
    except (ValueError, TelegramError) as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mute a user. Usage: /mute [minutes] reason"""
    if not await is_admin_or_owner(update, context, update.effective_user.id):
        return
    
    target_user = None
    duration = MUTE_DURATION_MINUTES
    reason = "Admin mute"
    
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        if context.args:
            try:
                duration = int(context.args[0])
                reason = " ".join(context.args[1:]) if len(context.args) > 1 else reason
            except ValueError:
                reason = " ".join(context.args)
    
    if not target_user:
        await update.message.reply_text("❌ Reply karke use karo!\nUsage: /mute (reply) [minutes] [reason]")
        return
    
    if await is_admin_or_owner(update, context, target_user.id):
        await update.message.reply_text("❌ Admin ko mute nahi kar sakte!")
        return
    
    mute_until = datetime.now() + timedelta(minutes=duration)
    
    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id, target_user.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=mute_until
        )
        await update.message.reply_text(
            f"🔇 <b>Muted!</b>\n"
            f"👤 User: <a href='tg://user?id={target_user.id}'>{target_user.first_name}</a>\n"
            f"⏱ Duration: {duration} minutes\n"
            f"📝 Reason: {reason}\n"
            f"👮 By: {update.effective_user.first_name}"
        )
        db.log_event("admin_mute", update.effective_chat.id, target_user.id, {"duration": duration, "reason": reason})
    except TelegramError as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unmute a user."""
    if not await is_admin_or_owner(update, context, update.effective_user.id):
        return
    
    target_user = None
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
    
    if not target_user:
        await update.message.reply_text("❌ Reply karke use karo!")
        return
    
    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id, target_user.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_change_info=False,
                can_invite_users=True,
                can_pin_messages=False
            )
        )
        await update.message.reply_text(
            f"🔊 <b>Unmuted!</b>\n"
            f"👤 User: <a href='tg://user?id={target_user.id}'>{target_user.first_name}</a>"
        )
    except TelegramError as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually warn a user."""
    if not await is_admin_or_owner(update, context, update.effective_user.id):
        return
    
    target_user = None
    reason = "Admin warning"
    
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        if context.args:
            reason = " ".join(context.args)
    
    if not target_user:
        await update.message.reply_text("❌ Reply karke use karo!")
        return
    
    if await is_admin_or_owner(update, context, target_user.id):
        await update.message.reply_text("❌ Admin ko warn nahi kar sakte!")
        return
    
    warnings = db.add_warning(update.effective_chat.id, target_user.id)
    
    if warnings >= MAX_WARNINGS:
        await context.bot.ban_chat_member(update.effective_chat.id, target_user.id)
        await update.message.reply_text(
            f"🚫 <b>Warning + Auto-Ban!</b>\n"
            f"👤 User: {target_user.first_name}\n"
            f"⚠️ Warnings: {warnings}/{MAX_WARNINGS}\n"
            f"📝 Reason: {reason}"
        )
        db.reset_warnings(update.effective_chat.id, target_user.id)
    else:
        await update.message.reply_text(
            f"⚠️ <b>Warning!</b>\n"
            f"👤 User: {target_user.first_name}\n"
            f"⚠️ Warnings: {warnings}/{MAX_WARNINGS}\n"
            f"📝 Reason: {reason}"
        )


async def cmd_warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check warnings of a user."""
    target_user = None
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
    elif context.args:
        try:
            user_id = int(context.args[0])
            target_user = type('obj', (object,), {'id': user_id, 'first_name': str(user_id)})()
        except ValueError:
            pass
    else:
        target_user = update.effective_user
    
    if not target_user:
        await update.message.reply_text("❌ User specify karo!")
        return
    
    warnings = db.get_warnings(update.effective_chat.id, target_user.id)
    await update.message.reply_text(
        f"📊 <b>Warning Status</b>\n"
        f"👤 User: {target_user.first_name}\n"
        f"⚠️ Warnings: {warnings}/{MAX_WARNINGS}\n"
        f"{'✅ Clean record!' if warnings == 0 else '🔴 Has violations!'}"
    )


async def cmd_resetwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset warnings of a user."""
    if not await is_admin_or_owner(update, context, update.effective_user.id):
        return
    
    target_user = None
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
    
    if not target_user:
        await update.message.reply_text("❌ Reply karke use karo!")
        return
    
    db.reset_warnings(update.effective_chat.id, target_user.id)
    await update.message.reply_text(
        f"✅ <b>Warnings Reset!</b>\n"
        f"👤 User: {target_user.first_name}\n"
        f"🧹 All warnings cleared!"
    )


async def cmd_kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kick (not ban) a user."""
    if not await is_admin_or_owner(update, context, update.effective_user.id):
        return
    
    target_user = None
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
    
    if not target_user:
        await update.message.reply_text("❌ Reply karke use karo!")
        return
    
    if await is_admin_or_owner(update, context, target_user.id):
        await update.message.reply_text("❌ Admin ko kick nahi kar sakte!")
        return
    
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target_user.id)
        await context.bot.unban_chat_member(update.effective_chat.id, target_user.id)
        await update.message.reply_text(
            f"👟 <b>Kicked!</b>\n"
            f"👤 User: {target_user.first_name}\n"
            f"ℹ️ User can rejoin with invite link."
        )
    except TelegramError as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pin a message."""
    if not await is_admin_or_owner(update, context, update.effective_user.id):
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Pin karne ke liye message pe reply karo!")
        return
    
    try:
        await context.bot.pin_chat_message(
            update.effective_chat.id,
            update.message.reply_to_message.message_id
        )
        await update.message.reply_text("📌 Message pinned!")
    except TelegramError as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show group statistics."""
    if not await is_admin_or_owner(update, context, update.effective_user.id):
        return
    
    chat_id = update.effective_chat.id
    stats = db.get_stats(chat_id)
    
    await update.message.reply_text(
        f"📊 <b>Group Statistics</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ Total Warnings Given: {stats.get('warnings', 0)}\n"
        f"🚫 Total Bans: {stats.get('bans', 0)}\n"
        f"🔇 Total Mutes: {stats.get('mutes', 0)}\n"
        f"👥 Members Joined: {stats.get('joins', 0)}\n"
        f"🤖 AI Answers Given: {stats.get('ai_answers', 0)}\n"
        f"🗑️ Messages Deleted: {stats.get('deletions', 0)}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <i>Powered by {BOT_NAME}</i>"
    )


async def cmd_setrules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set group rules."""
    if not await is_admin_or_owner(update, context, update.effective_user.id):
        return
    
    if not context.args:
        await update.message.reply_text(
            "Usage: /setrules [rules text]\n"
            "Example: /setrules 1. No spam 2. Be respectful"
        )
        return
    
    rules = " ".join(context.args)
    db.set_rules(update.effective_chat.id, rules)
    await update.message.reply_text("✅ Group rules set successfully!")


async def cmd_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show group rules."""
    rules = db.get_rules(update.effective_chat.id)
    
    if not rules:
        rules = (
            "1. 🚫 No adult/NSFW content\n"
            "2. 🤬 No abuse or offensive language\n"
            "3. 📢 No spam or promotions\n"
            "4. 🤝 Be respectful to everyone\n"
            "5. 🇮🇳 Hindi/English only"
        )
    
    await update.message.reply_text(
        f"📋 <b>Group Rules</b>\n\n{rules}\n\n"
        f"⚠️ Rules violate karne par AI automatic action lega!"
    )


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast a message to the group. (Bot owner only)"""
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /broadcast [message]")
        return
    
    msg = " ".join(context.args)
    await safe_send(
        context, update.effective_chat.id,
        f"📢 <b>Announcement</b>\n\n{msg}\n\n"
        f"— {BOT_NAME} 🤖"
    )


async def cmd_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Directly ask AI a question."""
    if not context.args:
        await update.message.reply_text(
            f"🤖 <b>{BOT_NAME} AI Assistant</b>\n\n"
            "Mujhse koi bhi sawaal pucho!\n"
            "Usage: /ai [apna sawaal]\n\n"
            "Example: /ai Python mein for loop kaise likhte hain?"
        )
        return
    
    question = " ".join(context.args)
    await context.bot.send_chat_action(update.effective_chat.id, action="typing")
    
    try:
        answer = await ai.answer_question(
            question,
            update.effective_user.first_name,
            update.effective_chat.title
        )
        await update.message.reply_text(
            f"🤖 <b>{BOT_NAME}:</b>\n\n{answer}"
        )
    except Exception as e:
        await update.message.reply_text("⚠️ AI currently unavailable. Try again later!")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help menu."""
    is_admin = await is_admin_or_owner(update, context, update.effective_user.id)
    
    user_cmds = (
        f"🤖 <b>{BOT_NAME} - Help Menu</b>\n\n"
        f"<b>User Commands:</b>\n"
        f"/ai [sawaal] — AI se kuch bhi pucho\n"
        f"/rules — Group rules dekho\n"
        f"/warnings — Apni warnings check karo\n"
        f"/help — Ye menu\n\n"
        f"💡 <i>Mujhe tag karo ya reply karo sawaal ke liye!</i>"
    )
    
    admin_cmds = (
        f"\n\n<b>Admin Commands:</b>\n"
        f"/ban — User ko ban karo (reply)\n"
        f"/unban [id] — User unban karo\n"
        f"/mute [mins] — User mute karo (reply)\n"
        f"/unmute — User unmute karo (reply)\n"
        f"/kick — User kick karo (reply)\n"
        f"/warn — Manual warning do (reply)\n"
        f"/resetwarn — Warnings clear karo (reply)\n"
        f"/pin — Message pin karo (reply)\n"
        f"/stats — Group statistics\n"
        f"/setrules [rules] — Rules set karo\n"
        f"/broadcast [msg] — Announcement karo"
    )
    
    await update.message.reply_text(
        user_cmds + (admin_cmds if is_admin else "")
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command."""
    keyboard = [
        [InlineKeyboardButton("📋 Rules", callback_data="rules_0"),
         InlineKeyboardButton("❓ Help", callback_data="help_menu")],
        [InlineKeyboardButton("🤖 Ask AI", callback_data="ask_ai")]
    ]
    
    await update.message.reply_text(
        f"🤖 <b>Namaste! Main hoon {BOT_NAME}</b>\n\n"
        f"Main is group/channel ka AI Controller hoon.\n\n"
        f"<b>Meri powers:</b>\n"
        f"✅ Adult/Gali words auto-delete\n"
        f"✅ 3 warnings ke baad auto-ban\n"
        f"✅ AI se koi bhi sawaal pucho\n"
        f"✅ New members ka welcome\n"
        f"✅ Deleted accounts auto-remove\n"
        f"✅ Smart moderation 24/7\n\n"
        f"💬 /ai [sawaal] likhkar mujhse kuch bhi pucho!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ════════════════════════════════════════════════════════════════
#                  CALLBACK QUERY HANDLERS
# ════════════════════════════════════════════════════════════════

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button callbacks."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("rules_"):
        chat_id = int(data.split("_")[1]) if data.split("_")[1] != "0" else query.message.chat_id
        rules = db.get_rules(chat_id) or (
            "1. 🚫 No adult/NSFW content\n"
            "2. 🤬 No gali ya offensive language\n"
            "3. 📢 No spam\n"
            "4. 🤝 Sabse respect karo\n"
            "5. 3 warnings = Auto Ban 🔨"
        )
        await query.message.reply_text(f"📋 <b>Group Rules</b>\n\n{rules}")
    
    elif data == "help_menu":
        await query.message.reply_text(
            f"🤖 <b>{BOT_NAME} Commands</b>\n\n"
            f"/ai [sawaal] — AI se pucho\n"
            f"/rules — Rules dekho\n"
            f"/warnings — Apni warnings\n"
            f"/help — Full help menu"
        )
    
    elif data == "ask_ai":
        await query.message.reply_text(
            "🤖 AI se sawaal karne ke liye:\n"
            "/ai [apna sawaal]\n\n"
            "Ya mujhe tag karo: @BotUsername [sawaal]"
        )


# ════════════════════════════════════════════════════════════════
#                      MAIN APPLICATION
# ════════════════════════════════════════════════════════════════

def main():
    """Start the bot."""
    logger.info(f"Starting {BOT_NAME}...")
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # ── Command Handlers ─────────────────────────────────────────
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("ai", cmd_ai))
    app.add_handler(CommandHandler("rules", cmd_rules))
    app.add_handler(CommandHandler("setrules", cmd_setrules))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))
    app.add_handler(CommandHandler("mute", cmd_mute))
    app.add_handler(CommandHandler("unmute", cmd_unmute))
    app.add_handler(CommandHandler("kick", cmd_kick))
    app.add_handler(CommandHandler("warn", cmd_warn))
    app.add_handler(CommandHandler("warnings", cmd_warnings))
    app.add_handler(CommandHandler("resetwarn", cmd_resetwarn))
    app.add_handler(CommandHandler("pin", cmd_pin))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    
    # ── Message Handler ──────────────────────────────────────────
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        moderate_message
    ))
    
    # ── New Member Handler ───────────────────────────────────────
    app.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS,
        handle_new_member
    ))
    
    # ── Callback Handler ─────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    logger.info("✅ Bot started successfully!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
