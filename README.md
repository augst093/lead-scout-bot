# Lead Scout Bot 🚀

Lead Scout Bot is a complete, lightweight, and secure personal lead generation assistant designed to help premium website design/development services discover high-quality candidate clients. 

It searches public indexes using the **Brave Search API**, filters results based on customizable niche keywords and location parameters, scores each prospect (0-10), and sends highly-qualified leads directly to your Telegram chat. 

---

## 🔒 Safety & Platform Compliance Rules

This tool is designed purely for **lead discovery and aggregation**. To ensure safety, stability, and compatibility with terms of service:

*   **NO Instagram Login**: The bot does not require or accept Instagram credentials.
*   **NO Profile Scraping**: The bot does not scrape Instagram profiles directly. It only collects public search results indexed by Brave Search.
*   **NO Platform Actions**: The bot does not perform automated DMs, comments, follows, likes, or messaging of any kind.
*   **Manual Outreach Only**: You receive the leads in Telegram and must manually review and message them yourself.
*   **NO Proxies/Captcha Bypasses**: The bot operates purely via standard public API request routes.

---

## 🛠️ Tech Stack

*   **Python 3.11+**
*   **python-telegram-bot (v20+)** (Modern asyncio-based Telegram client wrapper)
*   **SQLite** (Embedded local database for settings and lead deduplication)
*   **Brave Search Web API** (For retrieving search results securely and legally)
*   **APScheduler** (Under the hood of the Telegram JobQueue, for scheduled runs)
*   **python-dotenv** (Environment variable configuration)

---

## 📂 Project Structure

```
lead_scout_bot/
│
├── .env.example            # Template for environment settings
├── README.md               # Setup and usage guide (this file)
├── requirements.txt        # Python package dependencies
│
├── bot.py                  # Main entry point (commands & interactive callback handler)
├── config.py               # Config loader (merges environment and database parameters)
├── database.py             # SQLite connection, schema setup, settings CRUD, and deduplication logic
├── search_engine.py        # Brave Search Web API client wrapper
├── query_builder.py        # Dork query compiler optimized for niches & cities
├── lead_parser.py          # Platform detector (Instagram, Linktree, Booksy, etc.) & URL cleanups
├── scoring.py              # Evaluates leads 0-10 on custom signals and selects niche demos
├── message_templates.py    # Outreach templates (Fitness, Nails, Creators) & custom pitch angles
├── scheduler.py            # Round-robin scheduled background search manager
├── export_csv.py           # Exports lead database to CSV format
└── utils.py                # Logging configuration, URL normalizers, and handle extractors
```

---

## 🚀 Setup Instructions

Follow these step-by-step instructions to get the bot running on Windows.

### Step 1: Create a Telegram Bot
1. Open Telegram and search for [@BotFather](https://t.me/BotFather).
2. Click **Start** and send `/newbot`.
3. Give your bot a name (e.g., `My Lead Scout`) and a unique username (must end in `_bot`, e.g., `lead_scout_123_bot`).
4. Copy the API token provided (e.g., `1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ`). This is your `TELEGRAM_BOT_TOKEN`.

### Step 2: Get Your Telegram User ID
Only you should be allowed to use this bot.
1. Search Telegram for [@userinfobot](https://t.me/userinfobot) or [@IDBot](https://t.me/idbot).
2. Click **Start**.
3. Copy the numeric ID returned (e.g., `987654321`). This is your `ADMIN_TELEGRAM_ID`.

### Step 3: Configure Search & AI API Credentials (Brave, Google, Gemini, PageSpeed)
You can configure the search engines and AI capabilities inside your `.env` file:
*   **Brave Search API Key**: (Optional) Register at the [Brave Search API Dashboard](https://api.search.brave.com/app/dashboard).
*   **Google Custom Search (CSE)**: (Optional) Get an API key from the Google Cloud Console and a Search Engine ID (CX) from the Programmable Search Engine control panel.
*   **Google PageSpeed Insights API**: (Optional) Get a free key from Google Cloud Console to analyze website speeds of leads.
*   **Gemini API Key**: (Optional) Get an API key from Google AI Studio to write highly personalized cold DMs.

### Step 4: Configure Environment Variables
1. In the `lead_scout_bot/` directory, create a copy of `.env.example` and name it `.env`.
2. Open the `.env` file and replace the placeholder values with your credentials:
   ```ini
   TELEGRAM_BOT_TOKEN=1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ
   ADMIN_TELEGRAM_ID=987654321
   
   # Search APIs (Configure at least one)
   BRAVE_API_KEY=your_brave_key_here
   GOOGLE_API_KEY=your_google_cloud_api_key_here
   GOOGLE_CX=your_cse_search_engine_id_here
   
   # Advanced AI & Website Performance Analysis
   GEMINI_API_KEY=your_gemini_api_key_here
   PAGESPEED_API_KEY=your_google_cloud_api_key_here
   
   # Defaults
   MINIMUM_SCORE=7
   DEFAULT_CITIES=Dallas,Austin,Miami,Brooklyn,Los Angeles,London,Toronto,Dubai
   ENABLED_NICHES=fitness,nails,creators
   SCHEDULED_SEARCH_ENABLED=false
   SCHEDULED_SEARCH_FREQUENCY_HOURS=2
   MAX_LEADS_PER_RUN=10
   ```

### Step 5: Install Python Dependencies
Open command prompt (`cmd`) or PowerShell, navigate to your project folder, and run:
```bash
pip install -r requirements.txt
```

---

## 🏁 Running the Bot

To start the bot, run the following command in your terminal:
```bash
python bot.py
```
Upon startup, the bot will automatically initialize the `leads.db` SQLite database, load your settings, set up background scheduling (if enabled), and start listening for messages.

---

## 🤖 How to Use: Commands

### 🔍 Discovery
*   `/start` - Shows the welcome message, active demos, and quick-action menu.
*   `/help` - Lists all available commands and explanations.
*   `/find` - Triggers an **interactive setup flow** using inline buttons:
    1. Select a niche (Fitness, Nails, Creators, All).
    2. Choose from default cities (or type a custom one).
    3. Choose maximum leads to search for.
    4. Automatically executes searches and sends qualified leads here.
*   `/find_fitness <city>` - Fast search for fitness coaches/trainers (e.g., `/find_fitness Austin`).
*   `/find_nails <city>` - Fast search for nail techs/beauty studios (e.g., `/find_nails Brooklyn`).
*   `/find_creators <city>` - Fast search for UGC/lifestyle creators (e.g., `/find_creators London`).

### 📂 Lead Tracking & Workflows
*   `/next` - Shows the next unreviewed lead in the database with interactive buttons.
*   `/top` - Summarizes the top leads (score 8-10) recently discovered.
*   `/today` - Summarizes leads found today.
*   `/saved` - Lists leads you have clicked "Save" on.
*   `/messaged` - Lists leads you have marked as messaged.
*   `/followups` - Lists leads marked for tomorrow's follow-up.
*   `/clear_bad` - Purges database entries marked as "skipped", "bad_lead", or below your minimum score to keep the database tidy.

### ⚙️ System Controls
*   `/stats` - Shows stats (Total leads, leads by niche, score breakdown, status distribution).
*   `/export` - Exports your entire lead list to a CSV file and delivers it directly as an attached document in chat.
*   `/settings` - Opens the interactive configuration panel where you can modify the minimum score, target cities list, enabled niches, scheduler frequency, and run limits.
*   `/search_status` - Displays whether background scheduler searches are currently active.
*   `/pause` - Pauses/disables background scheduled runs.
*   `/resume` - Resumes/enables background scheduled runs.

---

## 🔘 Interactive Buttons Attached to Every Lead

Each lead card sent to Telegram includes a custom layout of action buttons:
1.  **🔗 Open Lead**: Opens the candidate's public website or social URL.
2.  **💻 Open Demo**: Opens the matching premium demo website recommended for this niche.
3.  **✅ Save**: Sets lead status to `saved` (shows in `/saved`).
4.  **❌ Skip**: Sets lead status to `skipped` (removes from next queues).
5.  **✉️ Mark Messaged**: Sets status to `messaged` (shows in `/messaged`).
6.  **📅 Follow-up Tomorrow**: Sets status to `follow_up_needed` and schedules a reminder date for tomorrow (shows in `/followups`).
7.  **👎 Bad Lead**: Sets status to `bad_lead`.
8.  **🔒 Closed**: Sets status to `closed` (successfully converted lead).
9.  **💡 Generate Custom Angle**: Sends a separate copyable chat message outlining a personalized marketing angle for the prospect (explaining why they need a custom landing page vs. their current Linktree/Booksy setups) and formats a pre-filled template message.

---

## 📈 Lead Scoring System (0-10)

The bot automatically scores leads out of 10 points:
*   **Positive Signals**:
    *   `+3` - Direct booking intents found in snippets (e.g., "DM to book", "book a call").
    *   `+2` - Match on niche keyword (e.g., "nail tech", "personal trainer").
    *   `+2` - Uses bio-link/booking directories (e.g., Linktree, Beacons, Booksy, Vagaro, Fresha).
    *   `+1` - Location matches Tier-1 countries/cities.
    *   `+1` - Email is detected in snippet.
    *   `+1` - Premium marketing terms (e.g., "luxury", "exclusive", "aesthetic", "signature").
*   **Negative Signals**:
    *   `-3` - Already has a custom private website domain.
    *   `-2` - Matches chain/franchise/corporate signals.
    *   `-2` - Marketplace list page (e.g., Yelp search directory).
    *   `-2` - No contact route.
    *   `-1` - Snippet is too short/vague.

---

## ⚙️ How Background Scheduled Search Works

If enabled (`scheduled_search_enabled = true`):
1.  The bot runs background scans periodically based on your configured interval (e.g., every 2 hours).
2.  **Round-Robin City Selection**: In each run, the bot selects *one* city from your default list and rotates to the next city on the next run. This distributes API usage safely and avoids rate limits.
3.  For that city, it queries all enabled niches.
4.  It normalizes URLs and detects Instagram handles to ensure **duplicate leads are never sent twice**.
5.  It pushes new leads with a score equal to or higher than `minimum_score` directly to your Telegram chat, up to your `max_leads_per_run` setting.

---

## 🔧 Troubleshooting

### 1. Bot replies "Access denied" to all commands
Check that the `ADMIN_TELEGRAM_ID` in your `.env` matches your numerical Telegram user ID exactly. If you changed the `.env` file, restart the bot.

### 2. Search returns "Brave API Key is missing" or "Search API credentials are missing"
Make sure you have configured either `BRAVE_API_KEY` or both `GOOGLE_API_KEY` and `GOOGLE_CX` inside your `.env` file. If using Google Custom Search, see item 5 below.

### 3. Background scheduler is not running
Verify that:
*   `python-telegram-bot[job-queue]` is correctly installed (standard `pip install -r requirements.txt` handles this).
*   Scheduled search is enabled. Type `/search_status` in Telegram to inspect.
*   The frequency interval in hours is at least 1.

### 4. Database Errors
If you get database locks or corruptions, terminate the bot (`Ctrl+C`), delete `leads.db`, and run `python bot.py` again. The bot will rebuild the database from scratch and apply defaults.

### 5. Google Custom Search returns HTTP 403 Permission Denied
If your logs show `Google Search API error (status 403): This project does not have the access to Custom Search JSON API.`:
1.  Go to the [Google Cloud Console API Library](https://console.cloud.google.com/apis/library).
2.  Select the project matching your `GOOGLE_API_KEY`.
3.  Search for **Custom Search API** and click **Enable**.
4.  If Google Search fails, the bot will automatically fall back to Brave Search.

### 6. Gemini API returns HTTP 429 Quota Exceeded or 404 Not Found
*   **429 (Resource Exhausted)**: If the bot logs a `WARNING - Gemini API returned status 429` error, your key has exceeded its daily or per-minute requests quota. The bot automatically handles this by **falling back to static templates** (so your outreach messages and angles are still generated cleanly without crashing). Check your usage dashboard at Google AI Studio or add a billing account to increase limits.
*   **404 (Model Not Found)**: If you get a model-not-found error, verify the model ID naming conventions supported by your specific API key. The bot is set up to call the `gemini-2.0-flash` model, which is widely available.

