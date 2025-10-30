# WhatsApp Group Daily Agent API (Flask + Python, Cohere + SerpAPI)

This Flask API generates one engaging, non-repeating daily item based on the weekday (IST), adds birthdays from `list.txt`, caches the first response per IST day, and returns a strict JSON payload suitable for Apple Shortcuts “Get Contents of URL” to forward to a WhatsApp group.

Core features:
- IST-aware daily content rules (Mon–Sun) using SerpAPI + Cohere
- Read birthdays from `list.txt` and add to the day’s message
- First call per IST day is cached and served for subsequent calls that day
- Non-repetition via normalized history per weekday
- Robust retries and safe fallbacks; strict JSON with success/error for Shortcuts
- Admin endpoints for preview and cache reset (token protected)

Endpoints:
- GET /health
- GET /daily
- GET /version
- GET /schema
- GET /preview?day=MONDAY (requires token if APP_TOKEN is set)
- GET /reset-cache (requires token if APP_TOKEN is set)

Environment variables:
- SERPAPI_API_KEY: Your SerpAPI key
- COHERE_API_KEY: Your Cohere API key
- APP_TOKEN: Optional token. If set, /daily also requires it via `?token=...` or Authorization: Bearer.

Install and run locally
1) Python 3.10+ recommended
2) Create venv and install
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt

3) Set environment variables
   export SERPAPI_API_KEY="..."
   export COHERE_API_KEY="..."
   # optional
   export APP_TOKEN="supersecrettoken"

4) Run
   python app.py
   # or FLASK_ENV=development python app.py

5) Test
   curl "http://127.0.0.1:5000/health"
   curl "http://127.0.0.1:5000/daily"
   # if APP_TOKEN set:
   curl "http://127.0.0.1:5000/daily?token=supersecrettoken"
   curl "http://127.0.0.1:5000/preview?day=WEDNESDAY&token=supersecrettoken"
   curl "http://127.0.0.1:5000/reset-cache?token=supersecrettoken"

PythonAnywhere deployment
1) Upload repository files to your PA account (or clone from git).
2) Create and activate a virtualenv on PythonAnywhere and install deps:
   mkvirtualenv --python=/usr/bin/python3.10 whatsapp-daily
   pip install -r /path/to/your/app/requirements.txt
3) On the Web tab:
   - Set “WSGI configuration file” to use the included `wsgi.py` (see below).
   - Set Environment variables: SERPAPI_API_KEY, COHERE_API_KEY, optional APP_TOKEN
   - Reload the web app after changes.
4) File structure example on PA:
   /home/username/yourapp/
     - app.py
     - wsgi.py
     - requirements.txt
     - list.txt
     - data/ (created at runtime)

WSGI file (wsgi.py)
- This repo includes a `wsgi.py`. If you need to create it manually on PA, put it at the project root and configure the Web tab to point to it.
- Content is essentially:
  import sys, os
  from pathlib import Path
  BASE_DIR = Path(__file__).parent.resolve()
  if str(BASE_DIR) not in sys.path:
      sys.path.insert(0, str(BASE_DIR))
  from app import app as application

Apple Shortcuts integration (iOS)
- Goal: Call GET /daily and forward the content to your WhatsApp group.
- Steps:
  1) Create a new Shortcut “Daily Group Message”
  2) Action: Get Contents of URL
     - URL: https://your-pythonanywhere-domain/daily
     - Method: GET
     - If using token: add a Query Item token=YOUR_TOKEN or Header Authorization: Bearer YOUR_TOKEN
     - Response: JSON
  3) Action: If [Get Dictionary Value of success] is true:
       - Get Dictionary Value message
       - Optionally prepend birthdays: Get Dictionary Value birthdays_today (list)
         - If count > 0, you already get it included at top of “message” by the API
       - Send message to WhatsApp group (e.g., using “Share” or “Send Message via WhatsApp” action)
     Otherwise:
       - Get Dictionary Value error_message
       - Optionally notify yourself (do not post to group)
- Schedule this Shortcut to run daily at your chosen IST time via Automation.

Strict JSON contract
Success response:
{
  "success": true,
  "version": "1.0.0",
  "date_ist": "YYYY-MM-DD",
  "weekday": "MONDAY..SUNDAY",
  "cache_hit": true|false,
  "birthdays_today": ["Name1", "Name2", ...],
  "anniversaries_today": [{"names": ["Name1","Name2"], "year": 2015, "years": 10}],
  "content_type": "quote|joke|news|movies|riddle|prompt|emoji",
  "title": "string",
  "message": "string",
  "items": [...],
  "metadata": {...}
}

Error response (still HTTP 200 for Apple Shortcuts):
{
  "success": false,
  "version": "1.0.0",
  "date_ist": "YYYY-MM-DD",
  "weekday": "MONDAY..SUNDAY",
  "error_code": "string",
  "error_message": "string"
}

Sample success response (example)
{
  "success": true,
  "version": "1.0.0",
  "date_ist": "2025-10-31",
  "weekday": "FRIDAY",
  "cache_hit": false,
  "birthdays_today": ["Rohan"],
  "anniversaries_today": [{"names": ["Vedant","Aisha"], "year": 2020, "years": 5}],
  "content_type": "movies",
  "title": "🎬 Friday Watchlist (Hindi, Mumbai)",
  "message": "🎉 Birthdays today: Rohan\n\n💍 Anniversaries today: Vedant & Aisha (5 yrs)\n\n1. Movie A\n\n2. Movie B",
  "items": [
    {"title": "Movie A"},
    {"title": "Movie B"}
  ],
  "metadata": {"source": "in.bookmyshow.com"}
}

Sample riddle response (example)
{
  "success": true,
  "version": "1.0.0",
  "date_ist": "2025-10-30",
  "weekday": "THURSDAY",
  "cache_hit": false,
  "birthdays_today": ["Rohan"],
  "anniversaries_today": [{"names": ["Vedant","Aisha"], "year": 2020, "years": 5}],
  "content_type": "riddle",
  "title": "Riddle of the Day",
  "message": "🎉 Birthdays today: Rohan\n\n💍 Anniversaries today: Vedant & Aisha (5 yrs)\n\n🧩 Riddle\n\n🔢 I’m odd. Take away a letter and I become even. What number am I?",
  "items": [
    {"riddle":"🔢 I’m odd. Take away a letter and I become even. What number am I?", "answer":"Seven", "type":"text"}
  ],
  "metadata": {"serp_used": true}
}

Daily rules (IST)
- MONDAY: Motivational quote (non-cliché, meaningful, non-repeating)
- TUESDAY: Clean, funny joke (non-vulgar, non-repeating)
- WEDNESDAY: Positive news (last week, uplifting, 3 items)
- THURSDAY: Riddle (emoji or text), answer included in JSON only (not in message), non-repeating
- FRIDAY: Hindi movies (names only) from BookMyShow (Mumbai Hindi page)
- SATURDAY: Ask “one interesting thing that happened”; may include a small fun fact
- SUNDAY: Resting panda emoji/caption

Birthdays
- Stored in `list.txt` as: Name:DD/MM/YYYY or Name:DD/MM
- Example:
  Name:Birthday
  Vedant:23/10/1994
  Rohan:30/10
- The API adds “🎉 Birthdays today: …” to the top of the day’s message when applicable.

Anniversaries
- Stored in `anniversaries.txt` as: "Name1 & Name2:DD/MM/YYYY" or "Name1 & Name2:DD/MM"
- Supported separators between names: "&", "-", or " and "
- Example:
  Names:Anniversary
  Vedant & Aisha:23/10/2020
  Rohan and Neha:30/10
  Kabir - Meera:12/12/2015
- The API adds “💍 Anniversaries today: Name1 & Name2 (X yrs), …” above the daily message when applicable
- The JSON includes `anniversaries_today` as array of objects with keys: names [string,string], year (int|null), years (int|null)

Caching and non-repetition
- The first call received per IST day is cached in data/cache.json; subsequent calls that day return the cached payload.
- Non-repetition is enforced by day-of-week with normalized text history stored in data/history.json.
- Admin: GET /reset-cache (with token) to clear cache; GET /preview?day=MONDAY (with token) to test without writing cache.

Retries and fallbacks
- SerpAPI and Cohere calls are wrapped with exponential backoff retries.
- If generation fails, the API returns a valid error JSON (success: false) with error_code and error_message so Apple Shortcuts won’t post bad content to the group.

Security
- Optional bearer token or query param token via APP_TOKEN; recommended to keep your API private.
- Do not commit actual keys; set them as environment variables on PythonAnywhere.

Ideas and enhancements
- Add per-group personalization (tone, length, categories)
- Add images (with URL) for news/movies when available
- Auto-GIF/emoji variants for jokes/riddles
- Add admin endpoint to rotate/delete recent history to allow repeats after a while
- Track engagement by letting Shortcut send back reaction counts (if desired)

Troubleshooting
- If /daily returns success=false, check logs and environment keys
- Verify your keys are set in PythonAnywhere Web > Environment variables
- Rate limits: With free tiers, caching ensures only one generation/day; more calls are served from cache
- If Cohere SDK shape changes, pin version in requirements (already pinned to 4.x) or adjust `cohere_chat_text` accordingly

License
MIT
