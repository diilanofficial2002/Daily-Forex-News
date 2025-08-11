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

# ========== Gemini AI and Telegram Functions ==========
# Config
client = OpenAI()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TYPHOON_API_KEY = os.getenv("TYPHOON_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SIGNAL_TOKEN = os.getenv("SIGNAL_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# ตั้งค่า Gemini

SYSTEM_PROMPT = """
You are an intraday FX analyst focused on same-day trades (minutes to hours).
Your job is to combine ECONOMIC EVENTS with MULTI-TIMEFRAME TECHNICALS and
produce a tightly structured analysis that downstream tools will parse.

Operating assumptions (do not violate):
- Timezone is Asia/Bangkok (ICT). Treat all times as ICT unless stated.
- Do not invent data. Use only inputs provided.
- Write in clear, concise English. Avoid emojis, filler, and disclaimers.
- Keep headings EXACT. Keep each bullet short and action-oriented.
- For price formatting: non-JPY pairs to 5 decimals (e.g., 1.08520), JPY pairs to 3 decimals (e.g., 148.230).
- If required info is missing, write "Insufficient data" at that field.
- Output must fit within ~900 tokens.

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
   - Entry: [precise multi-TF condition incl. levels]
   - TP: [...]
   - SL: [...]
   - Risk: [main invalidation factors]
   ### SHORT
   - Entry: [...]
   - TP: [...]
   - SL: [...]
   - Risk: [...]

5) ## RISK ALERTS
   - [events/time-windows or structure that can flip bias; ≤40 words]

Analysis method:
- Economic events: judge timing vs current time (pre/post), currency relevance, surprise vs forecast, and spillovers to the pair.
- Technicals: use H1 for context, M15/M5 for triggers; align with pivots/prev day H/L; confirm with EMA(20/50), RSI(14), MACD.
- Be specific about price interaction with zones and candle behavior.
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

4) M5 Technicals
- OHLC (last 5): {m5_ohlc}
- EMA20={m5_ema20}, EMA50={m5_ema50}, RSI14={m5_rsi}, MACD={m5_macd}, MACD_Hist={m5_macdh}, MACD_Signal={m5_macds}

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
- TP: ...
- SL: ...
- Risk: ...
### SHORT
- Entry: ...
- TP: ...
- SL: ...
- Risk: ...

## RISK ALERTS
- ...
"""

def call_gpt_api(user_prompt: str) -> str:
    """
    Call GPT-5 mini for intraday analysis.
    - Use 'instructions' for system prompt (cheaper + cache-friendly).
    - Use 'input' for the full user prompt.
    """
    try:
        resp = client.responses.create(
            model="gpt-5-mini",
            instructions=SYSTEM_PROMPT,      # keep your static system schema (cache-friendly)
            input=user_prompt,
            text={"verbosity":"medium",},               # your per-pair dynamic content
            reasoning={"effort":"low"},         # concise but complete
            max_output_tokens=1200
        )
        return resp.output_text
    except Exception as e:
        print(f"❌ OpenAI API call failed: {e}")
        return "Error: Could not get analysis from GPT-5 mini."


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

# ========== Main Workflow ==========
def analyze_and_send(all_events, pair, data_fetcher, bot):
    """Analyzes a specific pair using news and technical data, then sends it."""
    print(f"\n===== Analyzing: {pair} =====")
    
    # 1. กรองข่าวที่เกี่ยวข้องกับคู่เงิน (รับทุก Impact)
    currencies = pair.split('/')
    relevant_news = [
        event for event in all_events 
        if event['Currency'] in currencies and event.get('Impact') # รับทุก event ที่มีสกุลเงินตรงกันและมีค่า Impact
    ]
    news_data_str = json.dumps(relevant_news, indent=2) if relevant_news else "No relevant news scheduled for this pair today."

    # 2. ดึงข้อมูล Technical (จากคลาส IQDataFetcher)
    print(f"⚙️ Fetching REAL technical data for {pair}...")
    tech_data = data_fetcher.get_technical_data(pair)
    if not tech_data: # ตรวจสอบว่ามีข้อมูล tech_data ครบถ้วนหรือไม่
        send_telegram_message(f"⚠️ Could not fetch comprehensive technical data for *{pair}*. Skipping analysis.")
        return # ข้ามไปคู่ถัดไป

    # 3. สร้าง Prompt ที่สมบูรณ์
    today_date = datetime.now().strftime('%Y-%m-%d')
    # คำนวณเวลาปัจจุบันในโซนประเทศไทย (ICT)
    current_ict_time = datetime.utcnow() + timedelta(hours=7)
    current_time_str = current_ict_time.strftime('%Y-%m-%d %H:%M:%S ICT')

    user_prompt = USER_PROMPT_TEMPLATE.format(
        pair=pair,
        date=today_date,
        news_data=news_data_str,
        h1_ohlc=tech_data["h1_ohlc"],
        h1_ema20=tech_data["h1_ema20"],
        h1_ema50=tech_data["h1_ema50"],
        h1_rsi=tech_data["h1_rsi"],
        h1_macd=tech_data["h1_macd"],
        h1_macdh=tech_data["h1_macdh"],
        h1_macds=tech_data["h1_macds"],
        prev_day_high=tech_data["prev_day_high"],
        prev_day_low=tech_data["prev_day_low"],
        prev_day_close=tech_data["prev_day_close"],
        daily_pivot_pp=tech_data["daily_pivot_pp"],
        daily_pivot_r1=tech_data["daily_pivot_r1"],
        daily_pivot_r2=tech_data["daily_pivot_r2"],
        daily_pivot_r3=tech_data["daily_pivot_r3"],
        daily_pivot_s1=tech_data["daily_pivot_s1"],
        daily_pivot_s2=tech_data["daily_pivot_s2"],
        daily_pivot_s3=tech_data["daily_pivot_s3"],
        m15_ohlc=tech_data["m15_ohlc"],
        m15_rsi=tech_data["m15_rsi"],
        m15_ema20=tech_data["m15_ema20"],
        m15_ema50=tech_data["m15_ema50"],
        m15_macd=tech_data["m15_macd"],
        m15_macdh=tech_data["m15_macdh"],
        m15_macds=tech_data["m15_macds"],
        m5_ohlc=tech_data["m5_ohlc"],
        m5_rsi=tech_data["m5_rsi"],
        m5_ema20=tech_data["m5_ema20"],
        m5_ema50=tech_data["m5_ema50"],
        m5_macd=tech_data["m5_macd"],
        m5_macdh=tech_data["m5_macdh"],
        m5_macds=tech_data["m5_macds"],
        current_time=current_time_str
    )
    
    # 4. เรียก Gemini API
    ai_response = call_gpt_api(user_prompt)

    time.sleep(2)

    full_message = f"{pair}\n{'-'*20}\n{ai_response}"
    send_telegram_message(full_message)
    time.sleep(4)
    
    # 5. ส่งผลลัพธ์ไปที่ Telegram (ปรับแก้เพื่อให้ TyphoonForexAnalyzer สรุปก่อน)
    bot.send(ai_response) # ส่ง raw_analysis_text ไปให้ bot.send ซึ่งจะเรียก Typhoon Analyzer
    time.sleep(4)

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

    # 2. ตั้งค่าคู่เงินที่ต้องการวิเคราะห์
    target_pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "EUR/GBP", "EUR/CHF"]
    
    # 3. วนลูปเพื่อวิเคราะห์และส่งข้อมูลทีละคู่เงิน
    now_ict = datetime.utcnow() + timedelta(hours=7)
    initial_message = f"📈 *Daily Analysis Rundown* at {now_ict.strftime('%Y-%m-%d %H:%M')} ICT"
    send_telegram_message(initial_message)
    time.sleep(2)

    for pair in target_pairs:
        analyze_and_send(all_events, pair, data_fetcher,bot_tele)

    data_fetcher.close_connection()  
    print("\n✅ All pairs analyzed. Script finished.")