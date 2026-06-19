import re
from urllib.parse import urlparse
from utils import extract_instagram_username, clean_snippet

def parse_lead(result: dict, niche: str, city: str) -> dict:
    """
    Parses a single search result into a standard lead dictionary.
    Identifies source platform type, extracts name, and searches for
    linked Instagram profiles or custom websites.
    """
    url = result.get("url", "")
    title = result.get("title", "")
    snippet = clean_snippet(result.get("snippet", ""))
    source_domain = result.get("source_domain", "")
    
    # 1. Determine Source Type
    source_type = "other"
    domain_lower = source_domain.lower()
    
    if "instagram.com" in domain_lower:
        source_type = "instagram"
    elif "linktr.ee" in domain_lower:
        source_type = "linktree"
    elif "stan.store" in domain_lower:
        source_type = "stan_store"
    elif "beacons.ai" in domain_lower or "beacons.page" in domain_lower:
        source_type = "beacons"
    elif "booksy.com" in domain_lower:
        source_type = "booksy"
    elif "fresha.com" in domain_lower:
        source_type = "fresha"
    elif "vagaro.com" in domain_lower:
        source_type = "vagaro"
    elif "yelp.com" in domain_lower:
        source_type = "yelp"
    else:
        # Check if social network directory that is NOT a custom website
        social_dirs = [
            "facebook.com", "facebook.co", "fb.com", "tiktok.com", "youtube.com",
            "linkedin.com", "twitter.com", "x.com", "pinterest.com", "groupon.com"
        ]
        if any(sd in domain_lower for sd in social_dirs):
            source_type = "other"
        else:
            # Custom domains (e.g. janesnails.com) are business websites
            source_type = "business_website"
            
    # 2. Extract Lead Name from Title
    name = title
    # Clean standard suffixes
    name_clean_patterns = [
        r"\(@[a-zA-Z0-9_\.]+\)",  # Remove (@username)
        r"• Instagram.*",          # Remove • Instagram photos and videos
        r"\| Booksy",              # Remove Booksy suffixes
        r"\| Fresha",
        r"\| Yelp",
        r"- Yelp",
        r"- Facebook",
        r"\| Linktree",
        r"on Instagram",
        r"Instagram"
    ]
    
    for pattern in name_clean_patterns:
        name = re.sub(pattern, "", name, flags=re.IGNORECASE)
        
    # Split by common title separators and take the first portion
    split_chars = ["|", "-", "•"]
    for char in split_chars:
        if char in name:
            parts = name.split(char)
            if parts[0].strip():
                name = parts[0]
                break
                
    name = name.strip()
    if not name or name.lower() in ("instagram", "login", "booksy", "fresha", "yelp"):
        name = "there"
        
    # 3. Detect and cross-reference Instagram URL and Website URL
    instagram_url = ""
    website_url = ""
    
    if source_type == "instagram":
        instagram_url = url
        # Scan snippet for a custom website (exclude social networks)
        web_match = re.search(r'https?://(?:www\.)?([a-zA-Z0-9-]+\.[a-z]{2,6})(?:/[^\s]*)?', snippet, re.IGNORECASE)
        if web_match:
            detected_link = web_match.group(0).rstrip(".,;:")
            parsed_det = urlparse(detected_link)
            det_domain = parsed_det.netloc.lower() or parsed_det.path.split("/")[0].lower()
            
            socials = ["instagram.com", "facebook.com", "tiktok.com", "twitter.com", "x.com", "youtube.com", "linkedin.com"]
            if not any(s in det_domain for s in socials):
                website_url = detected_link
    elif source_type == "business_website":
        website_url = url
        # Scan snippet for Instagram URL or @handle
        inst_match = re.search(r'https?://(?:www\.)?instagram\.com/[a-zA-Z0-9_\.]+', snippet, re.IGNORECASE)
        if inst_match:
            instagram_url = inst_match.group(0).rstrip(".,;:")
        else:
            handle_match = re.search(r'@([a-zA-Z0-9_\.]+)', snippet)
            if handle_match:
                handle = handle_match.group(1).rstrip(".,;:")
                if len(handle) > 2 and not handle.endswith(('.com', '.net', '.org')):
                    instagram_url = f"https://instagram.com/{handle}"
    else:
        # For Linktree, Stan Store, Beacons, Booksy, etc.
        website_url = url
        # Scan snippet for Instagram
        inst_match = re.search(r'https?://(?:www\.)?instagram\.com/[a-zA-Z0-9_\.]+', snippet, re.IGNORECASE)
        if inst_match:
            instagram_url = inst_match.group(0).rstrip(".,;:")
        else:
            handle_match = re.search(r'@([a-zA-Z0-9_\.]+)', snippet)
            if handle_match:
                handle = handle_match.group(1).rstrip(".,;:")
                if len(handle) > 2 and not handle.endswith(('.com', '.net', '.org')):
                    instagram_url = f"https://instagram.com/{handle}"
                    
    # Clean the Instagram URL to ensure it is just the main profile
    if instagram_url:
        username = extract_instagram_username(instagram_url)
        if username:
            instagram_url = f"https://instagram.com/{username}"
        else:
            instagram_url = None
    else:
        instagram_url = None
        
    if not website_url:
        website_url = None
        
    return {
        "name": name,
        "niche": niche,
        "city": city,
        "url": url,
        "instagram_url": instagram_url,
        "website_url": website_url,
        "source_domain": source_domain,
        "source_type": source_type,
        "title": title,
        "snippet": snippet
    }
