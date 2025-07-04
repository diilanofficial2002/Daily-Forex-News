import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import requests
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
import requests
import json
import time
import openai

load_dotenv()

# ตั้งค่า Environment Variable สำหรับ timezone
os.environ['TZ'] = 'Asia/Bangkok'
time.tzset()  # สำหรับ Unix/Linux systems

# ตั้งค่า Browser
options = Options()
options.add_argument('--headless')
options.add_argument('--disable-gpu')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')  # เพิ่มเพื่อป้องกัน memory issues
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")

driver = webdriver.Chrome(options=options)

# ตั้งค่า timezone สำหรับ Chrome
driver.execute_cdp_cmd(
    'Emulation.setTimezoneOverride',
    {'timezoneId': 'Asia/Bangkok'} 
)

# เพิ่มการตั้งค่า locale สำหรับ Chrome
driver.execute_cdp_cmd(
    'Emulation.setLocaleOverride',
    {'locale': 'th-TH'}
)

try:
    url = "https://www.forexfactory.com/"
    
    driver.get(url)
    time.sleep(5)

    # ตรวจสอบ timezone ที่ browser ใช้
    timezone_check = driver.execute_script("return Intl.DateTimeFormat().resolvedOptions().timeZone")
    print(f"Browser timezone: {timezone_check}")
    
    soup = BeautifulSoup(driver.page_source, 'html.parser')

    table = soup.find("table", class_="calendar__table")
    rows = table.find_all("tr", class_="calendar__row")

    # ใช้ Thailand timezone แทน UTC
    from zoneinfo import ZoneInfo
    thailand_tz = ZoneInfo("Asia/Bangkok")
    today = datetime.now(thailand_tz).strftime("%a")  # เช่น 'Tue' สำหรับวันอังคาร
    
    print(f"Today in Thailand: {today}")

    extracted = []
    for row in rows:
        time_td = row.find("td", class_="calendar__time")
        time_text = time_td.get_text(strip=True) if time_td else ""

        # บางแถวจะไม่มีเวลา (เช่นเป็นเหตุการณ์ก่อนหน้านี้) → ข้าม
        if not time_text or time_text.lower() == 'all day':
            continue

        # ดึงข้อมูลอื่น
        currency = row.find("td", class_="calendar__currency").get_text(strip=True)
        impact = row.find("td", class_="calendar__impact").get_text(strip=True)
        event = row.find("td", class_="calendar__event").get_text(strip=True)
        actual = row.find("td", class_="calendar__actual").get_text(strip=True)
        forecast = row.find("td", class_="calendar__forecast").get_text(strip=True)
        previous = row.find("td", class_="calendar__previous").get_text(strip=True)

        extracted.append([time_text, currency, impact, event, actual, forecast, previous])

    keys = ["Time", "Currency", "Impact", "Event", "Actual", "Forecast", "Previous"]
    list_of_dicts = [dict(zip(keys, row)) for row in extracted]
    print("Success Scrap!")

finally:
    driver.quit()

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

def dispatch_messages(text,timeout):
    # Split by double newlines assuming each event block separated by \n\n
    blocks = [block.strip() for block in text.split('\n\n') if block.strip()]
    for block in blocks:
        send_telegram_message(block)
        time.sleep(timeout)  # rate-limit safety pause

# --- Main workflow ---

def analyze_and_send(events,timeout=2):
    for chunk in chunk_events(events, chunk_size=5):
        chunk_json = json.dumps(chunk, ensure_ascii=False)
        user_prompt = USER_PROMPT_TEMPLATE.format(events_json=chunk_json)
        try:
            ai_response = call_typhoon_api(SYSTEM_PROMPT, user_prompt)
        except Exception as e:
            print(f"Error calling Typhoon API: {e}")
            continue
        dispatch_messages(ai_response,timeout)

# --- Example usage ---
if __name__ == '__main__':
    send_update_message_thai_time()
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
    print("Script completed successfully.")