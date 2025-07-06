from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import requests
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
import openai
import os
import json

load_dotenv()

# ========== Playwright Scraper Function ==========
def scrape_forex_factory():
    """Scrape ForexFactory using Playwright"""
    
    with sync_playwright() as p:
        # Launch browser with anti-detection settings
        browser = p.chromium.launch(
            headless=False,  # Set to True if you want headless mode
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-gpu',
                '--window-size=1920,1080'
            ]
        )
        
        # Create context with realistic settings
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        page = context.new_page()
        
        try:
            print("🔄 Loading ForexFactory with Playwright...")
            
            # Navigate to ForexFactory
            page.goto("https://www.forexfactory.com/", wait_until="networkidle")
            
            # Wait for potential Cloudflare challenge
            print("⏳ Waiting for page to load completely...")
            page.wait_for_timeout(10000)  # 10 seconds
            
            # Check if we're blocked by Cloudflare
            if "Verifying you are human" in page.content():
                print("❌ Blocked by Cloudflare, waiting longer...")
                page.wait_for_timeout(20000)  # Wait 20 more seconds
                
                if "Verifying you are human" in page.content():
                    print("❌ Still blocked by Cloudflare")
                    return []
            
            # Wait for calendar table to load
            try:
                page.wait_for_selector(".calendar__table", timeout=30000)
                print("✅ Calendar table found!")
            except:
                print("⚠️ Calendar table not found immediately, trying anyway...")
            
            # Set timezone cookie
            context.add_cookies([{
                'name': 'fftimezone',
                'value': 'Pacific%2FMajuro',  # Same as your original
                'domain': '.forexfactory.com',
                'path': '/'
            }])
            
            # Reload page to apply cookie
            print("🔄 Reloading page with timezone cookie...")
            page.reload(wait_until="networkidle")
            page.wait_for_timeout(5000)
            
            # Wait for calendar table again
            try:
                page.wait_for_selector(".calendar__table", timeout=15000)
                print("✅ Calendar table loaded with timezone!")
            except:
                print("⚠️ Calendar table not found after reload")
            
            # Get page content
            html_content = page.content()
            
            # Parse with BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            print("========== Raw HTML Preview ==========")
            print(soup.prettify()[:3000])
            
            # Extract calendar data
            table = soup.find("table", class_="calendar__table")
            
            if not table:
                print("❌ Calendar table not found in HTML")
                return []
            
            rows = table.find_all("tr", class_="calendar__row")
            
            if not rows:
                print("❌ No calendar rows found")
                return []
            
            print(f"📊 Found {len(rows)} calendar rows")
            
            extracted = []
            for row in rows:
                try:
                    time_td = row.find("td", class_="calendar__time")
                    time_text = time_td.get_text(strip=True) if time_td else ""
                    
                    if not time_text or time_text.lower() == 'all day':
                        continue
                    
                    # Safe extraction to avoid AttributeError
                    currency_td = row.find("td", class_="calendar__currency")
                    impact_td = row.find("td", class_="calendar__impact")
                    event_td = row.find("td", class_="calendar__event")
                    actual_td = row.find("td", class_="calendar__actual")
                    forecast_td = row.find("td", class_="calendar__forecast")
                    previous_td = row.find("td", class_="calendar__previous")
                    
                    currency = currency_td.get_text(strip=True) if currency_td else ""
                    impact = impact_td.get_text(strip=True) if impact_td else ""
                    event = event_td.get_text(strip=True) if event_td else ""
                    actual = actual_td.get_text(strip=True) if actual_td else ""
                    forecast = forecast_td.get_text(strip=True) if forecast_td else ""
                    previous = previous_td.get_text(strip=True) if previous_td else ""
                    
                    extracted.append([time_text, currency, impact, event, actual, forecast, previous])
                    
                except Exception as e:
                    print(f"⚠️ Error extracting row: {e}")
                    continue
            
            keys = ["Time", "Currency", "Impact", "Event", "Actual", "Forecast", "Previous"]
            list_of_dicts = [dict(zip(keys, row)) for row in extracted]
            
            print(f"✅ Successfully extracted {len(list_of_dicts)} events!")
            
            return list_of_dicts
            
        except Exception as e:
            print(f"❌ Error during scraping: {e}")
            return []
            
        finally:
            browser.close()

# ========== AI and Telegram Functions (unchanged) ==========
# Config
TYPHOON_URL = 'https://api.opentyphoon.ai/v1/chat/completions'
TYPHOON_KEY = os.getenv("TYPHOON_API_KEY")
TELEGRAM_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

SYSTEM_PROMPT = """
You are a professional macroeconomic analyst. Your task is to evaluate scheduled economic events and determine their likely directional impact on the following individual currencies: EUR, USD, GBP, CHF, and JPY.

Go beyond numerical values—analyze each event based on:
- The nature of the event (e.g., inflation data, central bank speech, sentiment survey, surprise rate cut).
- Whether the result is above or below expectations (if provided).
- The broader macroeconomic and policy context.
- Any likely shifts in monetary policy or market sentiment.

Output must be focused, concise, and actionable. Avoid greetings or conversational tone. Each response should be formatted in bullet-style blocks, suitable for use in trading signals or Telegram alerts.
"""

USER_PROMPT_TEMPLATE = """
Analyze the following economic events. For each event:

- Start with the time and event title.
- List only the **currencies directly affected**, with expected direction: "Likely to strengthen", "Likely to weaken", or "No significant change".
- Include a **brief explanation** of why this event matters — based not just on numbers, but also on the type of event, its economic role, market expectations, and the broader macro context.
- Highlight if this event may change monetary policy expectations or trigger volatility.

Format your output in concise bullet-style text. Each item must be standalone and suitable for Telegram.

Events:
{events_json}
"""

# --- Helper functions ---

def chunk_events(events, chunk_size=5):
    """Yield successive chunk_size-sized chunks from events list."""
    for i in range(0, len(events), chunk_size):
        yield events[i:i + chunk_size]

def call_typhoon_api(system_prompt, user_prompt):
    client = openai.OpenAI(
        api_key=TYPHOON_KEY,
        base_url="https://api.opentyphoon.ai/v1"
    )

    response = client.chat.completions.create(
        model="typhoon-v2-70b-instruct",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2,
        max_tokens=3000
    )
    return response.choices[0].message.content

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        'chat_id': CHAT_ID,
        'text': text,
        'parse_mode': 'Markdown',
    }
    resp = requests.post(url, data=data)
    try:
        resp.raise_for_status()
    except Exception as e:
        print(f"Telegram send failed: {resp.status_code} {resp.text}")
        raise e
    
def send_update_message_thai_time():
    now_utc = datetime.utcnow()
    now_ict = now_utc + timedelta(hours=7)  # UTC+7 = ICT (Thailand Time)
    formatted_time = now_ict.strftime('%Y-%m-%d %H:%M:%S')
    send_telegram_message(f"Updated News at {formatted_time} ICT")

def dispatch_messages(text, timeout):
    # Split by double newlines assuming each event block separated by \n\n
    blocks = [block.strip() for block in text.split('\n\n') if block.strip()]
    for block in blocks:
        send_telegram_message(block)
        time.sleep(timeout)  # rate-limit safety pause

# --- Main workflow ---

def analyze_and_send(events, timeout=2):
    if not events:
        print("❌ No events to analyze")
        send_telegram_message("❌ No economic events found to analyze")
        return
        
    for chunk in chunk_events(events, chunk_size=5):
        chunk_json = json.dumps(chunk, ensure_ascii=False)
        user_prompt = USER_PROMPT_TEMPLATE.format(events_json=chunk_json)
        try:
            ai_response = call_typhoon_api(SYSTEM_PROMPT, user_prompt)
        except Exception as e:
            print(f"Error calling Typhoon API: {e}")
            continue
        dispatch_messages(ai_response, timeout)

# --- Main execution ---
if __name__ == '__main__':
    print("🚀 Starting ForexFactory Scraper with Playwright")
    print("=" * 50)
    
    # Send initial message
    send_update_message_thai_time()
    
    # Scrape data
    print("📡 Scraping ForexFactory...")
    list_of_dicts = scrape_forex_factory()
    
    if not list_of_dicts:
        print("❌ No data scraped, exiting...")
        send_telegram_message("❌ Failed to scrape ForexFactory data")
        exit(1)
    
    print(f"📊 Scraped {len(list_of_dicts)} events")
    
    # Show first few events
    print("\n📋 First 3 events:")
    for i, event in enumerate(list_of_dicts[:3]):
        print(f"  {i+1}. {event}")
    
    # Analyze and send
    MAX_RETRIES = 5
    RETRY_DELAY = 3  # seconds
    
    retries = 0
    timer = 0.5
    
    while retries < MAX_RETRIES:
        try:
            analyze_and_send(list_of_dicts, timer)
            break  # Success, exit loop
        except Exception as e:
            print(f"Error in main workflow (attempt {retries + 1}): {e}")
            send_telegram_message(f"Error occurred: retrying...")
            send_update_message_thai_time()
            timer *= 2  # Increase timer for next retry
            retries += 1
            time.sleep(RETRY_DELAY)
    else:
        send_telegram_message("❌ Max retries reached. Process failed permanently.")
        
    # End of script
    print("✅ Script completed successfully.")