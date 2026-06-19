import json
import httpx
from utils import logger
import config

FITNESS_TEMPLATE = "hey {name}, loved your fitness page. noticed you're booking through linktree/dms. I built this premium fitness portfolio demo recently: https://forge-method.vercel.app/#results doing a few sites for $300 (usually $700+) to build case studies. open to seeing what a custom page could look like for you?"

NAILS_TEMPLATE = "hey {name}, love your nail work. noticed you're booking clients through dms. I built this clean website demo recently: https://muse-nail-atelier.vercel.app/ doing a few sites for $300 (usually $700+) to build case studies. open to seeing what a custom page could look like for you?"

CREATOR_TEMPLATE = "hey {name}, love your creator page. noticed you're using linktree/dms. I built this premium creator portfolio demo recently: https://the-soft-edit-nine.vercel.app/ doing a few sites for $300 (usually $700+) to build case studies. open to seeing what a custom page could look like for you?"

def get_suggested_message_static(niche: str, name: str = None) -> str:
    """Fallback static template message."""
    display_name = name if name and name.lower() != "there" else "there"
    n = niche.lower().strip()
    
    if n == "fitness":
        template = FITNESS_TEMPLATE
    elif n in ("nails", "beauty"):
        template = NAILS_TEMPLATE
    else:
        template = CREATOR_TEMPLATE
        
    return template.format(name=display_name)

def generate_custom_angle_static(niche: str, source_type: str) -> str:
    """Fallback static template angle."""
    n = niche.lower().strip()
    s = source_type.lower().strip()
    
    if s == "linktree":
        return "Your Instagram already looks premium, but your booking path is split between multiple links. A single clean landing page could make the flow much simpler: see your work → understand the offer → book."
    elif s in ("booksy", "fresha", "vagaro"):
        return f"You already have booking infrastructure on {source_type.capitalize()}, but a premium landing page could make the brand feel more high-end before people reach the booking step."
        
    if n == "fitness":
        return "One strong landing page could show transformations, explain your method, build trust, and push visitors toward consultation calls."
    elif n in ("nails", "beauty"):
        return "A clean website could turn your Instagram traffic into appointments by showing services, pricing, portfolio, hygiene standards, and booking CTA in one place."
    elif n in ("creators", "creator"):
        return "A premium media-kit style website could make your brand look more serious to sponsors and make partnerships easier to close."
        
    return "A premium website could unify your brand, build immediate authority, and simplify the path for visitors to convert."

async def generate_gemini_outreach(lead: dict) -> dict:
    """
    Queries Gemini 3.5 Flash using direct HTTP REST API to generate a personalized
    custom angle and cold outreach message in JSON format.
    Returns a dict with 'custom_angle' and 'suggested_message' or None on failure.
    """
    api_key = config.GEMINI_API_KEY
    if not api_key or api_key.strip() == "" or api_key == "your_gemini_api_key_here":
        return None

    # URL endpoint for Gemini 3.5 Flash
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={api_key}"
    
    name = lead.get("name", "there")
    niche = lead.get("niche", "general")
    city = lead.get("city", "unknown")
    source_type = lead.get("source_type", "other")
    snippet = lead.get("snippet", "")
    pagespeed = lead.get("pagespeed_score", -1)
    
    demo_links = {
        "fitness": "https://forge-method.vercel.app/#results",
        "nails": "https://muse-nail-atelier.vercel.app/",
        "beauty": "https://muse-nail-atelier.vercel.app/",
        "creators": "https://the-soft-edit-nine.vercel.app/",
        "creator": "https://the-soft-edit-nine.vercel.app/"
    }
    recommended_demo = demo_links.get(niche.lower(), "https://the-soft-edit-nine.vercel.app/")
    
    speed_context = ""
    if pagespeed != -1:
        if pagespeed < 60:
            speed_context = f"PageSpeed score is {pagespeed}/100 (Slow website - this is a major selling point!)."
        else:
            speed_context = f"PageSpeed score is {pagespeed}/100 (Already fast website)."
            
    prompt = (
        f"You are an expert cold outreach copywriter who writes extremely brief, casual, and natural Instagram DMs.\n"
        f"I build premium, conversion-focused websites and landing pages for local businesses and creators.\n"
        f"I am offering to build a custom website at a case-study price of $300 (usually $700+).\n\n"
        f"Lead Details:\n"
        f"- Name: {name}\n"
        f"- Niche: {niche}\n"
        f"- City: {city}\n"
        f"- Platform: {source_type}\n"
        f"- Snippet Details: {snippet}\n"
        f"- Page Speed Context: {speed_context}\n\n"
        f"Recommended Demo: {recommended_demo}\n\n"
        f"Instructions:\n"
        f"Generate a JSON object containing:\n"
        f"1. \"custom_angle\": A short 1-2 sentence angle explaining how to pitch this specific lead. Mention if their current site is slow (PageSpeed score < 60) or if they are split across Linktree/booking directories and need a high-end unified landing page.\n"
        f"2. \"suggested_message\": A highly personalized, brief, casual, low-pressure outreach DM. STRICT LIMIT: Keep it between 35-50 words maximum. It must feel like a real human typed a quick message on a phone. Do not sound corporate, salesy, or robotic. Do not use exclamation marks or annoying marketing emojis. Write in a lower-cased style. Reference a specific detail from their snippet. Organic transition to the demo link ({recommended_demo}) and the $300 case-study price. Ends with a low-friction question. Keep it to a single short paragraph.\n\n"
        f"Response must be valid JSON in this structure:\n"
        f'{{\n  "custom_angle": "...",\n  "suggested_message": "..."\n}}'
    )
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.2
        }
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            logger.info(f"Querying Gemini API for personalized outreach for lead: {name}")
            response = await client.post(url, json=payload, headers=headers, timeout=15.0)
            if response.status_code == 200:
                data = response.json()
                text_content = data['candidates'][0]['content']['parts'][0]['text']
                parsed = json.loads(text_content)
                logger.info(f"Successfully generated Gemini outreach for {name}")
                return parsed
            else:
                logger.warning(f"Gemini API returned status {response.status_code}: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            return None

async def get_outreach_for_lead(lead: dict) -> tuple:
    """
    Primary API to get custom angle and outreach copy.
    Attempts to use Gemini API first for personalization.
    Falls back to static templates if Gemini fails or is not configured.
    Returns a tuple: (custom_angle, suggested_message)
    """
    # Try Gemini first
    gemini_data = await generate_gemini_outreach(lead)
    if gemini_data and isinstance(gemini_data, dict):
        angle = gemini_data.get("custom_angle")
        msg = gemini_data.get("suggested_message")
        if angle and msg:
            return angle, msg
            
    # Fallback to static
    logger.info("Using static template fallbacks for outreach copy.")
    angle = generate_custom_angle_static(lead.get("niche", ""), lead.get("source_type", ""))
    msg = get_suggested_message_static(lead.get("niche", ""), lead.get("name", ""))
    return angle, msg
