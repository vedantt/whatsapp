#!/usr/bin/env python3
import os
import re
import json
import time
import logging
import random
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Callable
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from flask import Flask, jsonify, request

try:
    import cohere
except Exception:
    cohere = None

# -------- Configuration --------
APP_VERSION = "1.0.0"
IST = ZoneInfo("Asia/Kolkata")

BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

CACHE_FILE = DATA_DIR / "cache.json"
HISTORY_FILE = DATA_DIR / "history.json"
LIST_FILE = BASE_DIR / "list.txt"
ANNIVERSARIES_FILE = BASE_DIR / "anniversaries.txt"

# Keys: set in environment on PythonAnywhere
#   SERPAPI_API_KEY
#   COHERE_API_KEY
# Optional app token for basic auth:
#   APP_TOKEN

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# -------- Utilities --------
def now_ist() -> datetime:
    return datetime.now(IST)

def today_str_ist() -> str:
    return now_ist().strftime("%Y-%m-%d")

def weekday_ist_str() -> str:
    return now_ist().strftime("%A").upper()

def read_json_file(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"Failed to read JSON {path}: {e}")
    return default

def write_json_file(path: Path, obj: Any) -> None:
    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Failed to write JSON {path}: {e}")

def normalize_text(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower().strip())

def get_cache() -> Dict[str, Any]:
    return read_json_file(CACHE_FILE, default={})

def set_cache(date_key: str, payload: Dict[str, Any]) -> None:
    cache = get_cache()
    cache[date_key] = payload
    write_json_file(CACHE_FILE, cache)

def get_history() -> Dict[str, List[str]]:
    # history maps weekday -> list of normalized strings
    hist = read_json_file(HISTORY_FILE, default={})
    for day in ["MONDAY","TUESDAY","WEDNESDAY","THURSDAY","FRIDAY","SATURDAY","SUNDAY"]:
        hist.setdefault(day, [])
    return hist

def save_history(hist: Dict[str, List[str]]) -> None:
    # keep last 200 entries per day
    for k in hist:
        if isinstance(hist[k], list) and len(hist[k]) > 200:
            hist[k] = hist[k][-200:]
    write_json_file(HISTORY_FILE, hist)

def is_repeated(day: str, text: str) -> bool:
    norm = normalize_text(text)
    hist = get_history()
    return norm in set(hist.get(day, []))

def add_history(day: str, text: str) -> None:
    norm = normalize_text(text)
    hist = get_history()
    if norm not in hist.get(day, []):
        hist[day].append(norm)
        save_history(hist)

def parse_list_txt(path: Path) -> List[Tuple[str, Optional[int], Optional[int], Optional[int]]]:
    """
    Reads lines of form:
    Name:DD/MM/YYYY
    or
    Name:DD/MM (year omitted)
    Returns list of (name, day, month, year)
    """
    result = []
    if not path.exists():
        return result
    try:
        with path.open("r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.lower().startswith("name:birthday"):
                    continue
                if ":" not in line:
                    continue
                name, birthday = line.split(":", 1)
                name = name.strip()
                parts = birthday.strip().split("/")
                day = month = year = None
                if len(parts) >= 2:
                    try:
                        day = int(parts[0])
                        month = int(parts[1])
                    except Exception:
                        day = month = None
                    if len(parts) >= 3:
                        try:
                            year = int(parts[2])
                        except Exception:
                            year = None
                if name and day and month:
                    result.append((name, day, month, year))
    except Exception as e:
        logging.error(f"Error reading list.txt: {e}")
    return result

def birthdays_today_ist() -> List[str]:
    today = now_ist()
    d = today.day
    m = today.month
    matches = []
    for (name, day, month, year) in parse_list_txt(LIST_FILE):
        if day == d and month == m:
            matches.append(name)
    return matches

def parse_anniversaries_txt(path: Path) -> List[Tuple[str, str, Optional[int], Optional[int], Optional[int]]]:
    """
    Reads lines of form:
    Name1 & Name2:DD/MM/YYYY
    or
    Name1 & Name2:DD/MM (year omitted)
    Accepts separators between names: '&', '-', or ' and '
    Returns list of (name1, name2, day, month, year)
    """
    result = []
    if not path.exists():
        return result
    try:
        with path.open("r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.lower().startswith("names:anniversary"):
                    continue
                if ":" not in line:
                    continue
                left, datepart = line.split(":", 1)
                parts = re.split(r"\s*&\s*|\s*-\s*|\s+and\s+", left.strip(), maxsplit=1)
                if len(parts) < 2:
                    continue
                n1 = parts[0].strip()
                n2 = parts[1].strip()
                dmy = datepart.strip().split("/")
                day = month = year = None
                if len(dmy) >= 2:
                    try:
                        day = int(dmy[0]); month = int(dmy[1])
                    except Exception:
                        day = month = None
                    if len(dmy) >= 3:
                        try:
                            year = int(dmy[2])
                        except Exception:
                            year = None
                if n1 and n2 and day and month:
                    result.append((n1, n2, day, month, year))
    except Exception as e:
        logging.error(f"Error reading anniversaries.txt: {e}")
    return result

def anniversaries_today_ist() -> List[Dict[str, Any]]:
    today = now_ist()
    d = today.day
    m = today.month
    y = today.year
    matches: List[Dict[str, Any]] = []
    for (n1, n2, day, month, year) in parse_anniversaries_txt(ANNIVERSARIES_FILE):
        if day == d and month == m:
            years = None
            if year and year > 1900 and y >= year:
                years = y - year
            matches.append({"names": [n1, n2], "year": year, "years": years})
    return matches

# -------- Retry wrappers --------
def with_retries(fn: Callable, max_attempts=3, base_delay=0.8, jitter=0.4):
    def wrapper(*args, **kwargs):
        attempt = 0
        last_exc = None
        while attempt < max_attempts:
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                last_exc = e
                attempt += 1
                sleep_for = base_delay * (2 ** (attempt - 1)) + random.uniform(0, jitter)
                logging.warning(f"{fn.__name__} failed (attempt {attempt}/{max_attempts}): {e}; retrying in {sleep_for:.2f}s")
                time.sleep(sleep_for)
        raise last_exc
    return wrapper

# -------- SERPAPI helpers --------
def serp_api_key() -> Optional[str]:
    return os.environ.get("SERPAPI_API_KEY")

@with_retries
def serp_search(query: str, num: int = 10, tbm: Optional[str] = None, tbs: Optional[str] = None) -> List[Dict[str, Any]]:
    api_key = serp_api_key()
    if not api_key:
        raise RuntimeError("SERPAPI_API_KEY not set")
    params = {
        "engine": "google",
        "q": query,
        "api_key": api_key,
        "hl": "en",
        "gl": "in",
        "num": num
    }
    if tbm:
        params["tbm"] = tbm
    if tbs:
        params["tbs"] = tbs
    r = requests.get("https://serpapi.com/search.json", params=params, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"SERPAPI non-200: {r.status_code} {r.text[:180]}")
    data = r.json()
    results: List[Dict[str, Any]] = []
    # Prefer specialized containers if present
    containers = []
    if tbm == "nws":
        containers.append(data.get("news_results") or [])
    containers.append(data.get("organic_results") or [])
    for cont in containers:
        for item in cont:
            title = item.get("title") or ""
            link = item.get("link") or item.get("url") or ""
            snippet = item.get("snippet") or item.get("content") or ""
            if title and link:
                results.append({"title": title, "link": link, "snippet": snippet})
    # Deduplicate by link
    seen = set()
    uniq = []
    for it in results:
        if it["link"] not in seen:
            seen.add(it["link"])
            uniq.append(it)
    return uniq[:num]

# -------- Cohere helpers --------
def cohere_client() -> "cohere.Client":
    key = os.environ.get("COHERE_API_KEY")
    if not key:
        raise RuntimeError("COHERE_API_KEY not set")
    if not cohere:
        raise RuntimeError("cohere python package not installed")
    return cohere.Client(key)

def try_parse_json(text: str) -> Optional[Dict[str, Any]]:
    # Extract first JSON object in text
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end+1])
    except Exception:
        pass
    return None

@with_retries
def cohere_chat_text(prompt: str, temperature: float = 0.3) -> str:
    """Simple wrapper for Cohere chat; returns plain text."""
    client = cohere_client()
    # Use older stable API signature for compatibility on PythonAnywhere
    resp = client.chat(message=prompt, model="command-a-03-2025", temperature=temperature)
    # SDK returns an object with 'text'
    return getattr(resp, "text", None) or ""

@with_retries
def cohere_chat_json(prompt: str, temperature: float = 0.2) -> Dict[str, Any]:
    """Ask Cohere to return a compact JSON object. We'll attempt to parse."""
    text = cohere_chat_text(
        prompt + "\n\nReturn ONLY a minified JSON object. Do not include any extra commentary, markdown, or code fences.",
        temperature=temperature
    )
    obj = try_parse_json(text)
    if not obj:
        raise RuntimeError("Cohere did not return JSON")
    return obj

# -------- BookMyShow scraping helper --------
@with_retries
def fetch_bms_hindi_movies(url: str = "https://in.bookmyshow.com/explore/movies-mumbai?languages=hindi", max_items: int = 8) -> List[str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        "Accept-Language": "en-IN,en;q=0.9",
    }
    r = requests.get(url, headers=headers, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"BMS non-200: {r.status_code}")
    html = r.text
    titles: List[str] = []

    # Try JSON-like title fields embedded in the HTML
    for m in re.finditer(r'"title"\s*:\s*"([^"]+)"', html):
        t = m.group(1).strip()
        if not t or len(t) < 2:
            continue
        if t.lower().startswith("bookmyshow") or t.lower().startswith("explore"):
            continue
        titles.append(t)

    # Fallback to anchor text around movie URLs
    if len(titles) < 3:
        for m in re.finditer(r'href="[^"]*/movie/[^"]*".*?>([^<]{2,100})<', html, re.IGNORECASE | re.DOTALL):
            t = re.sub(r"\s+", " ", m.group(1)).strip()
            if t and t not in titles:
                titles.append(t)

    # Deduplicate preserving order
    seen = set()
    uniq = []
    for t in titles:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq[:max_items]

# -------- Content generators --------
def choose_non_repeating(day: str, gen_fn: Callable[[], Tuple[str, Dict[str, Any]]], attempts: int = 4) -> Tuple[str, Dict[str, Any]]:
    """
    gen_fn returns (primary_text_for_dedup, full_payload)
    We'll try a few times to avoid repeats using day history.
    """
    last_payload = None
    for _ in range(attempts):
        text, payload = gen_fn()
        last_payload = payload
        if not is_repeated(day, text):
            add_history(day, text)
            return text, payload
    # If all attempts are repeats, still return last payload (better than failing)
    add_history(day, normalize_text(last_payload.get("message") or text))
    return text, last_payload

def gen_monday_quote() -> Tuple[str, Dict[str, Any]]:
    # Use SERP to gather candidate motivational quotes context, then Cohere to pick/compose one with author.
    serp_results = []
    try:
        serp_results = serp_search('site:brainyquote.com OR site:goodreads.com "motivational quotes" -cliche', num=10, tbs="qdr:y")
    except Exception as e:
        logging.warning(f"SERP for quotes failed: {e}")

    snippets = "\n".join([f"- {r['title']}: {r.get('snippet','')}" for r in serp_results[:12]])
    prompt = f"""
You are crafting a non-cliche, meaningful motivational quote suitable for an Indian audience on a Monday. Use inspiration from the list below but do not copy verbatim.

Inspiration:
{snippets}

Return JSON with keys:
- quote (string, single punchy line, <190 chars)
- author (string, if unknown, set to "Unknown")
- source_hint (string, very short rationale)

Ensure it's uplifting, fresh, and not cringe.
"""
    data = cohere_chat_json(prompt)
    quote = str(data.get("quote", "")).strip().strip('"')
    author = str(data.get("author", "Unknown")).strip()
    primary_text = f"{quote} — {author}".strip()
    message = f"🚀 Monday Motivation\n\n“{quote}”\n— {author}"
    return primary_text, {
        "content_type": "quote",
        "title": "Monday Motivation",
        "message": message,
        "items": [{"quote": quote, "author": author}],
        "metadata": {"source_hint": data.get("source_hint", ""), "serp_used": len(serp_results) > 0}
    }

def gen_tuesday_joke() -> Tuple[str, Dict[str, Any]]:
    serp_results = []
    try:
        serp_results = serp_search("clean funny jokes India family friendly one liners -offensive -adult", num=10, tbs="qdr:y")
    except Exception as e:
        logging.warning(f"SERP for jokes failed: {e}")

    examples = "\n".join([f"- {r['title']}" for r in serp_results[:8]])
    prompt = f"""
Write one clean, genuinely funny, non-offensive joke for an Indian audience. Avoid repetition, politics, or vulgarity.
Style: short one-liner or Q/A.

Examples (do not copy):
{examples}

Return JSON: {{"joke": "string"}}
"""
    data = cohere_chat_json(prompt, temperature=0.6)
    joke = str(data.get("joke", "")).strip()
    primary_text = joke
    message = f"😂 Tuesday Joker\n\n{joke}"
    return primary_text, {
        "content_type": "joke",
        "title": "Tuesday Joke",
        "message": message,
        "items": [{"joke": joke}],
        "metadata": {"serp_used": len(serp_results) > 0}
    }

def gen_wednesday_news() -> Tuple[str, Dict[str, Any]]:
    # Positive news from last week
    serp_results = []
    try:
        serp_results = serp_search("positive good news India", num=10, tbm="nws", tbs="qdr:w")
    except Exception as e:
        logging.warning(f"SERP for news failed: {e}")

    listings = "\n".join([f"- {r['title']} — {r['link']}\n  {r.get('snippet','')}" for r in serp_results[:12]])
    prompt = f"""
From the following recent news (last week), pick the 3 most positive, uplifting, verifiable stories for Indian audience.
Provide short title and one-line positive summary. Avoid tragedies, politics, or controversy.

News candidates:
{listings}

Return JSON:
{{
  "section_title": "Start your day with positive news",
  "items": [
    {{"title":"", "summary":"", "link":""}},
    ...
  ]
}}
"""
    data = cohere_chat_json(prompt, temperature=0.2)
    items = data.get("items") or []
    # Fall back: synthesize from serp if model failed
    if not isinstance(items, list) or not items:
        items = []
        for r in serp_results[:3]:
            items.append({"title": r["title"], "summary": r.get("snippet", "")[:180], "link": r["link"]})
    section_title = data.get("section_title") or "Start your day with positive news"
    # Build message
    lines = [f"🗞️ {section_title}"]
    for i, it in enumerate(items, 1):
        lines.append(f"{i}. {it.get('title','')}\n   {it.get('summary','')}\n   {it.get('link','')}")
    message = "\n\n".join(lines)
    primary_text = " ".join([it.get("title", "") for it in items])
    return primary_text, {
        "content_type": "news",
        "title": section_title,
        "message": message,
        "items": items,
        "metadata": {"serp_used": True}
    }

def gen_friday_movies() -> Tuple[str, Dict[str, Any]]:
    # Fetch Hindi movies from BookMyShow Mumbai page and return ONLY movie names
    try:
        titles = fetch_bms_hindi_movies()
    except Exception as e:
        logging.warning(f"BMS scrape failed: {e}")
        titles = []

    title = "🎬 Friday Watchlist (Hindi, Mumbai)"
    if not titles:
        message = f"{title}\n\nNo fresh listings found on BookMyShow right now."
        return "no titles", {
            "content_type": "movies",
            "title": title,
            "message": message,
            "items": [],
            "metadata": {"source": "in.bookmyshow.com"}
        }

    lines = [title]
    for i, t in enumerate(titles, 1):
        lines.append(f"{i}. {t}")
    message = "\n\n".join(lines)
    primary_text = " ".join(titles)
    return primary_text, {
        "content_type": "movies",
        "title": title,
        "message": message,
        "items": [{"title": t} for t in titles],
        "metadata": {"source": "in.bookmyshow.com"}
    }


def gen_friday_riddle() -> Tuple[str, Dict[str, Any]]:
    serp_results = []
    try:
        serp_results = serp_search("emoji riddles India family friendly", num=8, tbs="qdr:y")
    except Exception as e:
        logging.warning(f"SERP for riddles failed: {e}")

    prompt = f"""
Create one great riddle for an Indian audience. Prefer emoji-style if possible, else a clever text riddle. Difficulty: medium. Return also the answer.

Constraints:
- Family friendly
- Non-repeating
- Fun to share

Return JSON:
{{"riddle":"", "answer":"", "type":"emoji|text"}}
"""
    data = cohere_chat_json(prompt, temperature=0.7)
    riddle = str(data.get("riddle", "")).strip()
    answer = str(data.get("answer", "")).strip()
    rtype = str(data.get("type", "text")).strip()
    primary_text = riddle
    message = f"🧩 Riddle\n\n{riddle}"
    return primary_text, {
        "content_type": "riddle",
        "title": "Riddle of the Day",
        "message": message,
        "items": [{"riddle": riddle, "answer": answer, "type": rtype}],
        "metadata": {"serp_used": len(serp_results) > 0}
    }

def gen_saturday_prompt() -> Tuple[str, Dict[str, Any]]:
    # Ask 1 interesting thing that happened. Add a tiny icebreaker fact sourced lightly via SERP for variety.
    serp_results = []
    fact_line = ""
    try:
        serp_results = serp_search("uplifting facts India interesting", num=6, tbs="qdr:w")
        if serp_results:
            top = serp_results[0]
            fact_line = f"Fun fact: {top['title']}"
    except Exception as e:
        logging.warning(f"SERP for saturday prompt failed: {e}")
    prompt_text = "✨ Saturday Check-in\n\nShare 1 interesting thing that happened this week! " + (fact_line if fact_line else "")
    primary_text = prompt_text
    return primary_text, {
        "content_type": "prompt",
        "title": "Saturday Check-in",
        "message": prompt_text,
        "items": [],
        "metadata": {"serp_used": len(serp_results) > 0}
    }

def gen_sunday_panda() -> Tuple[str, Dict[str, Any]]:
    # Resting panda word/emoji
    prompt = """
Create a cute resting panda line with emoji/kaomoji to encourage rest. Keep it under 100 characters.
Return JSON: {"emoji":"", "caption":""}
"""
    data = cohere_chat_json(prompt, temperature=0.5)
    emoji = data.get("emoji") or "🐼💤"
    caption = data.get("caption") or "Rest day! Recharge and take it easy."
    primary_text = f"{emoji} {caption}"
    message = f"{emoji} {caption}"
    return primary_text, {
        "content_type": "emoji",
        "title": "Sunday Rest",
        "message": message,
        "items": [{"emoji": emoji, "caption": caption}],
        "metadata": {"serp_used": False}
    }

def generate_for_day(day: str) -> Dict[str, Any]:
    # Map weekday to generators
    day = day.upper()
    generators: Dict[str, Callable[[], Tuple[str, Dict[str, Any]]]] = {
        "MONDAY": lambda: choose_non_repeating("MONDAY", gen_monday_quote),
        "TUESDAY": lambda: choose_non_repeating("TUESDAY", gen_tuesday_joke),
        "WEDNESDAY": lambda: choose_non_repeating("WEDNESDAY", gen_wednesday_news),
        "THURSDAY": lambda: choose_non_repeating("THURSDAY", gen_friday_riddle),
        "FRIDAY": lambda: choose_non_repeating("FRIDAY", gen_friday_movies),
        "SATURDAY": lambda: choose_non_repeating("SATURDAY", gen_saturday_prompt),
        "SUNDAY": lambda: choose_non_repeating("SUNDAY", gen_sunday_panda),
    }
    if day not in generators:
        raise ValueError(f"Unsupported weekday: {day}")
    _text, payload = generators[day]()
    return payload

# -------- Flask app --------
app = Flask(__name__)

def check_token() -> Optional[str]:
    expected = os.environ.get("APP_TOKEN")
    if not expected:
        return None
    token = request.args.get("token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
    if token != expected:
        return "unauthorized"
    return None

def build_success_response(payload: Dict[str, Any], cache_hit: bool, birthdays: List[str], anniversaries: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "success": True,
        "version": APP_VERSION,
        "date_ist": today_str_ist(),
        "weekday": weekday_ist_str(),
        "cache_hit": cache_hit,
        "birthdays_today": birthdays,
        "anniversaries_today": anniversaries,
        "content_type": payload.get("content_type"),
        "title": payload.get("title"),
        "message": payload.get("message"),
        "items": payload.get("items", []),
        "metadata": payload.get("metadata", {})
    }

def build_error_response(code: str, message: str) -> Dict[str, Any]:
    return {
        "success": False,
        "version": APP_VERSION,
        "date_ist": today_str_ist(),
        "weekday": weekday_ist_str(),
        "error_code": code,
        "error_message": message
    }

@app.get("/health")
def health():
    return jsonify({"ok": True, "version": APP_VERSION})

@app.get("/daily")
def daily():
    # Optional token check
    auth_err = check_token()
    if auth_err:
        return jsonify(build_error_response("AUTH", "Unauthorized")), 200

    # Serve cached payload if exists
    cache = get_cache()
    today = today_str_ist()
    birthdays = birthdays_today_ist()
    anniversaries = anniversaries_today_ist()

    if today in cache:
        payload = cache[today]
        # Always attach latest birthdays (not stored in cache to avoid staleness if list.txt changes midday)
        payload["birthdays_today"] = birthdays
        # Always attach latest anniversaries too
        payload["anniversaries_today"] = anniversaries
        # Mark as cache hit for client visibility
        payload["cache_hit"] = True
        return jsonify(payload), 200

    # Generate fresh
    try:
        day = weekday_ist_str()
        generated = generate_for_day(day)
        # Prepend birthdays/anniversaries to message if any
        header_lines: List[str] = []
        if birthdays:
            bmsg = "🎉 Birthdays today: " + ", ".join(birthdays)
            header_lines.append(bmsg)
        if anniversaries:
            pairs = []
            for a in anniversaries:
                names = " & ".join(a.get("names", []))
                yrs = a.get("years")
                if yrs:
                    names += f" ({yrs} yrs)"
                pairs.append(names)
            amsg = "💍 Anniversaries today: " + ", ".join(pairs)
            header_lines.append(amsg)
        if header_lines:
            base_msg = generated.get("message", "")
            generated["message"] = f"{'\n'.join(header_lines)}\n\n{base_msg}"
        final = build_success_response(generated, cache_hit=False, birthdays=birthdays, anniversaries=anniversaries)
        # Cache for rest of the day
        set_cache(today, final)
        return jsonify(final), 200
    except Exception as e:
        logging.exception("Failed to generate daily content")
        # Robust fallback to ensure Shortcuts gets a valid JSON
        fallback = build_error_response("GENERATION_FAILED", str(e)[:300])
        return jsonify(fallback), 200

# -------- Utility admin/test endpoints (token required for mutating ops) --------
@app.get("/version")
def version():
    return jsonify({
        "ok": True,
        "version": APP_VERSION,
        "date_ist": today_str_ist(),
        "weekday": weekday_ist_str()
    }), 200

@app.get("/schema")
def schema():
    # Minimal schema description for Apple Shortcuts reference
    return jsonify({
        "success": "boolean",
        "version": "string",
        "date_ist": "YYYY-MM-DD (IST)",
        "weekday": "MONDAY..SUNDAY",
        "cache_hit": "boolean",
        "birthdays_today": ["string"],
        "anniversaries_today": [{"names": ["Name1","Name2"], "year": 2015, "years": 9}],
        "content_type": "quote|joke|news|movies|riddle|prompt|emoji",
        "title": "string",
        "message": "string",
        "items": "array (structure varies by content_type)",
        "metadata": "object",
        "error_code": "string (present only if success=false)",
        "error_message": "string (present only if success=false)"
    }), 200

@app.get("/preview")
def preview():
    # Preview generation for a specified day without caching (requires token)
    auth_err = check_token()
    if auth_err:
        return jsonify(build_error_response("AUTH", "Unauthorized")), 200

    day = (request.args.get("day") or weekday_ist_str()).upper().strip()
    try:
        generated = generate_for_day(day)
        # Mark as preview
        meta = generated.get("metadata", {}) or {}
        meta["preview"] = True
        generated["metadata"] = meta
        # Add birthdays/anniversaries context (from real today)
        bdays = birthdays_today_ist()
        anivs = anniversaries_today_ist()
        header_lines: List[str] = []
        if bdays:
            bmsg = "🎉 Birthdays today: " + ", ".join(bdays)
            header_lines.append(bmsg)
        if anivs:
            pairs = []
            for a in anivs:
                names = " & ".join(a.get("names", []))
                yrs = a.get("years")
                if yrs:
                    names += f" ({yrs} yrs)"
                pairs.append(names)
            amsg = "💍 Anniversaries today: " + ", ".join(pairs)
            header_lines.append(amsg)
        if header_lines:
            base_msg = generated.get("message","")
            generated["message"] = f"{'\n'.join(header_lines)}\n\n{base_msg}"
        final = build_success_response(generated, cache_hit=False, birthdays=bdays, anniversaries=anivs)
        return jsonify(final), 200
    except Exception as e:
        logging.exception("Preview generation failed")
        return jsonify(build_error_response("PREVIEW_FAILED", str(e)[:300])), 200

@app.get("/reset-cache")
def reset_cache():
    # Clear the daily cache (requires token)
    auth_err = check_token()
    if auth_err:
        return jsonify(build_error_response("AUTH", "Unauthorized")), 200
    try:
        write_json_file(CACHE_FILE, {})
        return jsonify({"ok": True, "cleared": True, "date_ist": today_str_ist()}), 200
    except Exception as e:
        return jsonify(build_error_response("RESET_FAILED", str(e)[:300])), 200

# -------- CLI entry --------
if __name__ == "__main__":
    # Local run: FLASK_ENV=development python app.py
    port = int(os.environ.get("PORT", "5051"))
    app.run(host="0.0.0.0", port=port)
