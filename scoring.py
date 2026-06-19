import re
import httpx
from utils import logger
import config

async def get_pagespeed_score(target_url: str) -> int:
    """
    Queries Google PageSpeed Insights API to analyze the website performance score.
    Returns the score (0-100) or -1 if the check fails or is not configured.
    """
    api_key = config.PAGESPEED_API_KEY
    if not api_key or api_key.strip() == "" or api_key == "your_pagespeed_api_key_here":
        return -1
        
    api_endpoint = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
    
    # Ensure URL has a scheme
    if not (target_url.startswith("http://") or target_url.startswith("https://")):
        url_to_check = "https://" + target_url
    else:
        url_to_check = target_url
        
    params = {
        'url': url_to_check,
        'key': api_key,
        'strategy': 'mobile'  # evaluate mobile speed as it is the most critical for conversions
    }
    
    # Analysis can take up to 20-30 seconds, using 35s timeout
    async with httpx.AsyncClient() as client:
        try:
            logger.info(f"Requesting PageSpeed analysis for: {url_to_check}")
            response = await client.get(api_endpoint, params=params, timeout=35.0)
            if response.status_code == 200:
                data = response.json()
                score_fraction = data['lighthouseResult']['categories']['performance']['score']
                score = int(score_fraction * 100)
                logger.info(f"PageSpeed result for {url_to_check}: {score}/100")
                return score
            else:
                logger.warning(f"PageSpeed API returned status {response.status_code}: {response.text}")
                return -1
        except httpx.TimeoutException:
            logger.warning(f"PageSpeed check timed out for {url_to_check}")
            return -1
        except Exception as e:
            logger.error(f"Error running PageSpeed for {url_to_check}: {e}")
            return -1

def recommend_demo(niche: str, title: str, snippet: str, url: str) -> str:
    """
    Recommends a demo website based on the lead's niche.
    """
    n = niche.lower().strip()
    if n == "fitness":
        return "https://forge-method.vercel.app/#results"
    elif n in ("nails", "beauty"):
        return "https://muse-nail-atelier.vercel.app/"
    elif n in ("creators", "creator"):
        return "https://the-soft-edit-nine.vercel.app/"
    else:
        return "https://the-soft-edit-nine.vercel.app/"

def score_lead(lead_dict: dict) -> tuple:
    """
    Scores a lead from 0 to 10 based on keywords in title, snippet, URL, and domain.
    Also incorporates PageSpeed performance results to adjust prioritization.
    Returns a tuple: (score, score_reason)
    """
    score = 0
    pos_reasons = []
    neg_reasons = []
    
    title = lead_dict.get("title", "").lower()
    snippet = lead_dict.get("snippet", "").lower()
    url = lead_dict.get("url", "").lower()
    niche = lead_dict.get("niche", "").lower()
    city = lead_dict.get("city", "").lower()
    source_type = lead_dict.get("source_type", "")
    pagespeed = lead_dict.get("pagespeed_score", -1)
    
    combined_text = f"{title} {snippet}"
    
    # 1. POSITIVE SIGNALS
    
    # Booking Intent (+3)
    booking_terms = [
        "book", "booking", "appointments", "dm to book", "apply now", 
        "book a call", "schedule", "consultation", "limited spots", 
        "taking clients", "accepting clients", "reserve"
    ]
    matched_bookings = [term for term in booking_terms if term in combined_text]
    if matched_bookings:
        score += 3
        pos_reasons.append(f"booking terms detected ('{matched_bookings[0]}')")
        
    # Niche Matches (+2)
    niche_terms = []
    if niche == "fitness":
        niche_terms = ["fitness coach", "personal trainer", "online coach", "transformation coach", "body recomposition", "coach"]
    elif niche in ("nails", "beauty"):
        niche_terms = ["nail artist", "nail tech", "nail salon", "beauty studio", "biab"]
    elif niche in ("creators", "creator"):
        niche_terms = ["ugc creator", "lifestyle creator", "content creator", "creator", "influencer"]
        
    matched_niches = [term for term in niche_terms if term in combined_text]
    if matched_niches:
        score += 2
        pos_reasons.append(f"niche keyword matched ('{matched_niches[0]}')")
    elif niche in combined_text:
        score += 2
        pos_reasons.append(f"niche matched ('{niche}')")
        
    # Link-in-Bio / Booking Platforms (+2)
    bio_platforms = ["linktr.ee", "stan.store", "beacons.ai", "booksy.com", "fresha.com", "vagaro.com"]
    matched_platforms = [p for p in bio_platforms if p in url or p in combined_text]
    if matched_platforms or source_type in ("linktree", "stan_store", "beacons", "booksy", "fresha", "vagaro"):
        score += 2
        platform_name = matched_platforms[0] if matched_platforms else source_type
        pos_reasons.append(f"uses bio/booking platform ('{platform_name}')")
        
    # Tier-1 Country / City (+1)
    tier1_countries = ["united states", "usa", "us", "united kingdom", "uk", "canada", "australia", "dubai", "uae", "london", "sydney", "toronto"]
    matched_tier1 = [c for c in tier1_countries if c in combined_text or c in city]
    if matched_tier1 or city in ("dallas", "austin", "miami", "brooklyn", "los angeles", "london", "toronto", "dubai"):
        score += 1
        pos_reasons.append(f"targets tier-1 location ('{city.capitalize()}')")
        
    # Email detected (+1)
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = re.findall(email_pattern, combined_text)
    if emails or "email" in combined_text or "dm for email" in combined_text:
        score += 1
        pos_reasons.append("contact email detected or referenced")
        
    # Premium Intent Words (+1)
    premium_words = ["luxury", "premium", "transformation", "studio", "high-end", "exclusive", "signature", "aesthetic", "editorial", "brand", "partnerships"]
    matched_premium = [w for w in premium_words if w in combined_text]
    if matched_premium:
        score += 1
        pos_reasons.append(f"premium intent vocabulary used ('{matched_premium[0]}')")

    # PageSpeed Score: Slow Website (+2)
    if pagespeed != -1 and pagespeed < 60:
        score += 2
        pos_reasons.append(f"website is slow (PageSpeed score: {pagespeed}/100)")

    # 2. NEGATIVE SIGNALS
    
    # Already has custom website (-3)
    if source_type == "business_website":
        if pagespeed != -1 and pagespeed < 60:
            score -= 1
            neg_reasons.append("has a custom website, but it is slow and needs optimization")
        else:
            score -= 3
            neg_reasons.append("already has a custom website on a private domain")
        
    # Large franchise/chain (-2)
    franchise_words = ["franchise", "chain", "corporate", "corporation", "locations nationwide", "inc.", "incorporated", "co.", "ltd"]
    matched_franchise = [w for w in franchise_words if w in combined_text]
    if matched_franchise:
        score -= 2
        neg_reasons.append("appears to be a large franchise or corporate entity")
        
    # Irrelevant (-2)
    core_niche_words = {
        "fitness": ["fit", "train", "coach", "gym", "body", "workout", "physique", "lift", "muscle", "strength", "health", "personal"],
        "nails": ["nail", "salon", "tech", "artist", "manicure", "pedicure", "biab", "gel", "acrylic", "beauty", "lashes", "brows"],
        "creators": ["ugc", "creator", "portfolio", "media", "influencer", "brand", "content", "collab", "ugc creator", "lifestyle"]
    }
    niche_words = core_niche_words.get(niche, [])
    has_core_word = any(w in combined_text for w in niche_words)
    if not has_core_word:
        score -= 2
        neg_reasons.append("lacks relevant niche terms in search result")
        
    # No clear contact path (-2)
    if not lead_dict.get("instagram_url") and not lead_dict.get("website_url") and source_type == "other":
        score -= 2
        neg_reasons.append("no apparent direct social media or site contact route")
        
    # Marketplace search/category page (-2)
    marketplace_indicators = ["/search", "/near-me", "/best-", "/browse", "/top-", "/category", "/reviews", "top 10", "best 10", "ranking", "find a"]
    matched_market = [ind for ind in marketplace_indicators if ind in url or ind in combined_text]
    if matched_market:
        score -= 2
        neg_reasons.append("looks like a search index or directory rather than an individual business page")
        
    # Too vague (-1)
    if len(snippet) < 40:
        score -= 1
        neg_reasons.append("snippet is too short/vague to evaluate details")

    # PageSpeed Score: Already Fast/Optimized (-1)
    if pagespeed != -1 and pagespeed >= 85:
        score -= 1
        neg_reasons.append(f"website is already fast and optimized (PageSpeed score: {pagespeed}/100)")
        
    # Clamp score between 0 and 10
    final_score = max(0, min(score, 10))
    
    # 3. CONSTRUCT REASON STRING
    if final_score >= 7:
        sentiment = "Strong lead"
    elif final_score >= 5:
        sentiment = "Average lead"
    else:
        sentiment = "Weak lead"
        
    if pos_reasons:
        pos_str = "because " + ", ".join(pos_reasons)
    else:
        pos_str = "with standard signals"
        
    if neg_reasons:
        neg_str = ", but note: " + ", ".join(neg_reasons)
    else:
        neg_str = ""
        
    reason_str = f"{sentiment} {pos_str}{neg_str}."
    reason_str = reason_str[0].upper() + reason_str[1:]
    
    return final_score, reason_str
