# ========== Import Libraries ==========
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import requests
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
import google.generativeai as genai
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
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36'}
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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TYPHOON_API_KEY = os.getenv("TYPHOON_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SIGNAL_TOKEN = os.getenv("SIGNAL_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# ตั้งค่า Gemini
genai.configure(api_key=GEMINI_API_KEY)
generation_config = {
  "temperature": 0.4,
  "top_p": 1,
  "top_k": 1,
  "max_output_tokens": 4096,
}
safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]
model = genai.GenerativeModel(
    model_name="gemini-1.5-pro-latest",
    generation_config=generation_config,
    safety_settings=safety_settings
)

SYSTEM_PROMPT = """
You are a world-class Forex market analyst and strategist, specializing in short-term trading (aiming for 6-12 hour position closure) for major currency pairs like EUR/USD, USD/JPY, USD/CHF, and USD/CAD. Your analysis must rigorously integrate high-impact fundamental news events with multi-timeframe technical analysis (H1 and M15).

Your primary goal is to provide a clear, actionable trading plan for a day trader. This plan must identify the **main trend**, **key support/resistance zones**, and **high-probability entry setups** based on common M15 price action patterns (e.g., strong candlestick reversals, engulfing patterns, pin bars, break-and-retest of key levels). The output must be concise, structured, and formatted with Markdown for Telegram, ensuring it's easy to read and understand.

Crucially, all trading scenarios must include:
1.  **Well-defined TP1 and TP2 (optional) targets**, with clear and explicit reasoning based on technical confluence (e.g., next significant S/R, daily pivot points, previous swing highs/lows, Fibonacci levels if applicable).
2.  A **logical SL area**, designed for a 6-12 hour holding period, placed strategically below/above key technical levels (e.g., below support, above resistance, beyond a previous swing low/high) to protect capital effectively.
3.  **Explicit reasoning** for both TP and SL placements, explaining the technical rationale.

Your analysis must connect the high-impact economic events directly to current market sentiment, potential volatility, and the most likely directional bias for the specific currency pair. If no high-probability setup is identified based on the provided data and current market conditions, clearly state the reasons for caution and advise a "no trade" stance for the given period.

Ensure the language is professional yet accessible, avoiding overly academic jargon but maintaining a high standard of analytical rigor.
"""

USER_PROMPT_TEMPLATE = """
Analyze the market for {pair} for today, {date}.

1.  **High-Impact Economic Events (Fundamental Context):**
    {news_data}

2.  **Technical Analysis - H1 Timeframe (Daily Bias & Key Zones):**
    * H1 OHLC Data (last 5 candles) (Note: All price data is in 0.1 pips. For example, 1.07543 represents 1.07543, where the '3' is the 0.1 pip unit. A 1-pip movement changes the second to last decimal place.): {h1_ohlc}
    * H1 Indicators: EMA(20)={h1_ema20}, EMA(50)={h1_ema50}, RSI(14)={h1_rsi}
    * Previous Day's Levels: High={prev_day_high}, Low={prev_day_low}, Close={prev_day_close}
    * Daily Pivot Points: PP={daily_pivot_pp}, R1={daily_pivot_r1}, R2={daily_pivot_r2}, R3={daily_pivot_r3}, S1={daily_pivot_s1}, S2={daily_pivot_s2}, S3={daily_pivot_s3}

3.  **Technical Analysis - M15 Timeframe (Entry & Confirmation):**
    * M15 OHLC Data (last 5 candles): {m15_ohlc}
    * M15 Indicators: EMA(20)={m15_ema20}, EMA(50)={m15_ema50}, RSI(14)={m15_rsi}

Current time (for reference): {current_time}
"""

def call_gemini_api(user_prompt):
    """Calls the Gemini API with the structured prompt."""
    print("🛰️  Calling Gemini API...")
    try:
        convo = model.start_chat(history=[
            {'role': 'user', 'parts': [SYSTEM_PROMPT]},
            {'role': 'model', 'parts': ["Acknowledged. I am ready to analyze the provided market data."]}
        ])
        convo.send_message(user_prompt)
        print("✅ Gemini response received.")
        return convo.last.text
    except Exception as e:
        print(f"❌ Gemini API call failed: {e}")
        return "Error: Could not get analysis from Gemini."

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
def analyze_and_send(all_events, pair, data_fetcher,bot):
    """Analyzes a specific pair using news and technical data, then sends it."""
    print(f"\n===== Analyzing: {pair} =====")
    
    # 1. กรองข่าวที่เกี่ยวข้องกับคู่เงิน
    currencies = pair.split('/')
    relevant_news = [
        event for event in all_events 
        if event['Currency'] in currencies and "High" in event.get('Impact', '')
    ]
    news_data_str = json.dumps(relevant_news, indent=2) if relevant_news else "No high-impact news scheduled for this pair."
    
    # 2. ดึงข้อมูล Technical (จากคลาส IQDataFetcher) <<<< แก้ไขตรงนี้
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
        prev_day_high=tech_data["prev_day_high"], # เพิ่มเข้ามา
        prev_day_low=tech_data["prev_day_low"],   # เพิ่มเข้ามา
        prev_day_close=tech_data["prev_day_close"], # เพิ่มเข้ามา
        daily_pivot_pp=tech_data["daily_pivot_pp"], # เพิ่มเข้ามา
        daily_pivot_r1=tech_data["daily_pivot_r1"], # เพิ่มเข้ามา
        daily_pivot_r2=tech_data["daily_pivot_r2"], # เพิ่มเข้ามา
        daily_pivot_r3=tech_data["daily_pivot_r3"], # เพิ่มเข้ามา
        daily_pivot_s1=tech_data["daily_pivot_s1"], # เพิ่มเข้ามา
        daily_pivot_s2=tech_data["daily_pivot_s2"], # เพิ่มเข้ามา
        daily_pivot_s3=tech_data["daily_pivot_s3"], # เพิ่มเข้ามา
        m15_ohlc=tech_data["m15_ohlc"],
        m15_rsi=tech_data["m15_rsi"],
        m15_ema20=tech_data["m15_ema20"],
        m15_ema50=tech_data["m15_ema50"],
        current_time=current_time_str
    )
    
    # 4. เรียก Gemini API
    ai_response = call_gemini_api(user_prompt)
    
    # 5. ส่งผลลัพธ์ไปที่ Telegram
    header = f"💎 *Gemini Forex Analysis for {pair}*"
    full_message = f"{header}\n{'-'*20}\n{ai_response}"
    send_telegram_message(full_message)
    time.sleep(5)
    bot.send(full_message)
    time.sleep(5)

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
        # ไม่ต้องลอง requests อีก เพราะเรารู้ว่ามันใช้ไม่ได้
        print("📰 No news events found for today, or scraping failed. Proceeding with technical analysis only.")
        all_events = [] # ทำให้แน่ใจว่าเป็น list ว่าง
    else:
        print(f"📰 Scraped {len(all_events)} total events.")

    # 2. ตั้งค่าคู่เงินที่ต้องการวิเคราะห์
    target_pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "USD/CAD"]
    
    # 3. วนลูปเพื่อวิเคราะห์และส่งข้อมูลทีละคู่เงิน
    now_ict = datetime.utcnow() + timedelta(hours=7)
    initial_message = f"📈 *Daily Analysis Rundown* at {now_ict.strftime('%Y-%m-%d %H:%M')} ICT"
    send_telegram_message(initial_message)
    time.sleep(2)

    for pair in target_pairs:
        # ไม่ว่าจะมีข่าวหรือไม่ ก็ให้ทำงานต่อไป
        analyze_and_send(all_events, pair, data_fetcher,bot_tele)

    data_fetcher.close_connection()  
    print("\n✅ All pairs analyzed. Script finished.")
