import asyncio
import html
from datetime import datetime
from database import (
    get_setting_int, get_setting_bool, get_setting_list, 
    save_setting, save_lead, get_db_connection
)
from query_builder import build_queries
from search_engine import search_web_results, SearchAPIKeysMissing, BraveSearchAPIKeyMissing
from lead_parser import parse_lead
from scoring import score_lead, recommend_demo, get_pagespeed_score
from message_templates import get_outreach_for_lead
from utils import logger
import config
from telegram.ext import ContextTypes
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

async def run_search_for_niche_city(niche: str, city: str, limit: int, min_score: int, context=None, chat_id=None) -> list:
    """
    Runs search for a specific niche and city.
    Dynamically scales query count and results per query based on the requested limit.
    Optionally streams qualified leads to Telegram in real-time if context and chat_id are provided.
    Returns a list of qualified lead dicts.
    """
    queries = build_queries(niche, city)
    qualified_leads = []
    
    # Dynamically determine the maximum number of queries to scan and result depth
    if limit <= 10:
        max_queries = 3
        count_per_query = 10
    elif limit <= 20:
        max_queries = 5
        count_per_query = 15
    elif limit <= 50:
        max_queries = 10
        count_per_query = 25
    elif limit <= 100:
        max_queries = 20
        count_per_query = 40
    else:
        max_queries = len(queries)
        count_per_query = 50

    selected_queries = queries[:max_queries]
    
    for query_item in selected_queries:
        query = query_item["query"]
        q_niche = query_item["niche"]
        try:
            results = await search_web_results(query, count=count_per_query)
            for r in results:
                # Parse search result using the query's actual niche
                lead = parse_lead(r, q_niche, city)
                
                # CORE FILTER: only keep Instagram profile leads that have an Instagram URL.
                # We are selling websites to Instagram creators — we need their Instagram,
                # not a vagaro/booksy/yelp page or any other platform directory.
                if lead.get("source_type") != "instagram":
                    continue
                if not lead.get("instagram_url"):
                    continue
                
                # Skip leads whose bio contains a booking platform link —
                # they already have booking infrastructure, not our target.
                # Check snippet text AND the website_url extracted from bio.
                BOOKING_SERVICES = [
                    "booksy.com", "fresha.com", "vagaro.com", "calendly.com",
                    "acuityscheduling.com", "squareup.com", "square.site",
                    "mindbodyonline.com", "schedulicity.com", "glofox.com",
                    "styleseat.com", "genbook.com", "timely.com", "setmore.com",
                    "book.app", "booker.com", "reservio.com", "simplybook.me",
                    "simplybook", "yclients", "dikidi", "masters.app", 
                    "rubitime", "qnits", "widget.salon", "profsalon", "app.apparent"
                ]
                check_text = " ".join([
                    lead.get("snippet", ""),
                    lead.get("website_url", "") or "",
                    r.get("url", "")
                ]).lower()
                if any(svc in check_text for svc in BOOKING_SERVICES):
                    logger.info(f"Skipping lead {lead.get('name')} due to booking platform link.")
                    continue
                
                # Filter website TLDs: if they have a website link that is not a link-in-bio site,
                # it MUST end in .com. All other custom TLDs (.net, .org, .co, .ru, etc.) are ignored.
                if lead.get("website_url"):
                    from urllib.parse import urlparse
                    parsed_web = urlparse(lead["website_url"])
                    web_domain = parsed_web.netloc.lower()
                    if web_domain.startswith("www."):
                        web_domain = web_domain[4:]
                    
                    LINK_BIO_SERVICES = [
                        "linktr.ee", "beacons.ai", "beacons.page", "stan.store", 
                        "taplink.cc", "taplink.ws", "taplink", "campsite.bio", 
                        "solo.to", "milkshake.app", "lnk.bio", "heylink.me", "heylink"
                    ]
                    
                    is_link_bio = any(lb in web_domain for lb in LINK_BIO_SERVICES)
                    if not is_link_bio:
                        if not web_domain.endswith(".com"):
                            logger.info(f"Skipping lead {lead.get('name')} because website {lead['website_url']} does not end with .com")
                            continue

                
                lead["pagespeed_score"] = -1
                
                # Score lead (incorporating PageSpeed details)
                score, reason = score_lead(lead)
                lead["score"] = score
                lead["score_reason"] = reason
                
                # Recommended demo based on actual query niche
                lead["recommended_demo"] = recommend_demo(q_niche, r["title"], r["snippet"], r["url"])
                
                # Filter by minimum score & defer Gemini personalization to save API and time
                if score >= min_score:
                    lead["status"] = "new"
                    # Generate custom angle and message ONLY for qualified leads
                    angle, msg = await get_outreach_for_lead(lead)
                    lead["custom_angle"] = angle
                    lead["suggested_message"] = msg
                else:
                    lead["status"] = "skipped"
                    lead["custom_angle"] = ""
                    lead["suggested_message"] = ""
                    
                # Save to DB (returns True if it's a new, unique lead)
                is_new = save_lead(lead)
                
                if is_new and score >= min_score:
                    # Fetch database ID for inline button callbacks
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT id FROM leads WHERE url = ?", (lead["url"],))
                    row = cursor.fetchone()
                    conn.close()
                    if row:
                        lead["id"] = row["id"]
                    
                    qualified_leads.append(lead)
                    
                    # Stream immediately to Telegram if context and chat_id are present
                    if context and chat_id:
                        try:
                            # Update status in DB to indicate it was sent to telegram
                            from database import update_lead_status
                            update_lead_status(lead["id"], "sent_to_telegram")
                            lead["status"] = "sent_to_telegram"
                            
                            text = build_lead_message_text(lead)
                            reply_markup = get_lead_inline_keyboard(lead["id"], lead["url"], lead["recommended_demo"])
                            
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=text,
                                reply_markup=reply_markup,
                                parse_mode="HTML"
                            )
                            # Brief sleep between messages to avoid Telegram rate limits
                            await asyncio.sleep(0.5)
                        except Exception as send_err:
                            logger.error(f"Failed to stream lead {lead.get('name')} to Telegram: {send_err}")
                    
                if len(qualified_leads) >= limit:
                    break
            if len(qualified_leads) >= limit:
                break
        except (BraveSearchAPIKeyMissing, SearchAPIKeysMissing):
            raise
        except Exception as e:
            logger.error(f"Error searching query '{query}' for {q_niche} in {city}: {e}")
            continue
            
    return qualified_leads

def build_lead_message_text(lead: dict) -> str:
    """Formats the Telegram lead notification message using HTML to avoid escape characters bugs."""
    name = html.escape(lead.get('name') or '')
    niche = html.escape(lead.get('niche') or '').capitalize()
    city = html.escape(lead.get('city') or '').capitalize()
    source_domain = html.escape(lead.get('source_domain') or '')
    url = html.escape(lead.get('url') or '')
    instagram = html.escape(lead.get('instagram_url') or 'Not found')
    website = html.escape(lead.get('website_url') or 'Not found')
    reason = html.escape(lead.get('score_reason') or '')
    demo = html.escape(lead.get('recommended_demo') or '')
    angle = html.escape(lead.get('custom_angle') or '')
    msg = html.escape(lead.get('suggested_message') or '')
    status = html.escape(lead.get('status') or '')
    
    return (
        f"🔥 <b>New Lead: {lead['score']}/10</b>\n\n"
        f"📂 <b>Niche:</b> {niche}\n"
        f"📍 <b>City:</b> {city}\n"
        f"🌐 <b>Source:</b> {source_domain}\n"
        f"👤 <b>Lead Name:</b> {name}\n"
        f"🔗 <b>URL:</b> {url}\n"
        f"📱 <b>Instagram:</b> {instagram}\n"
        f"🖥️ <b>Website:</b> {website}\n\n"
        f"✨ <b>Why this is a good lead:</b>\n{reason}\n\n"
        f"🎯 <b>Recommended Demo:</b>\n{demo}\n\n"
        f"💡 <b>Custom Angle:</b>\n{angle}\n\n"
        f"✉️ <b>Suggested DM:</b>\n<code>{msg}</code>\n\n"
        f"📌 <b>Status:</b> {status}"
    )

def get_lead_inline_keyboard(lead_id: int, lead_url: str, demo_url: str) -> InlineKeyboardMarkup:
    """Creates the grid layout of action buttons for a lead."""
    keyboard = [
        [
            InlineKeyboardButton("🔗 Open Lead", url=lead_url),
            InlineKeyboardButton("💻 Open Demo", url=demo_url)
        ],
        [
            InlineKeyboardButton("✅ Save", callback_data=f"save_{lead_id}"),
            InlineKeyboardButton("❌ Skip", callback_data=f"skip_{lead_id}")
        ],
        [
            InlineKeyboardButton("✉️ Mark Messaged", callback_data=f"msg_{lead_id}"),
            InlineKeyboardButton("📅 Follow-up Tomorrow", callback_data=f"follow_{lead_id}")
        ],
        [
            InlineKeyboardButton("👎 Bad Lead", callback_data=f"bad_{lead_id}"),
            InlineKeyboardButton("🔒 Closed", callback_data=f"close_{lead_id}")
        ],
        [
            InlineKeyboardButton("💡 Generate Custom Angle", callback_data=f"angle_{lead_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def scheduled_search_callback(context: ContextTypes.DEFAULT_TYPE):
    """
    Job Queue callback that runs background searches periodically.
    Rotates cities (round-robin) to avoid rate limits and high API cost.
    """
    logger.info("Executing scheduled background search job...")
    admin_id = config.ADMIN_TELEGRAM_ID
    if not admin_id:
        logger.warning("ADMIN_TELEGRAM_ID is not configured. Skipping scheduled search.")
        return
        
    try:
        # Load configuration settings from database
        min_score = get_setting_int("minimum_score", 7)
        cities = get_setting_list("default_cities", config.DEFAULT_CITIES)
        niches = get_setting_list("enabled_niches", config.DEFAULT_NICHES)
        max_leads = get_setting_int("max_leads_per_run", 10)
        
        if not cities or not niches:
            logger.warning("Scheduled search skipped: no cities or niches enabled.")
            return
            
        # Get next city to scan (round-robin)
        current_city_index = get_setting_int("current_city_index", 0)
        selected_city = cities[current_city_index % len(cities)]
        
        # Increment index and save back to DB
        save_setting("current_city_index", (current_city_index + 1) % len(cities))
        
        logger.info(f"Scheduled scan starting for city: {selected_city} across niches: {niches}")
        
        total_found = 0
        leads_to_send = []
        
        for niche in niches:
            # Calculate remaining space
            remaining_limit = max_leads - total_found
            if remaining_limit <= 0:
                break
                
            leads = await run_search_for_niche_city(niche, selected_city, remaining_limit, min_score)
            leads_to_send.extend(leads)
            total_found += len(leads)
            
        if not leads_to_send:
            logger.info(f"Scheduled search finished for {selected_city}. No new qualified leads found.")
            return
            
        # Send leads to Telegram admin
        for lead in leads_to_send:
            text = build_lead_message_text(lead)
            reply_markup = get_lead_inline_keyboard(lead["id"], lead["url"], lead["recommended_demo"])
            
            try:
                # Update status in DB to indicate it was sent to telegram
                from database import update_lead_status
                update_lead_status(lead["id"], "sent_to_telegram")
                lead["status"] = "sent_to_telegram"
                
                # Rebuild text with updated status
                text = build_lead_message_text(lead)
                
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )
                # Brief sleep between messages to avoid Telegram rate limits
                await asyncio.sleep(0.5)
            except Exception as send_err:
                logger.error(f"Failed to send scheduled lead message: {send_err}")
                
        logger.info(f"Scheduled search complete. Sent {len(leads_to_send)} leads to Telegram.")
        
    except (BraveSearchAPIKeyMissing, SearchAPIKeysMissing):
        logger.error("Scheduled search failed: Search API credentials are missing.")
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text="⚠️ **Scheduled Search Alert**\nSearch API credentials are missing. Add `GOOGLE_API_KEY`/`GOOGLE_CX` or `BRAVE_API_KEY` to `.env`."
            )
        except Exception as e:
            logger.error(f"Failed to notify admin of missing API keys: {e}")
    except Exception as err:
        logger.error(f"Error in scheduled search job: {err}")

def setup_scheduler(application) -> None:
    """Sets up the JobQueue with repeating background task based on DB settings."""
    job_queue = application.job_queue
    if not job_queue:
        logger.error("JobQueue is not enabled in Telegram Application. Background scheduling disabled.")
        return
        
    # Clean up existing search jobs
    current_jobs = job_queue.get_jobs_by_name("scheduled_search")
    for job in current_jobs:
        job.schedule_removal()
        
    enabled = get_setting_bool("scheduled_search_enabled", False)
    frequency = get_setting_int("scheduled_search_frequency_hours", 2)
    
    if enabled:
        interval_seconds = frequency * 3600
        # Wait 30 seconds after startup to trigger the first scan, then repeat
        job_queue.run_repeating(
            scheduled_search_callback,
            interval=interval_seconds,
            first=30,
            name="scheduled_search"
        )
        logger.info(f"Scheduler active: running background scans every {frequency} hours.")
    else:
        logger.info("Scheduler is disabled in configuration settings.")
