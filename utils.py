import logging
import re
from urllib.parse import urlparse, parse_qsl, urlencode

def setup_logging():
    """Sets up standard logging for the bot."""
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    # Reduce noise from telegram library
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    return logging.getLogger("LeadScoutBot")

logger = setup_logging()

def normalize_url(url: str) -> str:
    """
    Normalizes a URL for deduplication:
    - Removes http://, https://, www.
    - Lowercases the host and path.
    - Strips trailing slash.
    - Removes common tracking query parameters (UTM, fbclid, igsh, etc.).
    """
    if not url:
        return ""
    
    url = url.strip()
    # Ensure protocol for urlparse
    if not (url.startswith("http://") or url.startswith("https://")):
        url_to_parse = "https://" + url
    else:
        url_to_parse = url
        
    try:
        parsed = urlparse(url_to_parse)
        
        # Remove tracking parameters
        query_params = parse_qsl(parsed.query)
        clean_params = []
        for k, v in query_params:
            k_lower = k.lower()
            if k_lower.startswith("utm_") or k_lower in ("fbclid", "igsh", "gclid", "_hsenc", "ref", "source"):
                continue
            clean_params.append((k, v))
            
        # Clean netloc (remove www.)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
            
        # Clean path (lowercase and remove trailing slash)
        path = parsed.path.lower().rstrip("/")
        
        # Re-encode parameters
        query = urlencode(clean_params)
        
        # Build normalized representation
        normalized = f"{netloc}{path}"
        if query:
            normalized += f"?{query}"
        return normalized
    except Exception as e:
        logger.error(f"Error normalizing URL {url}: {e}")
        return url.lower().strip()

def extract_instagram_username(url: str) -> str:
    """
    Extracts an Instagram username from a URL if it points to an Instagram page.
    Filters out system paths like 'p', 'reel', 'explore', 'stories', etc.
    """
    if not url:
        return ""
        
    # Pattern to match instagram.com/username
    match = re.search(r'(?:instagram\.com)/([a-zA-Z0-9_\.]+)', url, re.IGNORECASE)
    if match:
        username = match.group(1).lower().strip()
        ignored = {
            'p', 'reel', 'reels', 'explore', 'stories', 'accounts', 
            'about', 'privacy', 'terms', 'developer', 'oauth', 'emails', 'blog'
        }
        if username not in ignored and not username.endswith(('.png', '.jpg', '.jpeg', '.gif')):
            return username
    return ""

def clean_snippet(text: str) -> str:
    """Cleans up search result snippets (removes excessive whitespace/newlines)."""
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()
