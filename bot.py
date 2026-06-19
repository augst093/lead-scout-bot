import asyncio
import os
import html
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
    MessageHandler, ContextTypes, filters
)
from utils import logger, setup_logging
import config
from database import (
    init_db, get_setting, save_setting, get_setting_int, 
    get_setting_bool, get_setting_list, get_all_settings,
    get_lead, update_lead_status, get_leads_by_status,
    get_top_leads, get_today_leads, get_next_unreviewed_lead,
    get_stats, clear_bad_leads, update_lead_custom_angle
)
from query_builder import build_queries
from search_engine import SearchAPIKeysMissing, BraveSearchAPIKeyMissing
from lead_parser import parse_lead
from scoring import score_lead, recommend_demo
# Outreach generation is handled inside scheduler.py via message_templates
from scheduler import setup_scheduler, build_lead_message_text, get_lead_inline_keyboard, run_search_for_niche_city
from export_csv import export_leads_to_csv

# Global logger initialization
setup_logging()

# ---------------------------------------------------------------------------
# Health-check HTTP server — keeps Render free tier from spinning down.
# UptimeRobot (free) pings /health every 5 min to maintain uptime.
# ---------------------------------------------------------------------------
class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass  # suppress HTTP access logs

def _start_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    logger.info(f"Health-check server listening on port {port}")
    server.serve_forever()

# --- Security Decorator / Helper ---

def admin_only(func):
    """Decorator to ensure only the configured admin can use the command/callback."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user or user.id != config.ADMIN_TELEGRAM_ID:
            logger.warning(f"Unauthorized access attempt by user ID: {user.id if user else 'Unknown'}")
            if update.message:
                await update.message.reply_text("⛔ Access denied.")
            elif update.callback_query:
                await update.callback_query.answer("⛔ Access denied.", show_alert=True)
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# --- Standard Commands ---

@admin_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends welcome message and main menu."""
    welcome_text = (
        "🚀 **Welcome to Lead Scout Bot!**\n\n"
        "I am your premium web design lead discovery assistant. I will search "
        "public web results, score candidates (0-10), and send high-quality leads here.\n\n"
        "💼 **Premium Demo Portfolios:**\n"
        "1. 🏋️ [Forge Method (Fitness)](https://forge-method.vercel.app/#results)\n"
        "2. 💅 [Muse Nail Atelier (Beauty)](https://muse-nail-atelier.vercel.app/)\n"
        "3. 🎨 [The Soft Edit (Creators)](https://the-soft-edit-nine.vercel.app/)\n\n"
        "🔍 Use /find for an interactive search, or type /help to view all commands."
    )
    
    # Simple inline buttons for quick actions
    keyboard = [
        [
            InlineKeyboardButton("🔍 Find Leads", callback_data="menu_find"),
            InlineKeyboardButton("📊 Stats", callback_data="menu_stats")
        ],
        [
            InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings"),
            InlineKeyboardButton("⏭️ Next Lead", callback_data="menu_next")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")

@admin_only
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Explains how to use the bot and lists commands."""
    help_text = (
        r"📖 **Lead Scout Bot Commands**" "\n\n"
        r"🔍 **Discovery Commands:**" "\n"
        r"• /find \- Start interactive search flow (choose niche, city, limit)" "\n"
        r"• /find\_fitness \{city\} \- Fast fitness search in a city" "\n"
        r"• /find\_nails \{city\} \- Fast nail tech search in a city" "\n"
        r"• /find\_creators \{city\} \- Fast creator search in a city" "\n\n"
        r"📂 **Review & Status Commands:**" "\n"
        r"• /next \- Review the next unreviewed lead" "\n"
        r"• /top \- View recently found top leads (score 8-10)" "\n"
        r"• /today \- View leads discovered today" "\n"
        r"• /saved \- View saved leads" "\n"
        r"• /messaged \- View leads marked as messaged" "\n"
        r"• /followups \- View leads scheduled for follow-up" "\n"
        r"• /clear\_bad \- Purge skipped/bad/low-scoring leads from DB" "\n\n"
        r"⚙️ **System & Settings:**" "\n"
        r"• /stats \- View lead count statistics" "\n"
        r"• /export \- Export all leads to CSV and send file" "\n"
        r"• /settings \- Open system configuration panel" "\n"
        r"• /search\_status \- Check background scheduler status" "\n"
        r"• /pause \- Pause background scheduled search" "\n"
        r"• /resume \- Resume background scheduled search" "\n\n"
        r"⚠️ _Note: This bot only aggregates public web index data. Auto-DMs are not supported._"
    )
    await update.message.reply_text(help_text, parse_mode="MarkdownV2")

# --- Discovery Operations ---

async def execute_fast_search(update: Update, context: ContextTypes.DEFAULT_TYPE, niche: str, city: str, limit: int = 10):
    """Executes a search query immediately and reports back to the admin."""
    chat_id = update.effective_chat.id
    # Send initial status
    status_msg = await update.message.reply_text(
        f"🔍 Searching for **{niche.capitalize()}** leads in **{city.capitalize()}** (max {limit})...\n"
        "Searching public web records. Progress will be sent in real-time...",
        parse_mode="Markdown"
    )
    
    min_score = get_setting_int("minimum_score", 7)
    
    try:
        leads = await run_search_for_niche_city(niche, city, limit, min_score, context=context, chat_id=chat_id)
        
        try:
            await status_msg.delete()
        except Exception:
            pass
            
        if not leads:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ No new leads found. Try a different city or check /search_status."
            )
            return
            
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ Done! Discovered and sent **{len(leads)}** new qualified leads (score >= {min_score}).",
            parse_mode="Markdown"
        )
        
    except (BraveSearchAPIKeyMissing, SearchAPIKeysMissing):
        await status_msg.edit_text(
            "⚠️ **Search Error:**\nSearch API credentials are missing. Add `GOOGLE_API_KEY`/`GOOGLE_CX` or `BRAVE_API_KEY` to your `.env` file."
        )
    except Exception as e:
        logger.error(f"Error executing search command: {e}")
        try:
            await status_msg.edit_text("❌ An unexpected error occurred during the search. Please check the logs.")
        except Exception:
            pass

@admin_only
async def find_fitness_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /find_fitness {city}."""
    if not context.args:
        await update.message.reply_text("✏️ Please specify a city. Example: `/find_fitness Dallas`", parse_mode="Markdown")
        return
    city = " ".join(context.args)
    await execute_fast_search(update, context, "fitness", city)

@admin_only
async def find_nails_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /find_nails {city}."""
    if not context.args:
        await update.message.reply_text("✏️ Please specify a city. Example: `/find_nails Miami`", parse_mode="Markdown")
        return
    city = " ".join(context.args)
    await execute_fast_search(update, context, "nails", city)

@admin_only
async def find_creators_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /find_creators {city}."""
    if not context.args:
        await update.message.reply_text("✏️ Please specify a city. Example: `/find_creators London`", parse_mode="Markdown")
        return
    city = " ".join(context.args)
    await execute_fast_search(update, context, "creators", city)

# --- Interactive Find Flow (/find) ---

@admin_only
async def find_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initializes the interactive lead generation setup flow."""
    context.user_data.clear() # Clear state
    
    keyboard = [
        [
            InlineKeyboardButton("🏋️ Fitness", callback_data="flow_niche_fitness"),
            InlineKeyboardButton("💅 Nails", callback_data="flow_niche_nails")
        ],
        [
            InlineKeyboardButton("🎨 Creators", callback_data="flow_niche_creators"),
            InlineKeyboardButton("🌟 All Niches", callback_data="flow_niche_all")
        ]
    ]
    
    target = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if target:
        await target.reply_text(
            "📂 **Select Niche:**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        logger.error("Could not find a valid message target in find_command")

# --- List Commands ---

@admin_only
async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays recently found high-scoring leads (8-10)."""
    leads = get_top_leads(8, 10)
    if not leads:
        await update.message.reply_text("📭 No top-rated leads (score 8-10) found in the database.")
        return
        
    response = "🏆 **Top Leads (Score 8-10)**\n\n"
    # Show top 10 recent
    for idx, lead in enumerate(leads[:10], 1):
        response += (
            f"{idx}. 🔥 **{lead['name']}** (Score: {lead['score']}/10)\n"
            f"   📍 {lead['city'].capitalize()} | Niche: {lead['niche'].capitalize()}\n"
            f"   🔗 [Open Link]({lead['url']}) | Status: {lead['status']}\n\n"
        )
    if len(leads) > 10:
        response += f"_...and {len(leads) - 10} more leads. Use /export to get the CSV._"
        
    await update.message.reply_text(response, parse_mode="Markdown", disable_web_page_preview=True)

@admin_only
async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays leads discovered today."""
    leads = get_today_leads()
    if not leads:
        await update.message.reply_text("📅 No leads discovered today yet.")
        return
        
    response = "📅 **Today's Discovered Leads**\n\n"
    for idx, lead in enumerate(leads[:15], 1):
        response += (
            f"{idx}. ⭐ **{lead['name']}** (Score: {lead['score']}/10)\n"
            f"   📍 {lead['city'].capitalize()} | {lead['niche'].capitalize()}\n"
            f"   🔗 [Open Link]({lead['url']}) | Status: {lead['status']}\n\n"
        )
    if len(leads) > 15:
        response += f"_...and {len(leads) - 15} more leads._"
        
    await update.message.reply_text(response, parse_mode="Markdown", disable_web_page_preview=True)

@admin_only
async def next_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the next unreviewed lead with full action options."""
    lead = get_next_unreviewed_lead()
    if not lead:
        await update.message.reply_text("🎉 All leads have been reviewed! No unreviewed leads in database.")
        return
        
    # Mark it as sent/viewed if it was in the initial 'new' state
    if lead["status"] == "new":
        update_lead_status(lead["id"], "sent_to_telegram")
        lead["status"] = "sent_to_telegram"
        
    text = build_lead_message_text(lead)
    reply_markup = get_lead_inline_keyboard(lead["id"], lead["url"], lead["recommended_demo"])
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")

@admin_only
async def saved_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists saved leads."""
    leads = get_leads_by_status("saved")
    if not leads:
        await update.message.reply_text("💾 No saved leads found.")
        return
        
    response = "💾 **Saved Leads**\n\n"
    for idx, lead in enumerate(leads[:15], 1):
        response += f"{idx}. **{lead['name']}** ({lead['score']}/10) - {lead['city'].capitalize()}\n   🔗 [Link]({lead['url']})\n"
    await update.message.reply_text(response, parse_mode="Markdown", disable_web_page_preview=True)

@admin_only
async def messaged_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists messaged leads."""
    leads = get_leads_by_status("messaged")
    if not leads:
        await update.message.reply_text("✉️ No messaged leads found.")
        return
        
    response = "✉️ **Messaged Leads**\n\n"
    for idx, lead in enumerate(leads[:15], 1):
        response += f"{idx}. **{lead['name']}** - {lead['city'].capitalize()}\n   🔗 [Link]({lead['url']})\n"
    await update.message.reply_text(response, parse_mode="Markdown", disable_web_page_preview=True)

@admin_only
async def followups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists follow-up candidates."""
    leads = get_leads_by_status("follow_up_needed")
    if not leads:
        await update.message.reply_text("📅 No leads pending follow-up.")
        return
        
    response = "📅 **Pending Follow-up Leads**\n\n"
    for idx, lead in enumerate(leads[:15], 1):
        response += (
            f"{idx}. **{lead['name']}** - {lead['city'].capitalize()}\n"
            f"   📅 Date: {lead['follow_up_date'] or 'Unscheduled'}\n"
            f"   🔗 [Link]({lead['url']})\n\n"
        )
    await update.message.reply_text(response, parse_mode="Markdown", disable_web_page_preview=True)

# --- Statistics & CSV Export ---

@admin_only
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Renders comprehensive SQLite lead database statistics."""
    stats = get_stats()
    
    total = stats.get("total", 0)
    today = stats.get("today", 0)
    
    statuses = stats.get("statuses", {})
    new_count = statuses.get("new", 0)
    sent_count = statuses.get("sent_to_telegram", 0)
    saved_count = statuses.get("saved", 0)
    skipped_count = statuses.get("skipped", 0)
    msg_count = statuses.get("messaged", 0)
    follow_count = statuses.get("follow_up_needed", 0)
    closed_count = statuses.get("closed", 0)
    bad_count = statuses.get("bad_lead", 0)
    
    niches = stats.get("niches", {})
    fit_count = niches.get("fitness", 0)
    nail_count = niches.get("nails", 0) + niches.get("beauty", 0)
    creator_count = niches.get("creators", 0) + niches.get("creator", 0)
    
    scores = stats.get("scores", {})
    s10 = scores.get(10, 0)
    s9 = scores.get(9, 0)
    s8 = scores.get(8, 0)
    s7 = scores.get(7, 0)
    s_low = sum(v for k, v in scores.items() if k < 7)
    
    stats_text = (
        "📊 **Lead Scout Database Statistics**\n\n"
        "📈 **Summary:**\n"
        f"• Total discovered: `{total}`\n"
        f"• Discovered today: `{today}`\n\n"
        "📁 **By Status:**\n"
        f"• 🆕 New: `{new_count}`\n"
        f"• 📤 Sent to Telegram: `{sent_count}`\n"
        f"• 💾 Saved: `{saved_count}`\n"
        f"• ⏭️ Skipped: `{skipped_count}`\n"
        f"• ✉️ Messaged: `{msg_count}`\n"
        f"• 📅 Follow-up: `{follow_count}`\n"
        f"• 🔒 Closed: `{closed_count}`\n"
        f"• 👎 Bad Leads: `{bad_count}`\n\n"
        "📂 **By Niche:**\n"
        f"• 🏋️ Fitness: `{fit_count}`\n"
        f"• 💅 Nails: `{nail_count}`\n"
        f"• 🎨 Creators: `{creator_count}`\n\n"
        "⭐ **By Score:**\n"
        f"• 10/10: `{s10}` | 9/10: `{s9}`\n"
        f"• 8/10: `{s8}` | 7/10: `{s7}`\n"
        f"• < 7/10: `{s_low}`"
    )
    await update.message.reply_text(stats_text, parse_mode="Markdown")

@admin_only
async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exports SQLite table to a CSV file and delivers it directly in Telegram."""
    filepath = "leads_export.csv"
    success = export_leads_to_csv(filepath)
    
    if not success:
        await update.message.reply_text("❌ Export failed: No leads in database or file system error.")
        return
        
    try:
        with open(filepath, "rb") as f:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=f,
                filename="leads_export.csv",
                caption="📊 Here is your exported leads database CSV file."
            )
        # Delete temporary file
        os.remove(filepath)
    except Exception as e:
        logger.error(f"Error sending exported CSV document: {e}")
        await update.message.reply_text("❌ Failed to deliver CSV document. See logs for details.")

@admin_only
async def clear_bad_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Purges bad/skipped records from SQLite."""
    deleted = clear_bad_leads()
    await update.message.reply_text(f"🧹 Database cleanup complete. Deleted **{deleted}** bad/skipped/low-scoring leads.", parse_mode="Markdown")

# --- Scheduler Configuration Commands ---

@admin_only
async def search_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tells the admin if scheduled repeating searches are active."""
    enabled = get_setting_bool("scheduled_search_enabled", False)
    frequency = get_setting_int("scheduled_search_frequency_hours", 2)
    cities = get_setting("default_cities", "None")
    niches = get_setting("enabled_niches", "None")
    
    if enabled:
        status = f"🟢 **Active** (repeating every {frequency} hours)"
    else:
        status = "🔴 **Paused / Disabled**"
        
    msg = (
        f"📅 **Scheduled Search Status:**\n\n"
        f"• Status: {status}\n"
        f"• Frequency: every {frequency} hours\n"
        f"• Targets: {niches.upper()} in {cities}\n\n"
        "Use /pause to disable or /resume to restart."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@admin_only
async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Disables the background scheduler."""
    save_setting("scheduled_search_enabled", False)
    setup_scheduler(context.application) # reload scheduler
    await update.message.reply_text("⏸️ Background scheduled searches have been paused/disabled.")

@admin_only
async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enables/resumes the background scheduler."""
    save_setting("scheduled_search_enabled", True)
    setup_scheduler(context.application) # reload scheduler
    await update.message.reply_text("▶️ Background scheduled searches have been resumed/enabled.")

# --- Settings Panels ---

@admin_only
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the current settings panel with adjustment buttons."""
    await send_settings_panel(update, context, False)

async def send_settings_panel(update: Update, context: ContextTypes.DEFAULT_TYPE, edit_message: bool = True):
    """Constructs and displays the interactive settings panel."""
    settings = get_all_settings()
    min_score = settings.get("minimum_score", "7")
    cities = settings.get("default_cities", "")
    niches = settings.get("enabled_niches", "")
    sched_enabled = settings.get("scheduled_search_enabled", "false").lower() == "true"
    frequency = settings.get("scheduled_search_frequency_hours", "2")
    max_leads = settings.get("max_leads_per_run", "10")
    
    status_emoji = "🟢 ON" if sched_enabled else "🔴 OFF"
    
    text = (
        "⚙️ **Lead Scout Configuration Panel**\n\n"
        f"• ⭐ **Minimum Score:** `{min_score}`\n"
        f"• 📍 **Default Cities:** `{cities}`\n"
        f"• 📂 **Enabled Niches:** `{niches}`\n"
        f"• ⏱️ **Scheduled Search:** `{status_emoji}`\n"
        f"• 🕒 **Scan Interval:** every `{frequency}` hours\n"
        f"• 🔢 **Max Leads/Run:** `{max_leads}`\n\n"
        "Select a button below to configure individual settings."
    )
    
    keyboard = [
        [
            InlineKeyboardButton("⭐ Change Min Score", callback_data="set_min_score"),
            InlineKeyboardButton("📍 Configure Cities", callback_data="set_cities")
        ],
        [
            InlineKeyboardButton("📂 Configure Niches", callback_data="set_niches"),
            InlineKeyboardButton(f"⏱️ Toggle Scheduler", callback_data="set_toggle_scheduler")
        ],
        [
            InlineKeyboardButton("🕒 Change Interval", callback_data="set_interval"),
            InlineKeyboardButton("🔢 Change Max Leads", callback_data="set_max_leads")
        ],
        [
            InlineKeyboardButton("❌ Close Panel", callback_data="set_close")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if edit_message and update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        # Check if called from message or query
        target = update.message if update.message else update.callback_query.message
        await target.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

# --- Text Message Handler (State Machine / Input Capture) ---

async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles text submissions from the user (such as entering custom cities)."""
    user_id = update.effective_user.id
    if user_id != config.ADMIN_TELEGRAM_ID:
        return
        
    text = update.message.text.strip()
    
    # 1. Capture custom city input for /find interactive flow
    if context.user_data.get("awaiting_city_input"):
        context.user_data["awaiting_city_input"] = False
        context.user_data["find_city"] = text
        await ask_for_limit(update, context)
        return
        
    # 2. Capture custom cities input for Settings Page
    if context.user_data.get("setting_awaiting_cities"):
        context.user_data["setting_awaiting_cities"] = False
        # Normalize and save cities
        cleaned = ",".join([c.strip() for c in text.split(",") if c.strip()])
        if cleaned:
            save_setting("default_cities", cleaned)
            await update.message.reply_text(f"✅ Default cities updated to: `{cleaned}`", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ Invalid format. Default cities left unchanged.")
        # Reload panel
        await send_settings_panel(update, context, False)
        return

# --- Inline Button Callback Handlers ---

async def ask_for_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Interactive /find flow step 3: limit selector."""
    keyboard = [
        [
            InlineKeyboardButton("5 Leads", callback_data="flow_limit_5"),
            InlineKeyboardButton("10 Leads", callback_data="flow_limit_10")
        ],
        [
            InlineKeyboardButton("15 Leads", callback_data="flow_limit_15"),
            InlineKeyboardButton("20 Leads", callback_data="flow_limit_20")
        ],
        [
            InlineKeyboardButton("50 Leads", callback_data="flow_limit_50"),
            InlineKeyboardButton("100 Leads", callback_data="flow_limit_100")
        ],
        [
            InlineKeyboardButton("200 Leads", callback_data="flow_limit_200")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg_text = (
        f"📂 **Niche:** {context.user_data['find_niche'].capitalize()}\n"
        f"📍 **City:** {context.user_data['find_city'].capitalize()}\n\n"
        "🔢 **Select maximum leads to find:**"
    )
    
    if update.callback_query:
        await update.callback_query.message.edit_text(msg_text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg_text, reply_markup=reply_markup, parse_mode="Markdown")

@admin_only
async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes callback triggers from settings, lead cards, and flow builders."""
    query = update.callback_query
    data = query.data
    await query.answer() # Ack
    
    # ------------------ LEAD CARD INTERACTIONS ------------------
    if any(data.startswith(prefix) for prefix in ["save_", "skip_", "msg_", "follow_", "bad_", "close_", "angle_"]):
        action, lead_id_str = data.split("_", 1)
        lead_id = int(lead_id_str)
        lead = get_lead(lead_id)
        
        if not lead:
            await query.edit_message_text("❌ Error: Lead not found in database.")
            return
            
        if action == "save":
            update_lead_status(lead_id, "saved")
            lead["status"] = "saved"
            await query.edit_message_text(build_lead_message_text(lead), reply_markup=query.message.reply_markup, parse_mode="HTML")
            
        elif action == "skip":
            update_lead_status(lead_id, "skipped")
            lead["status"] = "skipped"
            await query.edit_message_text(build_lead_message_text(lead), reply_markup=query.message.reply_markup, parse_mode="HTML")
            
        elif action == "msg":
            update_lead_status(lead_id, "messaged")
            lead["status"] = "messaged"
            await query.edit_message_text(build_lead_message_text(lead), reply_markup=query.message.reply_markup, parse_mode="HTML")
            
        elif action == "follow":
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            update_lead_status(lead_id, "follow_up_needed", tomorrow)
            lead["status"] = f"follow_up_needed (tomorrow: {tomorrow})"
            await query.edit_message_text(build_lead_message_text(lead), reply_markup=query.message.reply_markup, parse_mode="HTML")
            
        elif action == "bad":
            update_lead_status(lead_id, "bad_lead")
            lead["status"] = "bad_lead"
            await query.edit_message_text(build_lead_message_text(lead), reply_markup=query.message.reply_markup, parse_mode="HTML")
            
        elif action == "close":
            update_lead_status(lead_id, "closed")
            lead["status"] = "closed"
            await query.edit_message_text(build_lead_message_text(lead), reply_markup=query.message.reply_markup, parse_mode="HTML")
            
        elif action == "angle":
            # Sends custom outreach copy tailored with the angle using HTML format
            name = html.escape(lead.get('name') or '')
            angle = html.escape(lead.get('custom_angle') or '')
            msg = html.escape(lead.get('suggested_message') or '')
            source = html.escape(lead.get('source_type') or '').upper()
            
            custom_msg = (
                f"💡 <b>Custom Angle for {name}</b> ({source}):\n"
                f"<i>{angle}</i>\n\n"
                f"👉 <b>Send this customized DM:</b>\n"
                f"<code>{msg}</code>"
            )
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=custom_msg,
                parse_mode="HTML",
                reply_to_message_id=query.message.message_id
            )
            
    # ------------------ MENU SHORTCUTS ------------------
    elif data == "menu_find":
        await find_command(update, context)
    elif data == "menu_stats":
        # Simulate stats command
        class MockUpdate:
            def __init__(self, msg, user):
                self.message = msg
                self.effective_user = user
                
        await stats_command(MockUpdate(query.message, query.from_user), context)
    elif data == "menu_settings":
        await settings_command(update, context)
    elif data == "menu_next":
        class MockUpdate:
            def __init__(self, msg, user):
                self.message = msg
                self.effective_user = user
                
        await next_command(MockUpdate(query.message, query.from_user), context)
        
    # ------------------ INTERACTIVE /FIND FLOW ------------------
    elif data.startswith("flow_niche_"):
        niche = data.split("_")[-1]
        context.user_data["find_niche"] = niche
        
        # Build city options using default cities
        cities = get_setting_list("default_cities", config.DEFAULT_CITIES)
        keyboard = []
        # Display up to 6 default cities in 2 columns
        row = []
        for city in cities[:6]:
            row.append(InlineKeyboardButton(city.capitalize(), callback_data=f"flow_city_{city}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
            
        keyboard.append([InlineKeyboardButton("✍️ Other (Type city)", callback_data="flow_city_custom")])
        
        await query.edit_message_text(
            f"📂 Niche: **{niche.capitalize()}**\n\n📍 **Select City:**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
    elif data.startswith("flow_city_"):
        city = data.split("_")[-1]
        if city == "custom":
            context.user_data["awaiting_city_input"] = True
            await query.edit_message_text("✍️ Please type the city name in chat:")
        else:
            context.user_data["find_city"] = city
            await ask_for_limit(update, context)
            
    elif data.startswith("flow_limit_"):
        limit = int(data.split("_")[-1])
        context.user_data["find_limit"] = limit
        
        niche = context.user_data["find_niche"]
        city = context.user_data["find_city"]
        
        await query.edit_message_text(
            f"🚀 **Search Setup Complete!**\n\n"
            f"• Niche: `{niche.capitalize()}`\n"
            f"• City: `{city.capitalize()}`\n"
            f"• Limit: `{limit} leads`\n\n"
            "🔍 Searching public web records. Please wait...",
            parse_mode="Markdown"
        )
        
        # Run search immediately
        # We need a mock update object to pass to execute_fast_search since it expects update.message.reply_text
        # Or we can write the execute_fast_search logic tailored for query
        min_score = get_setting_int("minimum_score", 7)
        try:
            chat_id = query.message.chat_id
            leads = await run_search_for_niche_city(niche, city, limit, min_score, context=context, chat_id=chat_id)
            
            try:
                await query.delete_message()
            except Exception:
                pass
                
            if not leads:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ No new leads found. Try a different city."
                )
                return
                
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ Done! Found and sent **{len(leads)}** new qualified leads (score >= {min_score}).",
                parse_mode="Markdown"
            )
            
        except (BraveSearchAPIKeyMissing, SearchAPIKeysMissing):
            await query.edit_message_text("⚠️ Search API credentials are missing. Add `GOOGLE_API_KEY`/`GOOGLE_CX` or `BRAVE_API_KEY` to `.env`.")
        except Exception as e:
            logger.error(f"Error executing flow search: {e}")
            await query.edit_message_text("❌ An error occurred during search. Please check the logs.")
            
    # ------------------ SETTINGS INTERACTIONS ------------------
    elif data == "set_min_score":
        keyboard = []
        row = []
        for score in range(5, 10):
            row.append(InlineKeyboardButton(f"⭐ {score}", callback_data=f"setval_minscore_{score}"))
        keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔙 Back to Settings", callback_data="set_back")])
        
        await query.edit_message_text(
            "⭐ **Select Minimum Score Threshold:**\nLeads below this rating will be skipped automatically.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
    elif data == "set_cities":
        context.user_data["setting_awaiting_cities"] = True
        await query.edit_message_text(
            "📍 **Configure Target Cities:**\n\n"
            "Please type a comma-separated list of cities in the chat (no quotes):\n"
            "Example: `Dallas, Austin, Miami, Brooklyn`"
        )
        
    elif data == "set_niches":
        enabled_niches = get_setting_list("enabled_niches", config.DEFAULT_NICHES)
        
        # Build toggles for fitness, nails, creators
        fit_lbl = "🏋️ Fitness (ENABLED)" if "fitness" in enabled_niches else "🏋️ Fitness (DISABLED)"
        nail_lbl = "💅 Nails (ENABLED)" if "nails" in enabled_niches else "💅 Nails (DISABLED)"
        creator_lbl = "🎨 Creators (ENABLED)" if "creators" in enabled_niches else "🎨 Creators (DISABLED)"
        
        keyboard = [
            [InlineKeyboardButton(fit_lbl, callback_data="toggle_niche_fitness")],
            [InlineKeyboardButton(nail_lbl, callback_data="toggle_niche_nails")],
            [InlineKeyboardButton(creator_lbl, callback_data="toggle_niche_creators")],
            [InlineKeyboardButton("🔙 Back", callback_data="set_back")]
        ]
        await query.edit_message_text(
            "📂 **Toggle Enabled Niches for Scheduled Scan:**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
    elif data == "set_toggle_scheduler":
        state = get_setting_bool("scheduled_search_enabled", False)
        save_setting("scheduled_search_enabled", not state)
        setup_scheduler(context.application) # reload scheduler
        await send_settings_panel(update, context, True)
        
    elif data == "set_interval":
        keyboard = [
            [
                InlineKeyboardButton("1 hour", callback_data="setval_freq_1"),
                InlineKeyboardButton("2 hours", callback_data="setval_freq_2"),
                InlineKeyboardButton("4 hours", callback_data="setval_freq_4")
            ],
            [
                InlineKeyboardButton("8 hours", callback_data="setval_freq_8"),
                InlineKeyboardButton("12 hours", callback_data="setval_freq_12"),
                InlineKeyboardButton("24 hours", callback_data="setval_freq_24")
            ],
            [InlineKeyboardButton("🔙 Back", callback_data="set_back")]
        ]
        await query.edit_message_text(
            "🕒 **Select Background Search Frequency:**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
    elif data == "set_max_leads":
        keyboard = [
            [
                InlineKeyboardButton("5", callback_data="setval_maxleads_5"),
                InlineKeyboardButton("10", callback_data="setval_maxleads_10"),
                InlineKeyboardButton("20", callback_data="setval_maxleads_20"),
                InlineKeyboardButton("50", callback_data="setval_maxleads_50")
            ],
            [
                InlineKeyboardButton("100", callback_data="setval_maxleads_100"),
                InlineKeyboardButton("200", callback_data="setval_maxleads_200")
            ],
            [InlineKeyboardButton("🔙 Back", callback_data="set_back")]
        ]
        await query.edit_message_text(
            "🔢 **Select maximum leads sent per automated run:**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
    elif data == "set_back":
        await send_settings_panel(update, context, True)
        
    elif data == "set_close":
        await query.delete_message()
        
    # ------------------ SETTINGS VALUE SAVERS ------------------
    elif data.startswith("setval_minscore_"):
        score = int(data.split("_")[-1])
        save_setting("minimum_score", score)
        await send_settings_panel(update, context, True)
        
    elif data.startswith("setval_freq_"):
        hours = int(data.split("_")[-1])
        save_setting("scheduled_search_frequency_hours", hours)
        setup_scheduler(context.application) # reload scheduler
        await send_settings_panel(update, context, True)
        
    elif data.startswith("setval_maxleads_"):
        limit = int(data.split("_")[-1])
        save_setting("max_leads_per_run", limit)
        await send_settings_panel(update, context, True)
        
    elif data.startswith("toggle_niche_"):
        niche = data.split("_")[-1]
        enabled_niches = get_setting_list("enabled_niches", config.DEFAULT_NICHES)
        
        if niche in enabled_niches:
            enabled_niches.remove(niche)
        else:
            enabled_niches.append(niche)
            
        save_setting("enabled_niches", ",".join(enabled_niches))
        # Trigger reload of toggles
        # Generate menu again
        fit_lbl = "🏋️ Fitness (ENABLED)" if "fitness" in enabled_niches else "🏋️ Fitness (DISABLED)"
        nail_lbl = "💅 Nails (ENABLED)" if "nails" in enabled_niches else "💅 Nails (DISABLED)"
        creator_lbl = "🎨 Creators (ENABLED)" if "creators" in enabled_niches else "🎨 Creators (DISABLED)"
        
        keyboard = [
            [InlineKeyboardButton(fit_lbl, callback_data="toggle_niche_fitness")],
            [InlineKeyboardButton(nail_lbl, callback_data="toggle_niche_nails")],
            [InlineKeyboardButton(creator_lbl, callback_data="toggle_niche_creators")],
            [InlineKeyboardButton("🔙 Back to Settings", callback_data="set_back")]
        ]
        await query.edit_message_text(
            "📂 **Toggle Enabled Niches for Scheduled Scan:**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

# --- Startup Post-Initialization ---

async def post_init(application) -> None:
    """Invoked after bot starts up. Initializes DB schema and configures the scheduler."""
    logger.info("Initializing database...")
    init_db()
    
    logger.info("Starting background scheduler...")
    setup_scheduler(application)
    logger.info("Startup sequence complete.")

# --- Main Entry Point ---

def main():
    """Starts the Telegram bot application loop."""
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    if not config.TELEGRAM_BOT_TOKEN or config.TELEGRAM_BOT_TOKEN == "your_telegram_bot_token_here":
        print("❌ CRITICAL ERROR: TELEGRAM_BOT_TOKEN is missing or not configured in .env file.")
        return
        
    if not config.ADMIN_TELEGRAM_ID:
        print("⚠️ WARNING: ADMIN_TELEGRAM_ID is 0 or missing. The bot will deny access to everyone.")

    logger.info("Booting Lead Scout Bot...")
    
    # Build python-telegram-bot application with post-init hook
    application = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    
    # 1. Commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("find", find_command))
    application.add_handler(CommandHandler("find_fitness", find_fitness_command))
    application.add_handler(CommandHandler("find_nails", find_nails_command))
    application.add_handler(CommandHandler("find_creators", find_creators_command))
    
    application.add_handler(CommandHandler("top", top_command))
    application.add_handler(CommandHandler("today", today_command))
    application.add_handler(CommandHandler("next", next_command))
    application.add_handler(CommandHandler("saved", saved_command))
    application.add_handler(CommandHandler("messaged", messaged_command))
    application.add_handler(CommandHandler("followups", followups_command))
    
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("export", export_command))
    application.add_handler(CommandHandler("clear_bad", clear_bad_command))
    
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("search_status", search_status_command))
    application.add_handler(CommandHandler("pause", pause_command))
    application.add_handler(CommandHandler("resume", resume_command))
    
    # 2. Text Message Capture
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))
    
    # 3. Inline Button Callbacks
    application.add_handler(CallbackQueryHandler(callback_query_handler))
    
    # 4. Start health-check server in background thread (for Render keep-alive)
    threading.Thread(target=_start_health_server, daemon=True).start()

    # 5. Start Event Loop (Blocking)
    logger.info("Bot is polling. Press Ctrl+C to terminate.")
    application.run_polling()

if __name__ == "__main__":
    main()
