import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Admin Credentials
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")

try:
    ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", 0))
except (ValueError, TypeError):
    ADMIN_TELEGRAM_ID = 0

# Extended APIs
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CX = os.getenv("GOOGLE_CX")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PAGESPEED_API_KEY = os.getenv("PAGESPEED_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

# Database file — use /data/ volume on Fly.io, fallback to local for dev
_data_dir = "/data" if os.path.isdir("/data") else "."
DB_FILE = os.path.join(_data_dir, "leads.db")

# Base defaults (used to seed database if not already present)
DEFAULT_MINIMUM_SCORE = int(os.getenv("MINIMUM_SCORE", 7))

raw_cities = os.getenv("DEFAULT_CITIES", "Dallas,Austin,Miami,Brooklyn,Los Angeles,London,Toronto,Dubai")
DEFAULT_CITIES = [c.strip() for c in raw_cities.split(",") if c.strip()]

raw_niches = os.getenv("ENABLED_NICHES", "fitness,nails,creators")
DEFAULT_NICHES = [n.strip().lower() for n in raw_niches.split(",") if n.strip()]

DEFAULT_SCHEDULED_SEARCH_ENABLED = os.getenv("SCHEDULED_SEARCH_ENABLED", "false").lower() == "true"

try:
    DEFAULT_SCHEDULED_SEARCH_FREQUENCY_HOURS = int(os.getenv("SCHEDULED_SEARCH_FREQUENCY_HOURS", 2))
except (ValueError, TypeError):
    DEFAULT_SCHEDULED_SEARCH_FREQUENCY_HOURS = 2

try:
    DEFAULT_MAX_LEADS_PER_RUN = int(os.getenv("MAX_LEADS_PER_RUN", 10))
except (ValueError, TypeError):
    DEFAULT_MAX_LEADS_PER_RUN = 10
