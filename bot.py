"""
AI CONTROLLER BOT v2.0 - Professional Edition
Full AI-powered Group/Channel Management System
"""

import logging
import asyncio
from datetime import datetime, timedelta

from telegram import (
    Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.constants import ParseMode, ChatMemberStatus
from telegram.error import TelegramError

from config import (
    BOT_TOKEN, GROK_API_KEY, GROK_MODEL,
    MAX_WARNINGS, MUTE_DURATION_MINUTES,
    ADMIN_IDS, BOT_NAME, SUPPORT_CHANNEL,
    BOT_USERNAME, BANNER_IMAGE_URL
)
from database import db
from ai_engine import AIEngine

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)
ai = AIEngine(GROK_API_KEY, GROK_MODEL)

# ── UI Helpers ───────────────────────────────────────────────────
def D(): return "━━━━━━━━━━━━━━━━━━━━━━"
def H(t): return f"<b>{D()}\n  {t}\n{D()}</b>"

# ── Permission Helpers ───────────────────────────────────────────
async def is_admin(ctx, chat_id, user_id):
    if user_id in ADMIN_IDS: return True
    try:
        m = await ctx.bot.get_chat_member(chat_id, user_id)
        return m.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except: return False

async def get_status(ctx, chat_id, user_id):
    try:
        m = await ctx.bot.get_chat_member(chat_id, user_id)
        return m.status
    except: return None

async def safe_send(ctx, cid, text, **kw):
    try:
        return await ctx.bot.send_message(cid, text, parse_mode=ParseMode.HTML, **kw)
    except TelegramError as e: logger.error(f"Send error: {e}")

async def safe_delete(msg):
    try: await msg.delete()
    except: pass

async def get_target(update):
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user
    return None

# ════════════════════════════════════════════════════════════════
#  /start - Professional Banner + Buttons
# ════════════════════════════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    kb = [
        [InlineKeyboardButton(
            "Add me to your Group",
            url=f"https://t.me/{BOT_USERNAME}?startgroup=true"
        )],
        [
            InlineKeyboardButton("Support Channel", url=f"https://t.me/{SUPPORT_CHANNEL}"),
            InlineKeyboardButton("Help", callback_data="cb_help")
        ],
        [
            InlineKeyboardButton("Commands", callback_data="cb_commands"),
            InlineKeyboardButton("About", callback_data="cb_about")
        ]
    ]
    text = (
        f"{H('AI CONTROLLER  v2.0')}\n\n"
        f"<b>Status</b>      Online\n"
        f"<b>AI Engine</b>   Groq Llama 3.3 70B\n"
        f"<b>Version</b>     2.0 Professional\n\n"
        f"{D()}\n<b>Features</b>\n{D()}\n"
        f"  Auto content moderation\n"
        f"  Warning / Mute / Ban / Kick\n"
        f"  AI question answering\n"
        f"  Smart welcome messages\n"
        f"  Ghost account removal\n"
        f"  Broadcast to all groups\n"
        f"  Full admin command suite\n\n"
        f"{D()}"
    )
    try:
        if BANNER_IMAGE_URL:
            await ctx.bot.send_photo(
                chat.id, photo=BANNER_IMAGE_URL,
                caption=text, parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(kb)
            )
            return
    except: pass
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))

# ════════════════════════════════════════════════════════════════
#  WELCOME
# ════════════════════════════════════════════════════════════════
async def handle_new_member(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    for m in update.message.new_chat_members:
        uid, name = m.id, m.first_name or "User"
        # Remove deleted accounts
        if name in ["", "Deleted Account"] and not m.username:
            try:
                await ctx.bot.ban_chat_member(chat.id, uid)
                await ctx.bot.unban_chat_member(chat.id, uid)
                await safe_send(ctx, chat.id,
                    f"{H('SYSTEM  |  Auto Removal')}\n\n"
                    f"<b>Action</b>   Deleted account removed\n"
                    f"<b>Reason</b>   Ghost/inactive account\n\n{D()}"
                )
                continue
            except: pass

        try:
            ai_msg = await ai.generate_response(
                f"Write a 2-line professional welcome for '{name}' joining '{chat.title}'. "
                f"No emojis. Formal but warm. English only."
            )
        except:
            ai_msg = f"Welcome to {chat.title}. Please review the group rules."

        kb = [[
            InlineKeyboardButton("Rules", callback_data=f"cb_rules_{chat.id}"),
            InlineKeyboardButton("Help", callback_data="cb_help")
        ]]
        await safe_send(ctx, chat.id,
            f"{H('NEW MEMBER')}\n\n"
            f"<b>User</b>    <a href='tg://user?id={uid}'>{name}</a>\n"
            f"<b>Group</b>   {chat.title}\n\n"
            f"{ai_msg}\n\n{D()}",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        db.log_event("join", chat.id, uid, {"name": name})
        db.add_chat(chat.id)

# ════════════════════════════════════════════════════════════════
#  MESSAGE HANDLER - Moderation + AI Reply
# ════════════════════════════════════════════════════════════════
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.edited_message
    if not msg or not msg.text: return
    chat, user = update.effective_chat, update.effective_user
    if not user: return

    db.add_chat(chat.id)
    db.add_user(user.id)

    # Admins skip moderation
    admin = await is_admin(ctx, chat.id, user.id)

    if not admin:
        # Moderation check
        v = await ai.check_content_violation(msg.text)
        if v.get("is_violation"):
            await handle_violation(update, ctx, user, chat, msg, v)
            return
        sp = await ai.analyze_spam(msg.text, 0)
        if sp.get("is_spam"):
            await handle_violation(update, ctx, user, chat, msg, {
                "type": "Spam / Promotion", "reason": sp.get("reason","Spam detected"), "is_violation": True
            })
            return

    # AI reply logic
    text = msg.text
    bot_un = ctx.bot.username or ""
    tagged = bot_un and f"@{bot_un}".lower() in text.lower()
    replied_to_bot = (
        msg.reply_to_message and
        msg.reply_to_message.from_user and
        msg.reply_to_message.from_user.id == ctx.bot.id
    )
    is_dm = chat.type == "private"
    is_q = await ai.is_question_needing_answer(text)

    if tagged or replied_to_bot or is_dm or is_q:
        clean = text.replace(f"@{bot_un}", "").strip() if bot_un else text
        if len(clean) > 1:
            await do_ai_reply(msg, ctx, user, chat, clean)

async def do_ai_reply(msg, ctx, user, chat, question):
    try:
        await ctx.bot.send_chat_action(chat.id, "typing")
        ans = await ai.answer_question(question, user.first_name, chat.title)
        await msg.reply_text(
            f"{H('AI RESPONSE')}\n\n{ans}\n\n{D()}",
            parse_mode=ParseMode.HTML
        )
        db.log_event("ai_answer", chat.id, user.id, {"q": question[:80]})
    except Exception as e:
        logger.error(f"AI error: {e}")

# ════════════════════════════════════════════════════════════════
#  VIOLATION HANDLER
# ════════════════════════════════════════════════════════════════
async def handle_violation(update, ctx, user, chat, msg, v):
    await safe_delete(msg)
    uid, cid = user.id, chat.id
    warns = db.add_warning(cid, uid)
    vtype = v.get("type","Policy Violation")
    reason = v.get("reason","Content policy violation")

    if warns >= MAX_WARNINGS:
        try:
            await ctx.bot.ban_chat_member(cid, uid)
            await safe_send(ctx, cid,
                f"{H('ACTION  |  User Banned')}\n\n"
                f"<b>User</b>       <a href='tg://user?id={uid}'>{user.first_name}</a>\n"
                f"<b>Violation</b>  {vtype}\n"
                f"<b>Reason</b>     {reason}\n"
                f"<b>Warnings</b>   {warns}/{MAX_WARNINGS}\n"
                f"<b>Result</b>     Permanently banned\n\n{D()}"
            )
            db.log_event("auto_ban", cid, uid, {"reason": reason})
            db.reset_warnings(cid, uid)
        except TelegramError as e: logger.error(e)

    elif warns == MAX_WARNINGS - 1:
        try:
            await ctx.bot.restrict_chat_member(
                cid, uid,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=datetime.now() + timedelta(minutes=MUTE_DURATION_MINUTES)
            )
            await safe_send(ctx, cid,
                f"{H('ACTION  |  Warning + Mute')}\n\n"
                f"<b>User</b>       <a href='tg://user?id={uid}'>{user.first_name}</a>\n"
                f"<b>Violation</b>  {vtype}\n"
                f"<b>Warning</b>    {warns}/{MAX_WARNINGS}  [FINAL]\n"
                f"<b>Muted</b>      {MUTE_DURATION_MINUTES} minutes\n"
                f"<b>Next</b>       Permanent ban\n\n{D()}"
            )
            db.log_event("auto_mute", cid, uid, {"reason": reason})
        except TelegramError as e: logger.error(e)
    else:
        await safe_send(ctx, cid,
            f"{H('WARNING  |  Policy Violation')}\n\n"
            f"<b>User</b>       <a href='tg://user?id={uid}'>{user.first_name}</a>\n"
            f"<b>Violation</b>  {vtype}\n"
            f"<b>Reason</b>     {reason}\n"
            f"<b>Count</b>      {warns}/{MAX_WARNINGS}\n"
            f"<b>Remaining</b>  {MAX_WARNINGS - warns} before ban\n\n{D()}"
        )
        db.log_event("warning", cid, uid, {"reason": reason, "count": warns})

# ════════════════════════════════════════════════════════════════
#  ADMIN COMMANDS
# ════════════════════════════════════════════════════════════════
async def cmd_ban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(ctx, update.effective_chat.id, update.effective_user.id):
        return
    t = await get_target(update)
    if not t: return await update.message.reply_text("Reply to a user.")
    if await is_admin(ctx, update.effective_chat.id, t.id):
        return await update.message.reply_text(f"{H('ERROR')}\n\nCannot take action on an admin.\n\n{D()}")
    reason = " ".join(ctx.args) if ctx.args else "Admin action"
    try:
        await ctx.bot.ban_chat_member(update.effective_chat.id, t.id)
        await update.message.reply_text(
            f"{H('ACTION  |  Ban')}\n\n"
            f"<b>User</b>     <a href='tg://user?id={t.id}'>{t.first_name}</a>\n"
            f"<b>Reason</b>   {reason}\n"
            f"<b>By</b>       {update.effective_user.first_name}\n"
            f"<b>Status</b>   Banned\n\n{D()}", parse_mode=ParseMode.HTML
        )
        db.log_event("admin_ban", update.effective_chat.id, t.id, {"reason": reason})
    except TelegramError as e: await update.message.reply_text(f"Error: {e}")

async def cmd_unban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(ctx, update.effective_chat.id, update.effective_user.id): return
    if not ctx.args: return await update.message.reply_text("Usage: /unban [user_id]")
    try:
        uid = int(ctx.args[0])
        await ctx.bot.unban_chat_member(update.effective_chat.id, uid)
        db.reset_warnings(update.effective_chat.id, uid)
        await update.message.reply_text(
            f"{H('ACTION  |  Unban')}\n\n"
            f"<b>User ID</b>  <code>{uid}</code>\n"
            f"<b>By</b>       {update.effective_user.first_name}\n"
            f"<b>Status</b>   Unbanned\n\n{D()}", parse_mode=ParseMode.HTML
        )
    except (ValueError, TelegramError) as e: await update.message.reply_text(f"Error: {e}")

async def cmd_mute(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(ctx, update.effective_chat.id, update.effective_user.id): return
    t = await get_target(update)
    if not t: return await update.message.reply_text("Reply to a user.")
    if await is_admin(ctx, update.effective_chat.id, t.id):
        return await update.message.reply_text(f"{H('ERROR')}\n\nCannot mute an admin.\n\n{D()}")
    dur, reason = MUTE_DURATION_MINUTES, "Admin action"
    if ctx.args:
        try: dur = int(ctx.args[0]); reason = " ".join(ctx.args[1:]) or reason
        except: reason = " ".join(ctx.args)
    try:
        await ctx.bot.restrict_chat_member(
            update.effective_chat.id, t.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=datetime.now() + timedelta(minutes=dur)
        )
        await update.message.reply_text(
            f"{H('ACTION  |  Mute')}\n\n"
            f"<b>User</b>      <a href='tg://user?id={t.id}'>{t.first_name}</a>\n"
            f"<b>Duration</b>  {dur} minutes\n"
            f"<b>Reason</b>    {reason}\n"
            f"<b>By</b>        {update.effective_user.first_name}\n\n{D()}", parse_mode=ParseMode.HTML
        )
        db.log_event("admin_mute", update.effective_chat.id, t.id, {"dur": dur})
    except TelegramError as e: await update.message.reply_text(f"Error: {e}")

async def cmd_unmute(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(ctx, update.effective_chat.id, update.effective_user.id): return
    t = await get_target(update)
    if not t: return await update.message.reply_text("Reply to a user.")
    try:
        await ctx.bot.restrict_chat_member(
            update.effective_chat.id, t.id,
            permissions=ChatPermissions(
                can_send_messages=True, can_send_polls=True,
                can_send_other_messages=True, can_add_web_page_previews=True,
                can_invite_users=True
            )
        )
        await update.message.reply_text(
            f"{H('ACTION  |  Unmute')}\n\n"
            f"<b>User</b>    <a href='tg://user?id={t.id}'>{t.first_name}</a>\n"
            f"<b>By</b>      {update.effective_user.first_name}\n"
            f"<b>Status</b>  Unmuted\n\n{D()}", parse_mode=ParseMode.HTML
        )
    except TelegramError as e: await update.message.reply_text(f"Error: {e}")

async def cmd_kick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(ctx, update.effective_chat.id, update.effective_user.id): return
    t = await get_target(update)
    if not t: return await update.message.reply_text("Reply to a user.")
    if await is_admin(ctx, update.effective_chat.id, t.id):
        return await update.message.reply_text(f"{H('ERROR')}\n\nCannot kick an admin.\n\n{D()}")
    reason = " ".join(ctx.args) if ctx.args else "Admin action"
    try:
        await ctx.bot.ban_chat_member(update.effective_chat.id, t.id)
        await ctx.bot.unban_chat_member(update.effective_chat.id, t.id)
        await update.message.reply_text(
            f"{H('ACTION  |  Kick')}\n\n"
            f"<b>User</b>    <a href='tg://user?id={t.id}'>{t.first_name}</a>\n"
            f"<b>Reason</b>  {reason}\n"
            f"<b>By</b>      {update.effective_user.first_name}\n"
            f"<b>Note</b>    Can rejoin via invite link\n\n{D()}", parse_mode=ParseMode.HTML
        )
        db.log_event("kick", update.effective_chat.id, t.id, {"reason": reason})
    except TelegramError as e: await update.message.reply_text(f"Error: {e}")

async def cmd_warn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(ctx, update.effective_chat.id, update.effective_user.id): return
    t = await get_target(update)
    if not t: return await update.message.reply_text("Reply to a user.")
    if await is_admin(ctx, update.effective_chat.id, t.id):
        return await update.message.reply_text(f"{H('ERROR')}\n\nCannot warn an admin.\n\n{D()}")
    reason = " ".join(ctx.args) if ctx.args else "Admin warning"
    warns = db.add_warning(update.effective_chat.id, t.id)
    if warns >= MAX_WARNINGS:
        await ctx.bot.ban_chat_member(update.effective_chat.id, t.id)
        await update.message.reply_text(
            f"{H('ACTION  |  Warn + Auto Ban')}\n\n"
            f"<b>User</b>      {t.first_name}\n"
            f"<b>Warnings</b>  {warns}/{MAX_WARNINGS}\n"
            f"<b>Result</b>    Permanently banned\n\n{D()}", parse_mode=ParseMode.HTML
        )
        db.reset_warnings(update.effective_chat.id, t.id)
    else:
        await update.message.reply_text(
            f"{H('ACTION  |  Warning')}\n\n"
            f"<b>User</b>       <a href='tg://user?id={t.id}'>{t.first_name}</a>\n"
            f"<b>Reason</b>     {reason}\n"
            f"<b>Count</b>      {warns}/{MAX_WARNINGS}\n"
            f"<b>Remaining</b>  {MAX_WARNINGS - warns} before ban\n\n{D()}", parse_mode=ParseMode.HTML
        )

async def cmd_unwarn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(ctx, update.effective_chat.id, update.effective_user.id): return
    t = await get_target(update)
    if not t: return await update.message.reply_text("Reply to a user.")
    db.reset_warnings(update.effective_chat.id, t.id)
    await update.message.reply_text(
        f"{H('ACTION  |  Warnings Cleared')}\n\n"
        f"<b>User</b>    {t.first_name}\n"
        f"<b>Status</b>  All warnings removed\n\n{D()}", parse_mode=ParseMode.HTML
    )

async def cmd_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    t = await get_target(update) or update.effective_user
    chat = update.effective_chat
    warns = db.get_warnings(chat.id, t.id)
    status = await get_status(ctx, chat.id, t.id)
    await update.message.reply_text(
        f"{H('USER INFO')}\n\n"
        f"<b>Name</b>      {t.first_name} {t.last_name or ''}\n"
        f"<b>Username</b>  @{t.username or 'N/A'}\n"
        f"<b>ID</b>        <code>{t.id}</code>\n"
        f"<b>Status</b>    {status or 'Unknown'}\n"
        f"<b>Warnings</b>  {warns}/{MAX_WARNINGS}\n"
        f"<b>Bot</b>       {'Yes' if t.is_bot else 'No'}\n\n{D()}", parse_mode=ParseMode.HTML
    )

async def cmd_warnings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    t = await get_target(update) or update.effective_user
    w = db.get_warnings(update.effective_chat.id, t.id)
    await update.message.reply_text(
        f"{H('WARNING STATUS')}\n\n"
        f"<b>User</b>      {t.first_name}\n"
        f"<b>Warnings</b>  {w}/{MAX_WARNINGS}\n"
        f"<b>Record</b>    {'Clean' if w == 0 else 'Has violations'}\n\n{D()}", parse_mode=ParseMode.HTML
    )

async def cmd_pin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(ctx, update.effective_chat.id, update.effective_user.id): return
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to a message to pin.")
    try:
        await ctx.bot.pin_chat_message(update.effective_chat.id, update.message.reply_to_message.message_id)
        await update.message.reply_text(
            f"{H('ACTION  |  Message Pinned')}\n\n<b>By</b>  {update.effective_user.first_name}\n\n{D()}",
            parse_mode=ParseMode.HTML
        )
    except TelegramError as e: await update.message.reply_text(f"Error: {e}")

async def cmd_setrules(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(ctx, update.effective_chat.id, update.effective_user.id): return
    if not ctx.args: return await update.message.reply_text("Usage: /setrules [text]")
    db.set_rules(update.effective_chat.id, " ".join(ctx.args))
    await update.message.reply_text(
        f"{H('SETTINGS  |  Rules Updated')}\n\nGroup rules saved.\n\n{D()}", parse_mode=ParseMode.HTML
    )

async def cmd_rules(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    r = db.get_rules(update.effective_chat.id) or (
        f"1.  No abusive or offensive language\n"
        f"2.  No adult or NSFW content\n"
        f"3.  No spam or promotional links\n"
        f"4.  Respect all members\n"
        f"5.  Follow admin instructions\n"
        f"6.  {MAX_WARNINGS} violations = permanent ban"
    )
    await update.message.reply_text(f"{H('GROUP RULES')}\n\n{r}\n\n{D()}", parse_mode=ParseMode.HTML)

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(ctx, update.effective_chat.id, update.effective_user.id): return
    s = db.get_stats(update.effective_chat.id)
    await update.message.reply_text(
        f"{H('GROUP STATISTICS')}\n\n"
        f"<b>Warnings issued</b>   {s.get('warnings', 0)}\n"
        f"<b>Users banned</b>      {s.get('auto_ban', 0) + s.get('admin_ban', 0)}\n"
        f"<b>Users muted</b>       {s.get('auto_mute', 0) + s.get('admin_mute', 0)}\n"
        f"<b>Users kicked</b>      {s.get('kick', 0)}\n"
        f"<b>Members joined</b>    {s.get('join', 0)}\n"
        f"<b>AI responses</b>      {s.get('ai_answer', 0)}\n\n{D()}", parse_mode=ParseMode.HTML
    )

async def cmd_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(ctx, update.effective_chat.id, update.effective_user.id): return
    kb = [[InlineKeyboardButton("Close", callback_data="cb_close")]]
    await update.message.reply_text(
        f"{H('BOT SETTINGS')}\n\n"
        f"<b>Max warnings</b>    {MAX_WARNINGS}\n"
        f"<b>Mute duration</b>   {MUTE_DURATION_MINUTES} min\n"
        f"<b>AI moderation</b>   Active\n"
        f"<b>Auto-ban</b>        Active\n"
        f"<b>Ghost removal</b>   Active\n"
        f"<b>Broadcast</b>       Active\n\n{D()}",
        parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb)
    )

async def cmd_reload(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(ctx, update.effective_chat.id, update.effective_user.id): return
    await update.message.reply_text(
        f"{H('SYSTEM  |  Reloaded')}\n\nAdmin list refreshed.\n\n{D()}", parse_mode=ParseMode.HTML
    )

async def cmd_ai(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        return await update.message.reply_text(
            f"{H('AI ASSISTANT')}\n\nUsage:  /ai [question]\n\nExample:  /ai What is Python?\n\n{D()}",
            parse_mode=ParseMode.HTML
        )
    q = " ".join(ctx.args)
    await ctx.bot.send_chat_action(update.effective_chat.id, "typing")
    try:
        ans = await ai.answer_question(q, update.effective_user.first_name, update.effective_chat.title)
        await update.message.reply_text(
            f"{H('AI RESPONSE')}\n\n{ans}\n\n{D()}", parse_mode=ParseMode.HTML
        )
    except:
        await update.message.reply_text("AI is temporarily unavailable.")

# ════════════════════════════════════════════════════════════════
#  BROADCAST
# ════════════════════════════════════════════════════════════════
async def cmd_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text(f"{H('ERROR')}\n\nOwner only command.\n\n{D()}")
    if not ctx.args:
        return await update.message.reply_text(
            f"{H('BROADCAST')}\n\nUsage: /broadcast [message]\n\nSends to all groups where bot is active.\n\n{D()}",
            parse_mode=ParseMode.HTML
        )
    msg_text = " ".join(ctx.args)
    chats = db.get_all_chats()
    sent = failed = 0
    status = await update.message.reply_text(
        f"{H('BROADCAST  |  Sending...')}\n\nReaching {len(chats)} groups...\n\n{D()}",
        parse_mode=ParseMode.HTML
    )
    for cid in chats:
        try:
            await ctx.bot.send_message(
                cid,
                f"{H('BROADCAST')}\n\n{msg_text}\n\n<i>— {BOT_NAME}</i>\n{D()}",
                parse_mode=ParseMode.HTML
            )
            sent += 1
            await asyncio.sleep(0.1)
        except: failed += 1
    await status.edit_text(
        f"{H('BROADCAST  |  Complete')}\n\n"
        f"<b>Sent</b>     {sent} groups\n"
        f"<b>Failed</b>   {failed}\n"
        f"<b>Total</b>    {sent + failed}\n\n{D()}",
        parse_mode=ParseMode.HTML
    )

async def cmd_broadcastall(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    if not ctx.args: return await update.message.reply_text("Usage: /broadcastall [message]")
    msg_text = " ".join(ctx.args)
    users = db.get_all_users()
    sent = 0
    for uid in users:
        try:
            await ctx.bot.send_message(
                uid,
                f"{H('MESSAGE')}\n\n{msg_text}\n\n<i>— {BOT_NAME}</i>\n{D()}",
                parse_mode=ParseMode.HTML
            )
            sent += 1
            await asyncio.sleep(0.05)
        except: pass
    await update.message.reply_text(
        f"{H('BROADCAST  |  Users Done')}\n\n<b>Sent to</b>  {sent} users\n\n{D()}",
        parse_mode=ParseMode.HTML
    )

# ════════════════════════════════════════════════════════════════
#  TRACK CHATS/USERS
# ════════════════════════════════════════════════════════════════
async def track(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat: db.add_chat(update.effective_chat.id)
    if update.effective_user: db.add_user(update.effective_user.id)

# ════════════════════════════════════════════════════════════════
#  CALLBACKS
# ════════════════════════════════════════════════════════════════
async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data

    if d == "cb_help":
        await q.message.reply_text(
            f"{H('HELP')}\n\n"
            f"Tag me or reply to me to ask anything.\n"
            f"I respond using Groq AI.\n\n"
            f"/ai [question]  Direct AI query\n"
            f"/rules          View group rules\n"
            f"/warnings       Your warning status\n"
            f"/info           Your profile info\n\n{D()}",
            parse_mode=ParseMode.HTML
        )
    elif d == "cb_commands":
        await q.message.reply_text(
            f"{H('COMMAND LIST')}\n\n"
            f"<b>User Commands</b>\n"
            f"/ai [q]       Ask AI\n"
            f"/rules        Group rules\n"
            f"/warnings     Warning status\n"
            f"/info         Profile info\n\n"
            f"<b>Admin Commands</b>\n"
            f"/ban          Ban (reply)\n"
            f"/unban [id]   Unban by ID\n"
            f"/mute [min]   Mute (reply)\n"
            f"/unmute       Unmute (reply)\n"
            f"/kick         Kick (reply)\n"
            f"/warn         Warn (reply)\n"
            f"/unwarn       Clear warns (reply)\n"
            f"/pin          Pin message (reply)\n"
            f"/info         User info (reply)\n"
            f"/stats        Statistics\n"
            f"/setrules     Set rules\n"
            f"/settings     Bot settings\n"
            f"/reload       Reload admins\n\n"
            f"<b>Owner Commands</b>\n"
            f"/broadcast    Send to all groups\n"
            f"/broadcastall Send to all users\n\n{D()}",
            parse_mode=ParseMode.HTML
        )
    elif d == "cb_about":
        await q.message.reply_text(
            f"{H('ABOUT')}\n\n"
            f"<b>Name</b>       {BOT_NAME}\n"
            f"<b>Version</b>    2.0 Professional\n"
            f"<b>AI Engine</b>  Groq / Llama 3.3 70B\n"
            f"<b>Platform</b>   Railway\n\n"
            f"Full AI-powered group management system.\n"
            f"Moderation, Q&A, broadcast and more.\n\n{D()}",
            parse_mode=ParseMode.HTML
        )
    elif d.startswith("cb_rules"):
        parts = d.split("_")
        cid = int(parts[2]) if len(parts) > 2 and parts[2] not in ["0",""] else q.message.chat_id
        r = db.get_rules(cid) or (
            f"1.  No abusive language\n2.  No adult content\n"
            f"3.  No spam\n4.  Respect members\n"
            f"5.  {MAX_WARNINGS} violations = ban"
        )
        await q.message.reply_text(f"{H('GROUP RULES')}\n\n{r}\n\n{D()}", parse_mode=ParseMode.HTML)
    elif d == "cb_close":
        try: await q.message.delete()
        except: pass

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("Commands", callback_data="cb_commands"),
         InlineKeyboardButton("About", callback_data="cb_about")],
        [InlineKeyboardButton("Support", url=f"https://t.me/{SUPPORT_CHANNEL}")]
    ]
    await update.message.reply_text(
        f"{H('HELP CENTER')}\n\nUse /ai [question] to ask anything.\nSee commands list below.\n\n{D()}",
        parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb)
    )

# ════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════
def main():
    logger.info(f"Starting {BOT_NAME} v2.0 Professional...")
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.ALL, track), group=-1)
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
    app.add_handler(CommandHandler("unwarn", cmd_unwarn))
    app.add_handler(CommandHandler("warnings", cmd_warnings))
    app.add_handler(CommandHandler("info", cmd_info))
    app.add_handler(CommandHandler("pin", cmd_pin))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("reload", cmd_reload))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("broadcastall", cmd_broadcastall))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_member))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info(f"{BOT_NAME} v2.0 ready!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
