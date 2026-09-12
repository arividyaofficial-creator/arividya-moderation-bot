

"""
ARIvidya Group Moderation Bot
------------------------------
Features:
  /mute @user [minutes]   - restrict a user from sending messages (admin only)
  /unmute @user           - remove mute (admin only)
  /ban @user              - ban + remove a user (admin only)
  /unban @user            - unban a user (admin only)
  /purge                  - reply to a message with /purge to delete everything
                             from that message up to your /purge command (admin only)
  /nightmode on|off       - instantly lock/unlock the group for everyone except admins
  /setwelcome <text>      - set the welcome message shown to new members
                             (use {name} to insert the new member's name)
  /setbye <text>          - set the message shown when a member leaves
  /settings               - show current settings for this group

Settings are saved per-group in settings.json so you only configure once.
"""

import json
import logging
import os
from pathlib import Path

from telegram import Update, ChatPermissions
from telegram.ext import (
    Application,
    CommandHandler,
    ChatMemberHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------
# Put your bot token here, or set it as an environment variable BOT_TOKEN
BOT_TOKEN = os.environ.get("BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")

SETTINGS_FILE = Path(__file__).parent / "settings.json"

DEFAULT_WELCOME = "Welcome {name}! 🎉 Glad to have you here."
DEFAULT_BYE = "{name} has left the group. 👋"

# ----------------------------------------------------------------------
# SETTINGS STORAGE (simple JSON file, one entry per chat)
# ----------------------------------------------------------------------
def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_settings(data: dict) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_chat_settings(chat_id: int) -> dict:
    data = load_settings()
    key = str(chat_id)
    if key not in data:
        data[key] = {
            "welcome": DEFAULT_WELCOME,
            "bye": DEFAULT_BYE,
            "night_mode": False,
        }
        save_settings(data)
    return data[key]


def update_chat_settings(chat_id: int, **kwargs) -> None:
    data = load_settings()
    key = str(chat_id)
    if key not in data:
        data[key] = {
            "welcome": DEFAULT_WELCOME,
            "bye": DEFAULT_BYE,
            "night_mode": False,
        }
    data[key].update(kwargs)
    save_settings(data)


# ----------------------------------------------------------------------
# HELPERS
# ----------------------------------------------------------------------
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check whether the person running the command is a group admin."""
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == "private":
        return True  # allow testing in DM
    member = await context.bot.get_chat_member(chat.id, user.id)
    return member.status in ("administrator", "creator")


async def get_target_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get the target user either from a reply or from @username argument."""
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user
    if context.args:
        username = context.args[0].lstrip("@")
        # Note: resolving @username -> user_id reliably requires the user
        # to have interacted with the bot/group before. Replying to their
        # message is the most reliable method.
        return None
    return None


# ----------------------------------------------------------------------
# COMMAND HANDLERS
# ----------------------------------------------------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi! I'm the ARIvidya moderation bot. Add me as admin in your group "
        "and use /settings to see available commands."
    )


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    s = get_chat_settings(chat.id)
    text = (
        "⚙️ Current Settings\n\n"
        f"Welcome message: {s['welcome']}\n\n"
        f"Bye message: {s['bye']}\n\n"
        f"Night mode: {'ON 🌙' if s['night_mode'] else 'OFF ☀️'}\n\n"
        "Commands:\n"
        "/mute (reply to user) [minutes]\n"
        "/unmute (reply to user)\n"
        "/ban (reply to user)\n"
        "/unban <user_id>\n"
        "/purge (reply to the first message to delete)\n"
        "/nightmode on|off\n"
        "/setwelcome <text>  (use {name} for the member's name)\n"
        "/setbye <text>"
    )
    await update.message.reply_text(text)


async def mute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Only admins can use this command.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to the user's message with /mute [minutes].")
        return

    target = update.message.reply_to_message.from_user
    minutes = None
    if context.args:
        try:
            minutes = int(context.args[0])
        except ValueError:
            pass

    until_date = None
    if minutes:
        import time
        until_date = int(time.time()) + minutes * 60

    await context.bot.restrict_chat_member(
        chat_id=update.effective_chat.id,
        user_id=target.id,
        permissions=ChatPermissions(can_send_messages=False),
        until_date=until_date,
    )
    label = f"for {minutes} minute(s)" if minutes else "indefinitely"
    await update.message.reply_text(f"🔇 {target.first_name} has been muted {label}.")


async def unmute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Only admins can use this command.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to the user's message with /unmute.")
        return

    target = update.message.reply_to_message.from_user
    await context.bot.restrict_chat_member(
        chat_id=update.effective_chat.id,
        user_id=target.id,
        permissions=ChatPermissions(
            can_send_messages=True,
            can_send_photos=True,
            can_send_videos=True,
            can_send_other_messages=True,
        ),
    )
    await update.message.reply_text(f"🔊 {target.first_name} has been unmuted.")


async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Only admins can use this command.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to the user's message with /ban.")
        return

    target = update.message.reply_to_message.from_user
    await context.bot.ban_chat_member(update.effective_chat.id, target.id)
    await update.message.reply_text(f"⛔ {target.first_name} has been banned.")


async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Only admins can use this command.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    user_id = int(context.args[0])
    await context.bot.unban_chat_member(update.effective_chat.id, user_id)
    await update.message.reply_text(f"✅ User {user_id} has been unbanned.")


async def purge_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Only admins can use this command.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "Reply to the first message you want deleted, then send /purge."
        )
        return

    chat_id = update.effective_chat.id
    start_id = update.message.reply_to_message.message_id
    end_id = update.message.message_id

    deleted = 0
    for msg_id in range(start_id, end_id + 1):
        try:
            await context.bot.delete_message(chat_id, msg_id)
            deleted += 1
        except Exception:
            pass  # message may already be gone or too old to delete

    logger.info(f"Purged {deleted} messages in chat {chat_id}")


async def nightmode_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Only admins can use this command.")
        return
    if not context.args or context.args[0].lower() not in ("on", "off"):
        await update.message.reply_text("Usage: /nightmode on  OR  /nightmode off")
        return

    turn_on = context.args[0].lower() == "on"
    chat_id = update.effective_chat.id

    if turn_on:
        await context.bot.set_chat_permissions(
            chat_id, ChatPermissions(can_send_messages=False)
        )
        await update.message.reply_text("🌙 Night mode ON — group is now read-only.")
    else:
        await context.bot.set_chat_permissions(
            chat_id,
            ChatPermissions(
                can_send_messages=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_other_messages=True,
            ),
        )
        await update.message.reply_text("☀️ Night mode OFF — group is open again.")

    update_chat_settings(chat_id, night_mode=turn_on)


async def setwelcome_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Only admins can use this command.")
        return
    text = update.message.text.split(" ", 1)
    if len(text) < 2:
        await update.message.reply_text(
            "Usage: /setwelcome Welcome {name} to ARIvidya! 🎉"
        )
        return
    update_chat_settings(update.effective_chat.id, welcome=text[1])
    await update.message.reply_text("✅ Welcome message updated.")


async def setbye_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Only admins can use this command.")
        return
    text = update.message.text.split(" ", 1)
    if len(text) < 2:
        await update.message.reply_text("Usage: /setbye {name} left the group.")
        return
    update_chat_settings(update.effective_chat.id, bye=text[1])
    await update.message.reply_text("✅ Bye message updated.")


# ----------------------------------------------------------------------
# WELCOME / BYE ON MEMBER JOIN-LEAVE
# ----------------------------------------------------------------------
# Two separate mechanisms exist in Telegram for tracking join/leave:
#   1. Classic message-based updates (new_chat_members / left_chat_member)
#      - reliable when a user joins/leaves themselves via a visible action.
#   2. chat_member updates (ChatMemberHandler)
#      - the modern, more reliable way Telegram reports membership changes,
#        especially when an ADMIN removes/kicks a real user. Some admin
#        actions on human members are only reported this way, not as a
#        classic message.
# We handle both, with a de-duplication guard so a single join/leave
# doesn't trigger two welcome/bye messages if both update types fire.

_recent_events = set()  # (chat_id, user_id, "join"/"leave") seen in the last few seconds


def _already_handled(chat_id: int, user_id: int, kind: str) -> bool:
    key = (chat_id, user_id, kind)
    if key in _recent_events:
        return True
    _recent_events.add(key)
    # simple cleanup so this set doesn't grow forever
    if len(_recent_events) > 500:
        _recent_events.clear()
    return False


async def greet_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    s = get_chat_settings(chat_id)
    for member in update.message.new_chat_members:
        if _already_handled(chat_id, member.id, "join"):
            continue
        name = member.first_name or member.username or "there"
        await update.message.reply_text(s["welcome"].format(name=name))


async def say_bye(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    s = get_chat_settings(chat_id)
    member = update.message.left_chat_member
    if member:
        if _already_handled(chat_id, member.id, "leave"):
            return
        name = member.first_name or member.username or "Someone"
        await update.message.reply_text(s["bye"].format(name=name))


async def track_membership_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Catches join/leave/kick events via the modern chat_member update,
    which Telegram sends more reliably than classic messages -
    especially when an admin removes a real (non-bot) member."""
    result = update.chat_member
    if not result:
        return

    chat_id = update.effective_chat.id
    user = result.new_chat_member.user
    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status
    s = get_chat_settings(chat_id)

    joined_statuses = ("member", "restricted", "administrator")
    left_statuses = ("left", "kicked")

    # Someone joined
    if old_status in left_statuses and new_status in joined_statuses:
        if _already_handled(chat_id, user.id, "join"):
            return
        name = user.first_name or user.username or "there"
        await context.bot.send_message(chat_id, s["welcome"].format(name=name))

    # Someone left or was removed/banned
    elif old_status in joined_statuses and new_status in left_statuses:
        if _already_handled(chat_id, user.id, "leave"):
            return
        name = user.first_name or user.username or "Someone"
        await context.bot.send_message(chat_id, s["bye"].format(name=name))


# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------
def main():
    if BOT_TOKEN == "PUT_YOUR_BOT_TOKEN_HERE":
        print("⚠️  Set your BOT_TOKEN (env variable or in the file) before running.")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("mute", mute_cmd))
    app.add_handler(CommandHandler("unmute", unmute_cmd))
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("unban", unban_cmd))
    app.add_handler(CommandHandler("purge", purge_cmd))
    app.add_handler(CommandHandler("nightmode", nightmode_cmd))
    app.add_handler(CommandHandler("setwelcome", setwelcome_cmd))
    app.add_handler(CommandHandler("setbye", setbye_cmd))

    from telegram.ext import MessageHandler

    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, greet_new_member))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, say_bye))
    app.add_handler(ChatMemberHandler(track_membership_change, ChatMemberHandler.CHAT_MEMBER))

    print("🤖 Bot is starting... (Ctrl+C to stop)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
  
