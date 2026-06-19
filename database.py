import sqlite3
import os
from datetime import datetime
from utils import logger, normalize_url, extract_instagram_username
import config

def get_db_connection():
    """Returns a sqlite3 connection with Row factory enabled."""
    conn = sqlite3.connect(config.DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database schema and seeds default settings if empty."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create leads table matching user schema exactly
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        niche TEXT,
        city TEXT,
        url TEXT UNIQUE,
        instagram_url TEXT,
        website_url TEXT,
        source_domain TEXT,
        source_type TEXT,
        title TEXT,
        snippet TEXT,
        score INTEGER,
        score_reason TEXT,
        recommended_demo TEXT,
        suggested_message TEXT,
        custom_angle TEXT,
        status TEXT DEFAULT 'new',
        follow_up_date TEXT,
        created_at TEXT,
        updated_at TEXT
    )
    """)
    
    # Create settings table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    
    conn.commit()
    
    # Seed default settings if empty
    cursor.execute("SELECT COUNT(*) FROM settings")
    if cursor.fetchone()[0] == 0:
        logger.info("Seeding default settings into database...")
        default_settings = {
            "minimum_score": str(config.DEFAULT_MINIMUM_SCORE),
            "default_cities": ",".join(config.DEFAULT_CITIES),
            "enabled_niches": ",".join(config.DEFAULT_NICHES),
            "scheduled_search_enabled": "true" if config.DEFAULT_SCHEDULED_SEARCH_ENABLED else "false",
            "scheduled_search_frequency_hours": str(config.DEFAULT_SCHEDULED_SEARCH_FREQUENCY_HOURS),
            "max_leads_per_run": str(config.DEFAULT_MAX_LEADS_PER_RUN)
        }
        for k, v in default_settings.items():
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, v))
        conn.commit()
        
    conn.close()
    logger.info("Database initialized successfully.")

# --- Settings Manager Functions ---

def get_setting(key: str, default=None) -> str:
    """Gets a setting value as string."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default

def get_setting_int(key: str, default=0) -> int:
    """Gets a setting value as integer."""
    val = get_setting(key)
    try:
        return int(val) if val is not None else default
    except ValueError:
        return default

def get_setting_bool(key: str, default=False) -> bool:
    """Gets a setting value as boolean."""
    val = get_setting(key)
    if val is None:
        return default
    return val.lower() == "true"

def get_setting_list(key: str, default=None) -> list:
    """Gets a setting value as a list (split by comma)."""
    val = get_setting(key)
    if not val:
        return default or []
    return [item.strip() for item in val.split(",") if item.strip()]

def save_setting(key: str, value) -> None:
    """Saves or updates a setting."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Normalize booleans
    if isinstance(value, bool):
        val_str = "true" if value else "false"
    elif isinstance(value, list):
        val_str = ",".join(value)
    else:
        val_str = str(value)
        
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, val_str))
    conn.commit()
    conn.close()
    logger.info(f"Setting updated: {key} = {val_str}")

def get_all_settings() -> dict:
    """Retrieves all settings as a dictionary."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    conn.close()
    return {row["key"]: row["value"] for row in rows}

# --- Leads Functions ---

def is_duplicate(cursor, url: str, instagram_url: str, title: str, city: str, niche: str) -> bool:
    """
    Checks if a lead is a duplicate based on four criteria:
    1. Exact URL match
    2. Normalized URL match
    3. Instagram username match (if detected)
    4. Exact title + city + niche match
    """
    norm_url = normalize_url(url)
    inst_handle = extract_instagram_username(instagram_url or url)
    
    cursor.execute("SELECT url, instagram_url, title, city, niche FROM leads")
    rows = cursor.fetchall()
    
    for row in rows:
        db_url = row["url"]
        db_inst_url = row["instagram_url"]
        db_title = row["title"]
        db_city = row["city"]
        db_niche = row["niche"]
        
        # 1. Exact URL
        if url == db_url:
            return True
            
        # 2. Normalized URL
        if norm_url == normalize_url(db_url):
            return True
            
        # 3. Instagram username match
        if inst_handle:
            db_inst_handle = extract_instagram_username(db_inst_url or db_url)
            if db_inst_handle and inst_handle == db_inst_handle:
                return True
                
        # 4. Same title + city + niche (case-insensitive)
        if title and db_title:
            t1 = title.lower().strip()
            t2 = db_title.lower().strip()
            if t1 == t2 and city.lower() == db_city.lower() and niche.lower() == db_niche.lower():
                return True
                
    return False

def save_lead(lead_dict: dict) -> bool:
    """
    Saves a lead to the database if it is not a duplicate.
    Returns True if successfully saved, False if skipped as a duplicate.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    url = lead_dict.get("url")
    instagram_url = lead_dict.get("instagram_url")
    title = lead_dict.get("title")
    city = lead_dict.get("city")
    niche = lead_dict.get("niche")
    
    if is_duplicate(cursor, url, instagram_url, title, city, niche):
        conn.close()
        return False
        
    now_str = datetime.now().isoformat()
    
    try:
        cursor.execute("""
        INSERT INTO leads (
            name, niche, city, url, instagram_url, website_url, 
            source_domain, source_type, title, snippet, score, 
            score_reason, recommended_demo, suggested_message, 
            custom_angle, status, follow_up_date, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            lead_dict.get("name"),
            niche,
            city,
            url,
            instagram_url,
            lead_dict.get("website_url"),
            lead_dict.get("source_domain"),
            lead_dict.get("source_type"),
            title,
            lead_dict.get("snippet"),
            lead_dict.get("score"),
            lead_dict.get("score_reason"),
            lead_dict.get("recommended_demo"),
            lead_dict.get("suggested_message"),
            lead_dict.get("custom_angle"),
            lead_dict.get("status", "new"),
            lead_dict.get("follow_up_date"),
            now_str,
            now_str
        ))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        # Just in case UNIQUE constraint kicks in
        success = False
    except Exception as e:
        logger.error(f"Error saving lead {url}: {e}")
        success = False
    finally:
        conn.close()
        
    return success

def get_lead(lead_id: int) -> dict:
    """Gets a single lead by its ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_lead_status(lead_id: int, status: str, follow_up_date: str = None) -> None:
    """Updates a lead's status and optional follow-up date."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()
    
    if follow_up_date:
        cursor.execute("""
        UPDATE leads 
        SET status = ?, follow_up_date = ?, updated_at = ? 
        WHERE id = ?
        """, (status, follow_up_date, now_str, lead_id))
    else:
        cursor.execute("""
        UPDATE leads 
        SET status = ?, updated_at = ? 
        WHERE id = ?
        """, (status, now_str, lead_id))
        
    conn.commit()
    conn.close()
    logger.info(f"Lead ID {lead_id} status updated to {status}")

def update_lead_custom_angle(lead_id: int, custom_angle: str) -> None:
    """Updates a lead's custom angle."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()
    cursor.execute("""
    UPDATE leads 
    SET custom_angle = ?, updated_at = ? 
    WHERE id = ?
    """, (custom_angle, now_str, lead_id))
    conn.commit()
    conn.close()
    logger.info(f"Lead ID {lead_id} custom angle updated.")

def get_leads_by_status(status: str) -> list:
    """Gets list of leads filtered by status."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM leads WHERE status = ? ORDER BY score DESC, id DESC", (status,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_top_leads(min_score: int = 8, max_score: int = 10) -> list:
    """Gets leads with score between min_score and max_score."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM leads 
    WHERE score >= ? AND score <= ? 
    ORDER BY score DESC, id DESC
    """, (min_score, max_score))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_today_leads() -> list:
    """Gets leads created today (UTC local)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    today_date = datetime.now().strftime("%Y-%m-%d")
    # created_at is saved as ISO format: YYYY-MM-DDTHH:MM:SS
    cursor.execute("""
    SELECT * FROM leads 
    WHERE created_at LIKE ? 
    ORDER BY score DESC, id DESC
    """, (f"{today_date}%",))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_next_unreviewed_lead() -> dict:
    """Gets the next unreviewed lead (status = 'new' or 'sent_to_telegram')."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM leads 
    WHERE status IN ('new', 'sent_to_telegram') 
    ORDER BY score DESC, id ASC 
    LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_stats() -> dict:
    """Computes and returns descriptive lead statistics."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    stats = {}
    
    # Total
    cursor.execute("SELECT COUNT(*) FROM leads")
    stats["total"] = cursor.fetchone()[0]
    
    # Today
    today_date = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT COUNT(*) FROM leads WHERE created_at LIKE ?", (f"{today_date}%",))
    stats["today"] = cursor.fetchone()[0]
    
    # By niche
    cursor.execute("SELECT niche, COUNT(*) FROM leads GROUP BY niche")
    stats["niches"] = {row[0]: row[1] for row in cursor.fetchall()}
    
    # By score
    cursor.execute("SELECT score, COUNT(*) FROM leads GROUP BY score ORDER BY score DESC")
    stats["scores"] = {row[0]: row[1] for row in cursor.fetchall()}
    
    # By status
    cursor.execute("SELECT status, COUNT(*) FROM leads GROUP BY status")
    stats["statuses"] = {row[0]: row[1] for row in cursor.fetchall()}
    
    conn.close()
    return stats

def clear_bad_leads() -> int:
    """
    Deletes or purges skipped, bad, or low-scoring leads (< minimum_score) from database.
    Returns the number of deleted records.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    min_score = get_setting_int("minimum_score", 7)
    
    cursor.execute("""
    DELETE FROM leads 
    WHERE status IN ('skipped', 'bad_lead') OR score < ?
    """, (min_score,))
    
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()
    
    logger.info(f"Purged {deleted_count} bad/skipped leads from database.")
    return deleted_count

def get_all_leads() -> list:
    """Gets all leads in the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM leads ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]
