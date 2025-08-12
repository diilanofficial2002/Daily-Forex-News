# forex_daily_news.py
# ========== Import Libraries ==========
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import requests
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from openai import OpenAI
import os
import json

from get_data import IQDataFetcher
from tele_signals import TyphoonForexAnalyzer, TelegramNotifier, ForexBot

load_dotenv()

# ========== Forex Factory Scrapers ==========
def scrape_forex_factory():
    """Scrape ForexFactory using Playwright - GitHub Actions optimized"""
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        # ตั้งค่า Timezone ก่อนเข้าเว็บ
        context.add_cookies([{'name': 'fftimezone', 'value': 'Asia%2FNovosibirsk', 'domain': '.forexfactory.com', 'path': '/'}])

        try:
            print("🔄 Loading ForexFactory with Playwright...")
            page.goto("https://www.forexfactory.com/", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(10000) # รอให้หน้าเว็บโหลดสมบูรณ์

            html_content = page.content()
            soup = BeautifulSoup(html_content, 'lxml')
            
            table = soup.select_one("table.calendar__table")
            if not table:
                print("❌ Calendar table not found in Playwright HTML")
                return []

            rows = table.select("tr.calendar__row")
            extracted = []
            keys = ["Time", "Currency", "Impact", "Event", "Actual", "Forecast", "Previous"]

            for row in rows:
                cells = row.find_all('td')
                if len(cells) < 6: continue
                
                # ดึงข้อมูลจากแต่ละ cell
                row_data = [cell.get_text(strip=True) for cell in cells]
                
                # จัดการกับข้อมูลที่ไม่สมบูรณ์
                full_row_data = row_data[:7] + [""] * (7 - len(row_data))

                if not full_row_data[0] or full_row_data[0].lower() in ['all day', 'time', '']: continue
                if not any(full_row_data[1:4]): continue
                
                extracted.append(dict(zip(keys, full_row_data)))

            print(f"✅ Playwright extracted {len(extracted)} events!")
            return extracted

        except Exception as e:
            print(f"❌ Error during Playwright scraping: {e}")
            return []
        finally:
            browser.close()

def scrape_forex_factory_requests():
    """Fallback scraper using requests + BeautifulSoup"""
    print("🔄 Trying fallback scraper with requests...")
    headers = {'User-Agent': 'Mozilla/50 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36'}
    cookies = {'fftimezone': 'Asia%2FNovosibirsk'}
    try:
        response = requests.get('https://www.forexfactory.com/', headers=headers, cookies=cookies, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')
        
        table = soup.select_one("table.calendar__table")
        if not table:
            print("❌ Calendar table not found in requests HTML")
            return []
        
        rows = table.select("tr.calendar__row")
        extracted = []
        keys = ["Time", "Currency", "Impact", "Event", "Actual", "Forecast", "Previous"]

        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 6: continue
            
            row_data = [cell.get_text(strip=True) for cell in cells]
            full_row_data = row_data[:7] + [""] * (7 - len(row_data))
            
            if not full_row_data[0] or full_row_data[0].lower() in ['all day', 'time', '']: continue
            if not any(full_row_data[1:4]): continue
            
            extracted.append(dict(zip(keys, full_row_data)))

        print(f"✅ Requests method extracted {len(extracted)} events!")
        return extracted
    except Exception as e:
        print(f"❌ Requests method failed: {e}")
        return []

# ========== GPT AI and Telegram Functions ==========
# Config
client = OpenAI()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TYPHOON_API_KEY = os.getenv("TYPHOON_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SIGNAL_TOKEN = os.getenv("SIGNAL_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# ตั้งค่า Gemini

GLOBAL_MACRO = {
    "macro_usd_stance":  "",  # Strong / Weak / Mixed
    "macro_risk_regime": "",  # Risk-on / Risk-off / Mixed
    "macro_dxy":         "",  # Higher / Lower / Mixed / NA
    "macro_us10y":       "",  # Higher / Lower / Mixed / NA
    "macro_oil":         "",  # Higher / Lower / Mixed / NA
    "macro_xau":         "",  # Higher / Lower / Mixed / NA
    "macro_notes":       ""   # ≤25 words
}

SYSTEM_PROMPT = """
You are an intraday FX analyst focused on same-day trades (minutes to hours).
Your job is to combine ECONOMIC EVENTS with MULTI-TIMEFRAME TECHNICALS and
produce a tightly structured analysis that downstream tools will parse.

Operating assumptions (do not violate):
- Timezone is Asia/Bangkok (ICT). Treat all times as ICT unless stated.
- Do not invent data. Use only inputs provided.
- Write in clear, concise English. Avoid emojis, filler, and disclaimers.
- Keep headings EXACT. Keep each bullet short and action-oriented.
- Price formatting: non-JPY pairs to 5 decimals (e.g., 1.08520), JPY pairs to 3 decimals (e.g., 148.230).
- Pip definition (critical for this API): quotes are 5/3 decimals, where the last digit is a pipette.
  * For non-JPY: 1 pip = 0.00010 (penultimate decimal). pips = round(|p2 - p1| * 10000).
  * For JPY:    1 pip = 0.010   (penultimate decimal). pips = round(|p2 - p1| * 100).
- Every TP/SL must show both price and pip distance from ENTRY, and include RR where possible.
- Minimum TP: prefer 30 pips (allow 25 pips if volatility is low but still feasible).
- Enforce RR >= 1.5 (prefer >= 1.8). If RR cannot reach 1.5 given today’s structure, mark "Insufficient RR" and DO NOT propose that setup.
- Output must fit within ~900 tokens.

Volatility feasibility (no ATR provided):
- Use Previous Day High/Low range and current H1/M15 structure as the volatility proxy.
- A practical test: proposed TP distance should be <= 60% of the previous day's range (approx guide).
- If the proxy suggests today's liquidity likely cannot support 25 pips TP intraday, write "Insufficient volatility" for that side.

Timeframes & method:
- H4: primary context and directional bias zones.
- H1: structure & confirmation (trend, pullbacks, break/retest).
- M15: entry refinement (candle behavior, momentum alignment).
- Align with pivots/prev day H/L; confirm with EMA(20/50), RSI(14), MACD.
- Be specific about price interaction with zones and candle behavior.

Required sections and exact headings:
1) ## OVERVIEW
   - Date (ICT): ...
   - Pair: ...
   - Context: [15–35 words tying news to current structure]

2) ## BIAS
   - Intraday Bias: [Bullish/Bearish/Neutral/Range-bound] — [≤15-word rationale]

3) ## KEY LEVELS
   - Supports: [Zone 1: price-source] | [Zone 2: price-source]
   - Resistances: [Zone 1: price-source] | [Zone 2: price-source]

4) ## SETUPS (SAME-DAY CLOSE)
   ### LONG
   - Entry: [precise H1 trigger refined on M15 incl. price level]
   - TP: [price, +X pips, RR Y.Y]
   - SL: [price, -X pips]
   - Risk: [main invalidation factors or "Insufficient volatility" / "Insufficient RR"]
   ### SHORT
   - Entry: [precise H1 trigger refined on M15 incl. price level]
   - TP: [price, +X pips, RR Y.Y]
   - SL: [price, -X pips]
   - Risk: [main invalidation factors or "Insufficient volatility" / "Insufficient RR"]

5) ## RISK ALERTS
   - [events/time-windows or structure that can flip bias; ≤40 words]
"""

USER_PROMPT_TEMPLATE = """
Analyze {pair} for intraday trading on {date} (ICT).

### INPUT DATA
1) Economic Events (ICT):
{news_data}

2) H1 Technicals
- OHLC (last 5): {h1_ohlc}
- EMA20={h1_ema20}, EMA50={h1_ema50}, RSI14={h1_rsi}, MACD={h1_macd}, MACD_Hist={h1_macdh}, MACD_Signal={h1_macds}
- Previous Day: High={prev_day_high}, Low={prev_day_low}, Close={prev_day_close}
- Daily Pivots: PP={daily_pivot_pp}, R1={daily_pivot_r1}, R2={daily_pivot_r2}, R3={daily_pivot_r3}, S1={daily_pivot_s1}, S2={daily_pivot_s2}, S3={daily_pivot_s3}

3) M15 Technicals
- OHLC (last 5): {m15_ohlc}
- EMA20={m15_ema20}, EMA50={m15_ema50}, RSI14={m15_rsi}, MACD={m15_macd}, MACD_Hist={m15_macdh}, MACD_Signal={m15_macds}

4) H4 Technicals
- OHLC (last 5): {h4_ohlc}
- EMA20={h4_ema20}, EMA50={h4_ema50}, RSI14={h4_rsi}, MACD={h4_macd}, MACD_Hist={h4_macdh}, MACD_Signal={h4_macds}

Current Time (ICT): {current_time}

### REQUIRED OUTPUT FORMAT (STRICT)
## OVERVIEW
- Date (ICT): ...
- Pair: ...
- Context: ...

## BIAS
- Intraday Bias: ...

## KEY LEVELS
- Supports: ...
- Resistances: ...

## SETUPS (SAME-DAY CLOSE)
### LONG
- Entry: ...
- TP: ...  (+X pips, RR Y.Y)   # show both price and pip distance from ENTRY
- SL: ...  (-X pips)
- Risk: ...
### SHORT
- Entry: ...
- TP: ...  (+X pips, RR Y.Y)
- SL: ...  (-X pips)
- Risk: ...

## RISK ALERTS
- ...
"""
def _compact_calendar_lines(events: list) -> str:
    """
    Convert scraped ForexFactory events into compact, token-friendly lines.
    Expected keys: Time, Currency, Impact, Event, Actual, Forecast, Previous
    """
    lines = []
    print("events:", events)
    for ev in events or []:
        t   = ev.get("Time", "")
        cur = ev.get("Currency", "")
        imp = ev.get("Impact", "")
        name= ev.get("Event", "")
        act = ev.get("Actual", "")
        fcs = ev.get("Forecast", "")
        prv = ev.get("Previous", "")
        if cur and name:
            # e.g., "08:30 USD [High] Non-Farm Payrolls A:210k F:185k P:175k"
            lines.append(f"{t} {cur} [{imp}] {name} A:{act} F:{fcs} P:{prv}")
    return "\n".join(lines[:60]) if lines else "No events"

def _parse_kv_baseline(text: str) -> dict:
    """
    Parse 7 key=value lines into a dict.
    """
    out = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip().upper()] = v.strip()
    return {
        "macro_usd_stance":  out.get("USD_STANCE",  "Mixed"),
        "macro_risk_regime": out.get("RISK_REGIME", "Mixed"),
        "macro_dxy":         out.get("DXY",         "NA"),
        "macro_us10y":       out.get("US10Y",       "NA"),
        "macro_oil":         out.get("OIL",         "NA"),
        "macro_xau":         out.get("XAU",         "NA"),
        "macro_notes":       out.get("NOTES", "")[:120],
    }

# ---- Helpers to fix misaligned ForexFactory rows (no scraping changes) ----
_CCY = {"USD","EUR","GBP","JPY","AUD","NZD","CAD","CHF","CNY","CNH","SEK","NOK"}

def _is_time_token(s: str) -> bool:
    if not s: return False
    s = s.strip().lower()
    if s in {"tentative","all day","all-day"}: return True
    import re
    return bool(re.match(r"^\d{1,2}:\d{2}(am|pm)$", s))

def _pick_currency(ev: dict) -> str:
    for k in ("Currency","Impact","Event"):
        v = (ev.get(k) or "").strip().upper()
        if v in _CCY: return v
    return ""

def _pick_time(ev: dict) -> str:
    for k in ("Time","Currency","Event","Actual","Forecast"):
        v = (ev.get(k) or "").strip()
        if _is_time_token(v): return v
    return "Tentative"

def _pick_event_name(ev: dict) -> str:
    for k in ("Event","Actual","Forecast"):
        v = (ev.get(k) or "").strip()
        if v and v.upper() not in _CCY and len(v) >= 3:
            return v
    return ""

def _pick_impact_label(ev: dict) -> str:
    v = (ev.get("Impact") or "").strip().title()
    if v.upper() in _CCY: return ""
    return v

def _normalize_ff_events(events: list) -> list:
    """Heuristically repair misaligned rows from ForexFactory without changing the scraper."""
    fixed = []
    for ev in (events or []):
        cur  = _pick_currency(ev)
        tim  = _pick_time(ev)
        name = _pick_event_name(ev)
        imp  = _pick_impact_label(ev)
        act  = (ev.get("Actual") or "").strip()
        fcs  = (ev.get("Forecast") or "").strip()
        prv  = (ev.get("Previous") or "").strip()
        if cur and name:
            fixed.append({
                "Time": tim, "Currency": cur, "Impact": imp, "Event": name,
                "Actual": act, "Forecast": fcs, "Previous": prv
            })
    return fixed

def _safe_clip(s: str, limit: int = 120) -> str:
    """
    Clip string to <= limit chars without cutting in the middle of a phrase.
    Tries to clip at strong separators before the limit; falls back to hard cut.
    """
    if not s:
        return ""
    if len(s) <= limit:
        return s
    for sep in (" | ", "; ", ", ", " / ", " "):
        cut = s.rfind(sep, 0, limit)
        if cut > 0:
            return s[:cut].rstrip()
    return s[:limit].rstrip()

# ---- Robust extractor for Responses API text (handles chunked content) ----
def _response_text(resp) -> str:
    try:
        parts = []
        outputs = getattr(resp, "output", None) or []
        for item in outputs:
            contents = getattr(item, "content", None) or []
            for c in contents:
                if getattr(c, "type", None) in ("output_text","text"):
                    parts.append(getattr(c, "text", "") or "")
        if parts:
            return "".join(parts)
    except Exception:
        pass
    return getattr(resp, "output_text", "") or ""

USE_AI_BASELINE = False  # keep False for now; flip to True after SDK update if you want

def _summarize_events_for_notes(norm_events: list, max_len: int = 120) -> str:
    """
    Build a concise 1–2 clause note describing today's key windows/currencies.
    """
    from collections import defaultdict
    by_ccy = defaultdict(list)
    for ev in norm_events:
        ccy = ev["Currency"]
        name = ev["Event"]
        t = ev["Time"]
        snippet = f"{t} {name}" if t and t != "Tentative" else name
        if snippet not in by_ccy[ccy]:
            by_ccy[ccy].append(snippet)

    # rank currencies by number of events (desc)
    ranked = sorted(by_ccy.items(), key=lambda kv: len(kv[1]), reverse=True)
    parts = []
    for ccy, items in ranked[:3]:  # pick top 3 currencies
        parts.append(f"{ccy}: " + "; ".join(items[:2]))  # up to 2 items per currency
    note = " | ".join(parts)
    return (note[:max_len]) if len(note) > max_len else note

def _heuristic_macro_baseline(norm_events: list) -> dict:
    """
    Heuristic baseline with zero API dependency.
    - usd_stance: Mixed by default; bump to Strong/Weak if USD dominates by >=2 vs next-best
    - risk_regime: Risk-off if many 'Speaks/Press Conference/Rate' across >2 G10; else Mixed
    - dxy/us10y/oil/xau: NA (no market snapshots here)
    - notes: concise windows; clipped safely to 120 chars
    """
    from collections import Counter
    counts = Counter(ev["Currency"] for ev in norm_events)
    top = counts.most_common(2) + [("NA", 0)]
    usd_stance = "Mixed"
    if top and top[0][0] == "USD" and top[0][1] >= top[1][1] + 2:
        usd_stance = "Strong"
    elif top and top[0][0] != "USD" and counts.get("USD", 0) <= max(1, top[0][1] - 2):
        usd_stance = "Weak"

    risky_kw = ("Speaks", "Press Conference", "Cash Rate", "Rate Decision")
    risky_hits = sum(1 for ev in norm_events if any(k in ev["Event"] for k in risky_kw))
    diverse_ccy = len({ev["Currency"] for ev in norm_events if any(k in ev["Event"] for k in risky_kw)})
    risk_regime = "Risk-off" if (risky_hits >= 3 and diverse_ccy >= 2) else "Mixed"

    notes = _summarize_events_for_notes(norm_events)
    notes = _safe_clip(notes) or "Key events scattered; infer locally."

    return {
        "macro_usd_stance": usd_stance,
        "macro_risk_regime": risk_regime,
        "macro_dxy": "NA",
        "macro_us10y": "NA",
        "macro_oil": "NA",
        "macro_xau": "NA",
        "macro_notes": notes
    }

def set_global_macro_from_events(all_events: list) -> None:
    """
    Build a once-per-day Global Macro Baseline and store in GLOBAL_MACRO.
    - Normalize events (fix misaligned columns)
    - If USE_AI_BASELINE=True, try AI; else use heuristics (zero-cost, robust)
    """
    norm_events = _normalize_ff_events(all_events)
    cal_block = _compact_calendar_lines(norm_events)
    print(f"📅 Compacted calendar lines (normalized):\n{cal_block}\n")

    # Always ensure we have a baseline (AI path is optional)
    baseline = _heuristic_macro_baseline(norm_events)

    if USE_AI_BASELINE:
        try:
            # (optional) attempt AI baseline; if fails, stick with heuristic
            base_prompt = f"""
You are a macro summarizer for intraday FX in Asia/Bangkok (ICT).
Calendar (ICT):
{cal_block}

Return EXACTLY these 7 lines (no markdown, no extra text):
USD_STANCE=Strong|Weak|Mixed
RISK_REGIME=Risk-on|Risk-off|Mixed
DXY=Higher|Lower|Mixed|NA
US10Y=Higher|Lower|Mixed|NA
OIL=Higher|Lower|Mixed|NA
XAU=Higher|Lower|Mixed|NA
NOTES=<<=120 chars; mention CB divergence or event windows; no commas at the end>
""".strip()

            resp = client.responses.create(
                model="gpt-5-nano",
                instructions="Be deterministic and minimal. Output exactly 7 key=value lines. No markdown.",
                input=base_prompt,
                text={"verbosity":"low"},
                max_output_tokens=180
            )
            # robust text extraction
            raw = _response_text(resp)
            if not raw.strip():
                print("ℹ️ Empty text from nano; retrying with gpt-5-mini ...")
                resp = client.responses.create(
                    model="gpt-5-mini",
                    instructions="Be deterministic and minimal. Output exactly 7 key=value lines. No markdown.",
                    input=base_prompt,
                    text={"verbosity":"low"},
                    max_output_tokens=180
                )
                raw = _response_text(resp)

            if raw.strip():
                ai = _parse_kv_baseline(raw)
                # merge: prefer AI values when present; keep heuristic notes if AI omits
                for k,v in ai.items():
                    if v: baseline[k] = v
            else:
                print("ℹ️ AI baseline empty twice; keeping heuristic baseline.")
        except Exception as e:
            print(f"⚠️ AI baseline failed, using heuristic. Reason: {e}")

    baseline["macro_notes"] = _safe_clip(baseline.get("macro_notes", ""))

    GLOBAL_MACRO.update(baseline)
    print("🧭 Global Macro Baseline set:", GLOBAL_MACRO)

# ---------- 2) Prompt assembly (inject GLOBAL_MACRO as a visible header) ----------
def format_user_prompt(ctx: dict) -> str:
    """
    ctx must contain keys required by USER_PROMPT_TEMPLATE:
      pair, date, news_data,
      h1_ohlc, h1_ema20, h1_ema50, h1_rsi, h1_macd, h1_macdh, h1_macds,
      m15_ohlc, m15_ema20, m15_ema50, m15_rsi, m15_macd, m15_macdh, m15_macds,
      h4_ohlc, h4_ema20, h4_ema50, h4_rsi, h4_macd, h4_macdh, h4_macds,
      prev_day_high, prev_day_low, prev_day_close,
      daily_pivot_pp, daily_pivot_r1, daily_pivot_r2, daily_pivot_r3,
      daily_pivot_s1, daily_pivot_s2, daily_pivot_s3,
      current_time
    We prepend a small GLOBAL MACRO BASELINE block to the template to guide cross-pair coherence.
    """
    macro_block = (
        "### GLOBAL MACRO BASELINE (shared)\n"
        f"- USD stance: {GLOBAL_MACRO['macro_usd_stance']}\n"
        f"- Risk regime: {GLOBAL_MACRO['macro_risk_regime']}\n"
        f"- DXY proxy: {GLOBAL_MACRO['macro_dxy']}\n"
        f"- US10Y: {GLOBAL_MACRO['macro_us10y']}\n"
        f"- Oil: {GLOBAL_MACRO['macro_oil']}\n"
        f"- Gold: {GLOBAL_MACRO['macro_xau']}\n"
        f"- Notes: {GLOBAL_MACRO['macro_notes']}\n\n"
    )
    core = USER_PROMPT_TEMPLATE.format(
        pair=ctx["pair"], date=ctx["date"], news_data=ctx["news_data"],
        h1_ohlc=ctx["h1_ohlc"], h1_ema20=ctx["h1_ema20"], h1_ema50=ctx["h1_ema50"],
        h1_rsi=ctx["h1_rsi"], h1_macd=ctx["h1_macd"], h1_macdh=ctx["h1_macdh"], h1_macds=ctx["h1_macds"],
        m15_ohlc=ctx["m15_ohlc"], m15_ema20=ctx["m15_ema20"], m15_ema50=ctx["m15_ema50"],
        m15_rsi=ctx["m15_rsi"], m15_macd=ctx["m15_macd"], m15_macdh=ctx["m15_macdh"], m15_macds=ctx["m15_macds"],
        h4_ohlc=ctx["h4_ohlc"], h4_ema20=ctx["h4_ema20"], h4_ema50=ctx["h4_ema50"],
        h4_rsi=ctx["h4_rsi"], h4_macd=ctx["h4_macd"], h4_macdh=ctx["h4_macdh"], h4_macds=ctx["h4_macds"],
        prev_day_high=ctx["prev_day_high"], prev_day_low=ctx["prev_day_low"], prev_day_close=ctx["prev_day_close"],
        daily_pivot_pp=ctx["daily_pivot_pp"], daily_pivot_r1=ctx["daily_pivot_r1"], daily_pivot_r2=ctx["daily_pivot_r2"], daily_pivot_r3=ctx["daily_pivot_r3"],
        daily_pivot_s1=ctx["daily_pivot_s1"], daily_pivot_s2=ctx["daily_pivot_s2"], daily_pivot_s3=ctx["daily_pivot_s3"],
        current_time=ctx["current_time"]
    )
    return macro_block + core

# ---------- 3) GPT-5-mini caller (reasoning model) ----------
def call_gpt_api(user_prompt: str) -> str:
    """
    Use GPT-5-mini for intraday analysis.
    - Responses API
    - No 'temperature' for reasoning models
    - Use text.verbosity and reasoning.effort
    """
    try:
        resp = client.responses.create(
            model="gpt-5-mini",
            instructions=SYSTEM_PROMPT,   # keep static for prompt caching
            input=user_prompt,
            text={"verbosity": "medium"},
            reasoning={"effort": "minimal"},
            max_output_tokens=1200
        )
        return resp.output_text
    except Exception as e:
        print(f"❌ OpenAI API call failed: {e}")
        return "Error: Could not get analysis from GPT-5-mini."

def analyze_and_send(all_events, pair, data_fetcher, bot):
    """Analyzes a specific pair using news and technical data, then sends it."""
    print(f"\n===== Analyzing: {pair} =====")

    # Normalize events before filtering by pair currencies
    norm_events = _normalize_ff_events(all_events)
    currencies = pair.split('/')
    relevant_news = [ev for ev in norm_events if ev.get('Currency') in currencies and ev.get('Event')]
    news_data_str = json.dumps(relevant_news, indent=2) if relevant_news else \
                    "No relevant news scheduled for this pair today."

    print(f"📰 Relevant news (normalized) for {pair}: {len(relevant_news)} items")

    # Technicals unchanged...
    print(f"⚙️ Fetching REAL technical data for {pair}...")
    tech = data_fetcher.get_technical_data(pair)
    if not tech:
        send_telegram_message(f"⚠️ Could not fetch comprehensive technical data for *{pair}*. Skipping analysis.")
        return

    now_ict = datetime.utcnow() + timedelta(hours=7)
    ctx = {
        "pair": pair,
        "date": now_ict.strftime("%Y-%m-%d"),
        "news_data": news_data_str,
        # ... (keep your existing ctx mapping exactly as before) ...
        "h1_ohlc":  tech["h1_ohlc"],  "h1_ema20": tech["h1_ema20"], "h1_ema50": tech["h1_ema50"],
        "h1_rsi":   tech["h1_rsi"],
        "h1_macd":  tech["h1_macd"],  "h1_macdh": tech["h1_macdh"],  "h1_macds": tech["h1_macds"],
        "m15_ohlc": tech["m15_ohlc"], "m15_ema20": tech["m15_ema20"], "m15_ema50": tech["m15_ema50"],
        "m15_rsi":  tech["m15_rsi"],
        "m15_macd": tech["m15_macd"], "m15_macdh": tech["m15_macdh"], "m15_macds": tech["m15_macds"],
        "h4_ohlc":  tech["h4_ohlc"],  "h4_ema20": tech["h4_ema20"],  "h4_ema50": tech["h4_ema50"],
        "h4_rsi":   tech["h4_rsi"],
        "h4_macd":  tech["h4_macd"],  "h4_macdh": tech["h4_macdh"],  "h4_macds": tech["h4_macds"],
        "prev_day_high": tech["prev_day_high"], "prev_day_low": tech["prev_day_low"], "prev_day_close": tech["prev_day_close"],
        "daily_pivot_pp": tech["daily_pivot_pp"], "daily_pivot_r1": tech["daily_pivot_r1"], "daily_pivot_r2": tech["daily_pivot_r2"], "daily_pivot_r3": tech["daily_pivot_r3"],
        "daily_pivot_s1": tech["daily_pivot_s1"], "daily_pivot_s2": tech["daily_pivot_s2"], "daily_pivot_s3": tech["daily_pivot_s3"],
        "current_time": now_ict.strftime("%Y-%m-%d %H:%M:%S ICT"),
    }

    user_prompt = format_user_prompt(ctx)
    ai_response = call_gpt_api(user_prompt)

    full_message = f"{pair}\n{'-'*20}\n{ai_response}"
    send_telegram_message(full_message)
    time.sleep(2)
    bot.send(ai_response)
    time.sleep(2)

def send_telegram_message(text):
    """Sends a message to a Telegram chat."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {'chat_id': CHAT_ID, 'text': text, 'parse_mode': 'Markdown'}
    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        print(f"📨 Telegram message sent successfully.")
    except requests.exceptions.RequestException as e:
        print(f"❌ Telegram send failed: {e}")

if __name__ == '__main__':
    print("🚀 Starting Forex Analysis Bot...")

    # สร้าง Instance ของ Data Fetcher
    print("Initializing data connection...")
    data_fetcher = IQDataFetcher()
    analyzer = TyphoonForexAnalyzer(TYPHOON_API_KEY)
    notifier = TelegramNotifier(SIGNAL_TOKEN, CHAT_ID)
    bot_tele = ForexBot(analyzer, notifier)
    # เช็คว่าเชื่อมต่อสำเร็จไหม
    if data_fetcher.api is None:
        send_telegram_message("❌ Bot could not connect to IQ Option. Shutting down.")
        exit(1)
    
    # 1. ดึงข้อมูลข่าวจาก Forex Factory
    all_events = scrape_forex_factory()
    if not all_events:
        print("📰 No news events found for today, or scraping failed. Proceeding with technical analysis only.")
        all_events = [] # ทำให้แน่ใจว่าเป็น list ว่าง
    else:
        print(f"📰 Scraped {len(all_events)} total events.")
    
    set_global_macro_from_events(all_events)
    # print("🧭 Global Macro Baseline:", GLOBAL_MACRO)

    # 2. ตั้งค่าคู่เงินที่ต้องการวิเคราะห์
    target_pairs = ["EUR/USD", "USD/JPY"] #["EUR/USD", "GBP/USD", "USD/JPY", "EUR/GBP", "EUR/CHF"]
    
    # 3. วนลูปเพื่อวิเคราะห์และส่งข้อมูลทีละคู่เงิน
    now_ict = datetime.utcnow() + timedelta(hours=7)
    initial_message = f"📈 *Daily Analysis Rundown* at {now_ict.strftime('%Y-%m-%d %H:%M')} ICT"
    send_telegram_message(initial_message)
    time.sleep(2)

    for pair in target_pairs:
        analyze_and_send(all_events, pair, data_fetcher,bot_tele)

    data_fetcher.close_connection()  
    print("\n✅ All pairs analyzed. Script finished.")