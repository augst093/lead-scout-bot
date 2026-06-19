import asyncio
import httpx
import random
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup
from utils import logger, clean_snippet
import config
from ddgs import DDGS

class SearchAPIKeysMissing(Exception):
    """Exception raised when all configured search engines fail or lack credentials."""
    pass

class BraveSearchAPIKeyMissing(Exception):
    """Fallback exception kept for backward compatibility."""
    pass

async def search_ddg(query: str, count: int = 10) -> list:
    """
    Queries DuckDuckGo search using the duckduckgo_search library.
    It is keyless, free, and robust.
    """
    # Throttle slightly to be polite
    await asyncio.sleep(1.0)
    try:
        logger.info(f"Querying DuckDuckGo Search (ddgs): '{query}'")
        def run_search():
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=count))
                
        loop = asyncio.get_running_loop()
        raw_results = await loop.run_in_executor(None, run_search)
        
        results = []
        for item in raw_results:
            r_url = item.get("href", "")
            if not r_url:
                continue
            parsed_url = urlparse(r_url)
            domain = parsed_url.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
                
            results.append({
                "title": item.get("title", ""),
                "url": r_url,
                "snippet": clean_snippet(item.get("body", "")),
                "source_domain": domain
            })
        logger.info(f"DuckDuckGo (ddgs) returned {len(results)} search results.")
        return results
    except Exception as e:
        logger.error(f"Error querying DuckDuckGo (ddgs) for '{query}': {e}")
        return []

async def search_serper(query: str, count: int = 10) -> list:
    """
    Queries Serper.dev Google Search API if configured.
    Provides 2,500 free searches on registration.
    """
    api_key = config.SERPER_API_KEY
    if not api_key or api_key.strip() == "" or api_key == "your_serper_api_key_here":
        return []
        
    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "q": query,
        "num": max(1, min(count, 20))
    }
    
    await asyncio.sleep(0.5)
    
    async with httpx.AsyncClient() as client:
        try:
            logger.info(f"Querying Serper.dev Search: '{query}'")
            response = await client.post(url, headers=headers, json=payload, timeout=15.0)
            if response.status_code != 200:
                logger.error(f"Serper.dev returned error {response.status_code}: {response.text}")
                return []
                
            data = response.json()
            organic = data.get("organic", [])
            results = []
            for item in organic:
                r_url = item.get("link", "")
                if not r_url:
                    continue
                parsed_url = urlparse(r_url)
                domain = parsed_url.netloc.lower()
                if domain.startswith("www."):
                    domain = domain[4:]
                    
                results.append({
                    "title": item.get("title", ""),
                    "url": r_url,
                    "snippet": clean_snippet(item.get("snippet", "")),
                    "source_domain": domain
                })
            return results
        except Exception as e:
            logger.error(f"Error querying Serper.dev for '{query}': {e}")
            return []

async def search_searxng(query: str, count: int = 10) -> list:
    """
    Queries public SearXNG instances in a rotating pool.
    Keyless, free, and aggregates Google/Bing/DDG results.
    """
    # A list of active public SearXNG instances to try
    instances = [
        "https://searx.be",
        "https://paulgo.io",
        "https://baresearch.org",
        "https://searx.space",
        "https://searx.work",
        "https://searxng.site",
        "https://search.ononoki.org",
        "https://searx.priv.si",
        "https://northboot.xyz",
        "https://search.disroot.org",
        "https://searx.mx",
        "https://searx.xyz",
        "https://searx.or.id",
        "https://priv.au",
        "https://searx.ch"
    ]
    
    # Shuffle to distribute load randomly
    random.shuffle(instances)
    
    for instance in instances:
        url = f"{instance}/search"
        params = {
            "q": query,
            "format": "json",
            "categories": "general",
            "language": "en"
        }
        
        await asyncio.sleep(0.5)
        
        async with httpx.AsyncClient() as client:
            try:
                logger.info(f"Querying SearXNG instance '{instance}' for: '{query}'")
                response = await client.get(url, params=params, timeout=10.0)
                
                # Check for 403 Forbidden or other errors (some instances disable json format)
                if response.status_code != 200:
                    logger.warning(f"SearXNG instance '{instance}' returned status {response.status_code}. Trying next...")
                    continue
                    
                data = response.json()
                raw_results = data.get("results", [])
                
                if not raw_results:
                    logger.warning(f"SearXNG instance '{instance}' returned no results. Trying next...")
                    continue
                    
                results = []
                for item in raw_results:
                    r_url = item.get("url", "")
                    if not r_url:
                        continue
                    parsed_url = urlparse(r_url)
                    domain = parsed_url.netloc.lower()
                    if domain.startswith("www."):
                        domain = domain[4:]
                        
                    results.append({
                        "title": item.get("title", ""),
                        "url": r_url,
                        "snippet": clean_snippet(item.get("content", "")),
                        "source_domain": domain
                    })
                    if len(results) >= count:
                        break
                        
                logger.info(f"SearXNG instance '{instance}' successfully returned {len(results)} results.")
                return results
                
            except httpx.HTTPError as e:
                logger.warning(f"SearXNG instance '{instance}' failed with network error: {e}. Trying next...")
            except Exception as e:
                logger.warning(f"SearXNG instance '{instance}' failed to parse: {e}. Trying next...")
                
    logger.error("All public SearXNG instances failed to retrieve results.")
    return []

async def search_serpapi(query: str, count: int = 10) -> list:
    """
    Queries SerpAPI Google Search.
    """
    api_key = config.SERPAPI_KEY
    if not api_key or api_key.strip() == "" or api_key == "your_serpapi_key_here":
        return []
        
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google",
        "q": query,
        "api_key": api_key,
        "num": max(1, min(count, 10))
    }
    
    await asyncio.sleep(0.5)
    
    async with httpx.AsyncClient() as client:
        try:
            logger.info(f"Querying SerpAPI Search: '{query}'")
            response = await client.get(url, params=params, timeout=15.0)
            if response.status_code != 200:
                logger.error(f"SerpAPI returned error {response.status_code}: {response.text}")
                return []
                
            data = response.json()
            organic = data.get("organic_results", [])
            results = []
            for item in organic:
                r_url = item.get("link", "")
                if not r_url:
                    continue
                parsed_url = urlparse(r_url)
                domain = parsed_url.netloc.lower()
                if domain.startswith("www."):
                    domain = domain[4:]
                    
                results.append({
                    "title": item.get("title", ""),
                    "url": r_url,
                    "snippet": clean_snippet(item.get("snippet", "")),
                    "source_domain": domain
                })
            return results
        except Exception as e:
            logger.error(f"Error querying SerpAPI for '{query}': {e}")
            return []

async def search_google(query: str, count: int = 10) -> list:
    """
    Queries Google Custom Search.
    """
    api_key = config.GOOGLE_API_KEY
    cx = config.GOOGLE_CX
    if not api_key or not cx or api_key.strip() == "" or cx.strip() == "" or api_key.startswith("your_"):
        return []

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": cx,
        "q": query,
        "num": max(1, min(count, 10))
    }
    
    await asyncio.sleep(0.5)
    
    async with httpx.AsyncClient() as client:
        try:
            logger.info(f"Querying Google Search: '{query}'")
            response = await client.get(url, params=params, timeout=10.0)
            if response.status_code != 200:
                return []
                
            data = response.json()
            items = data.get("items", [])
            results = []
            for item in items:
                r_url = item.get("link", "")
                if not r_url:
                    continue
                parsed_url = urlparse(r_url)
                domain = parsed_url.netloc.lower()
                if domain.startswith("www."):
                    domain = domain[4:]
                    
                results.append({
                    "title": item.get("title", ""),
                    "url": r_url,
                    "snippet": clean_snippet(item.get("snippet", "")),
                    "source_domain": domain
                })
            return results
        except Exception as e:
            return []

async def search_brave(query: str, count: int = 10) -> list:
    """
    Queries Brave Search.
    """
    api_key = config.BRAVE_API_KEY
    if not api_key or api_key.strip() == "" or api_key == "your_brave_search_api_key_here":
        return []

    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key
    }
    params = {
        "q": query,
        "count": max(1, min(count, 20))
    }
    
    await asyncio.sleep(1.0)
    
    async with httpx.AsyncClient() as client:
        try:
            logger.info(f"Querying Brave Search: '{query}'")
            response = await client.get(url, headers=headers, params=params, timeout=10.0)
            if response.status_code != 200:
                return []
                
            data = response.json()
            web = data.get("web", {})
            raw_results = web.get("results", [])
            results = []
            for r in raw_results:
                r_url = r.get("url", "")
                if not r_url:
                    continue
                parsed_url = urlparse(r_url)
                domain = parsed_url.netloc.lower()
                if domain.startswith("www."):
                    domain = domain[4:]
                    
                results.append({
                    "title": r.get("title", ""),
                    "url": r_url,
                    "snippet": clean_snippet(r.get("description", "")),
                    "source_domain": domain
                })
            return results
        except Exception as e:
            return []

async def search_web_results(query: str, count: int = 10) -> list:
    """
    Search Router.
    Prioritizes user-configured API keys first for premium/exact results, 
    and automatically falls back to free, unlimited, and keyless options.
    
    Order:
    1. Serper.dev (if configured - 2500 free queries)
    2. Google Custom Search (if configured - 100/day free)
    3. SerpAPI (if configured - 100/250 free)
    4. Brave Search (if configured - 1000/month free)
    5. DuckDuckGo (Free, Keyless, Unlimited via ddgs library)
    6. SearXNG Rotating Pool (Free, Keyless, Unlimited)
    """
    # 1. Try Serper.dev if configured (2500 free queries)
    has_serper = config.SERPER_API_KEY and config.SERPER_API_KEY != "your_serper_api_key_here"
    if has_serper:
        logger.info("Trying Serper.dev...")
        results = await search_serper(query, count)
        if results:
            return results

    # 2. Try Google Custom Search if configured
    has_google = config.GOOGLE_API_KEY and config.GOOGLE_CX and config.GOOGLE_API_KEY != "your_google_api_key_here"
    if has_google:
        logger.info("Trying Google Custom Search...")
        results = await search_google(query, count)
        if results:
            return results

    # 3. Try SerpAPI if configured
    has_serp = config.SERPAPI_KEY and config.SERPAPI_KEY != "your_serpapi_key_here"
    if has_serp:
        logger.info("Trying SerpAPI...")
        results = await search_serpapi(query, count)
        if results:
            return results
            
    # 4. Try Brave Search if configured
    has_brave = config.BRAVE_API_KEY and config.BRAVE_API_KEY != "your_brave_search_api_key_here"
    if has_brave:
        logger.info("Trying Brave Search...")
        results = await search_brave(query, count)
        if results:
            return results
            
    # 5. Try DuckDuckGo first as the primary free keyless option (unlimited)
    logger.info("No active search API keys found or all keys rate-limited. Trying DuckDuckGo keyless search...")
    results = await search_ddg(query, count)
    if results:
        return results
        
    # 6. Try SearXNG keyless rotating pool next
    logger.info("DuckDuckGo failed or was throttled. Trying SearXNG rotation fallback...")
    results = await search_searxng(query, count)
    if results:
        return results
            
    return []
