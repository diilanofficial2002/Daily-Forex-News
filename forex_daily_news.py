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
    """Scrape ForexFactory using Playwright - GitHub Actions optimized"""
    
    with sync_playwright() as p:
        # Launch browser without user data dir for CI/CD compatibility
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor',
                '--disable-blink-features=AutomationControlled',
                '--window-size=1920,1080',
                '--disable-extensions',
                '--disable-plugins',
                '--disable-images',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding'
            ]
        )

        # Create context with proper settings
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            extra_http_headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
        )

        # Set default timeout
        context.set_default_timeout(60000)  # 60 seconds
        page = context.new_page()

        # Set timezone cookie before navigation
        context.add_cookies([{
            'name': 'fftimezone',
            'value': 'Pacific%2FMajuro',
            'domain': '.forexfactory.com',
            'path': '/'
        }])

        try:
            print("🔄 Loading ForexFactory with Playwright...")
            retry_count = 0
            max_retries = 3

            while retry_count < max_retries:
                try:
                    page.goto("https://www.forexfactory.com/", wait_until="domcontentloaded", timeout=60000)
                    print("⏳ Waiting for page to load completely...")
                    page.wait_for_timeout(15000)

                    page_content = page.content()
                    if "Verifying you are human" in page_content or "Cloudflare" in page_content:
                        print(f"❌ Blocked by Cloudflare (attempt {retry_count + 1})")
                        retry_count += 1
                        if retry_count < max_retries:
                            print("🔄 Retrying in 10 seconds...")
                            time.sleep(10)
                            continue
                        else:
                            print("❌ Max retries reached for Cloudflare bypass")
                            return []
                    break

                except Exception as e:
                    print(f"❌ Navigation error (attempt {retry_count + 1}): {e}")
                    retry_count += 1
                    if retry_count < max_retries:
                        print("🔄 Retrying in 10 seconds...")
                        time.sleep(10)
                        continue
                    else:
                        print("❌ Max retries reached for navigation")
                        return []

            print("⏳ Waiting for calendar table...")
            try:
                page.wait_for_selector(
                    ".calendar__table, table.calendar, .calendar-table, [class*='calendar']",
                    timeout=30000
                )
                print("✅ Calendar table found!")
            except:
                print("⚠️ Calendar table not found with primary selector, trying alternative...")
                try:
                    page.wait_for_selector("table", timeout=15000)
                    print("✅ Found table element!")
                except:
                    print("⚠️ No table found, proceeding with HTML parsing...")

            html_content = page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            print(f"📄 Page title: {soup.title.string if soup.title else 'No title'}")
            print(f"📄 Page content length: {len(html_content)}")

            table = None
            table_selectors = [
                "table.calendar__table",
                ".calendar__table",
                "table[class*='calendar']",
                "table",
            ]

            for selector in table_selectors:
                if selector == "table":
                    tables = soup.find_all("table")
                    for t in tables:
                        if any(word in str(t).lower() for word in ['calendar', 'time', 'currency', 'event']):
                            table = t
                            break
                else:
                    table = soup.select_one(selector)

                if table:
                    print(f"✅ Found table using selector: {selector}")
                    break

            if not table:
                print("❌ Calendar table not found in HTML")
                print("🔍 Available table classes:")
                for t in soup.find_all("table"):
                    print(f"  - {t.get('class', 'No class')}")
                return []

            row_selectors = [
                "tr.calendar__row",
                "tr[class*='calendar']",
                "tr",
            ]
            rows = []

            for selector in row_selectors:
                if selector == "tr":
                    rows = table.find_all("tr")
                else:
                    rows = table.select(selector)

                if rows:
                    print(f"✅ Found {len(rows)} rows using selector: {selector}")
                    break

            if not rows:
                print("❌ No calendar rows found")
                return []

            print(f"📊 Processing {len(rows)} calendar rows")
            extracted = []

            for i, row in enumerate(rows):
                try:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) < 6:
                        continue

                    time_text = cells[0].get_text(strip=True)
                    currency = cells[1].get_text(strip=True)
                    impact = cells[2].get_text(strip=True)
                    event = cells[3].get_text(strip=True)
                    actual = cells[4].get_text(strip=True)
                    forecast = cells[5].get_text(strip=True)
                    previous = cells[6].get_text(strip=True) if len(cells) > 6 else ""

                    if not time_text or time_text.lower() in ['all day', 'time', '']:
                        continue

                    if not any([currency, event, actual, forecast, previous]):
                        continue

                    extracted.append([time_text, currency, impact, event, actual, forecast, previous])

                except Exception as e:
                    print(f"⚠️ Error extracting row {i}: {e}")
                    continue

            keys = ["Time", "Currency", "Impact", "Event", "Actual", "Forecast", "Previous"]
            list_of_dicts = [dict(zip(keys, row)) for row in extracted]

            print(f"✅ Successfully extracted {len(list_of_dicts)} events!")

            if list_of_dicts:
                print("📋 First extracted event:")
                print(json.dumps(list_of_dicts[0], indent=2))

            return list_of_dicts

        except Exception as e:
            print(f"❌ Error during scraping: {e}")
            import traceback
            traceback.print_exc()
            return []

        finally:
            try:
                context.close()
                browser.close()
            except Exception:
                pass

# ========== Alternative Scraper using requests + BeautifulSoup ==========
def scrape_forex_factory_requests():
    """Fallback scraper using requests + BeautifulSoup"""
    
    print("🔄 Trying fallback scraper with requests...")
    
    session = requests.Session()
    
    # Set headers to mimic real browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    session.headers.update(headers)
    
    # Set timezone cookie
    session.cookies.set('fftimezone', 'Pacific%2FMajuro', domain='.forexfactory.com')
    
    try:
        # Make request with longer timeout
        response = session.get('https://www.forexfactory.com/', timeout=30)
        response.raise_for_status()
        
        # Parse with BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Check if blocked
        if "Verifying you are human" in response.text or "Cloudflare" in response.text:
            print("❌ Blocked by Cloudflare in requests method")
            return []
        
        # Find calendar table
        table = soup.find("table", class_="calendar__table")
        if not table:
            # Try alternative selectors
            table = soup.find("table", class_=lambda x: x and 'calendar' in x.lower())
        
        if not table:
            print("❌ No calendar table found in requests method")
            return []
        
        # Extract rows similar to Playwright method
        rows = table.find_all("tr")
        
        extracted = []
        for row in rows:
            try:
                cells = row.find_all(['td', 'th'])
                
                if len(cells) < 6:
                    continue
                
                time_text = cells[0].get_text(strip=True) if len(cells) > 0 else ""
                currency = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                impact = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                event = cells[3].get_text(strip=True) if len(cells) > 3 else ""
                actual = cells[4].get_text(strip=True) if len(cells) > 4 else ""
                forecast = cells[5].get_text(strip=True) if len(cells) > 5 else ""
                previous = cells[6].get_text(strip=True) if len(cells) > 6 else ""
                
                if not time_text or time_text.lower() in ['all day', 'time', '']:
                    continue
                
                if not any([currency, event, actual, forecast, previous]):
                    continue
                
                extracted.append([time_text, currency, impact, event, actual, forecast, previous])
                
            except Exception as e:
                continue
        
        keys = ["Time", "Currency", "Impact", "Event", "Actual", "Forecast", "Previous"]
        list_of_dicts = [dict(zip(keys, row)) for row in extracted]
        
        print(f"✅ Requests method extracted {len(list_of_dicts)} events!")
        return list_of_dicts
        
    except Exception as e:
        print(f"❌ Requests method failed: {e}")
        return []

# ========== AI and Telegram Functions ==========
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
    
    # Try Playwright first, then fallback to requests
    print("📡 Scraping ForexFactory...")
    list_of_dicts = scrape_forex_factory()
    
    # If Playwright fails, try requests method
    if not list_of_dicts:
        print("🔄 Playwright failed, trying requests method...")
        list_of_dicts = scrape_forex_factory_requests()
    
    if not list_of_dicts:
        print("❌ Both scraping methods failed, exiting...")
        send_telegram_message("❌ Failed to scrape ForexFactory data using both methods")
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