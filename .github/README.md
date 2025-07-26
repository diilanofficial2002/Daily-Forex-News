# 🤖 Automated Forex Analysis Bot

บอทวิเคราะห์ตลาด Forex อัตโนมัติที่ผสมผสานระหว่างปัจจัยพื้นฐาน (ข่าวเศรษฐกิจ) และปัจจัยทางเทคนิค (ข้อมูลราคาและ Indicators) โดยใช้ **Google Gemini AI** ในการวิเคราะห์และส่งแผนการเทรดรายวันผ่าน **Telegram**

## 🚀 คุณสมบัติ (Features)

- **Automated News Scraping**: ดึงข้อมูลข่าวเศรษฐกิจจาก `ForexFactory` อัตโนมัติ
- **Real-time Technical Data**: เชื่อมต่อ **IQ Option API** เพื่อดึงข้อมูลราคา (OHLC) และคำนวณ Technical Indicators (EMA, RSI)
- **Advanced AI Analysis**: ใช้ **Google Gemini** ในการวิเคราะห์ข้อมูลทั้งหมดเพื่อสร้างแผนการเทรดรายวัน
- **Telegram Notifications**: ส่งบทวิเคราะห์และแผนการเทรดที่ชัดเจนไปยังช่องทาง Telegram
- **Scheduled & Automated**: ทำงานอัตโนมัติทุกวันตามเวลาที่กำหนดด้วย **GitHub Actions**

## 📋 สิ่งที่ต้องมี (Requirements)

- Python 3.9+
- Playwright (สำหรับดึงข้อมูลเว็บ)
- Pandas & Pandas-TA (สำหรับจัดการข้อมูลและคำนวณ Indicators)
- Google Generative AI SDK (สำหรับ Gemini API)
- IQ Option API
- บัญชี IQ Option (แนะนำให้เริ่มด้วยบัญชี Practice)
- Google Gemini API Key
- Telegram Bot Token

## 🔧 วิธีการติดตั้ง (Setup Instructions)

### 1\. การติดตั้งในเครื่อง (Local Setup)

```bash
# Clone a repository
git clone https://github.com/diilanofficial2002/Daily-Forex-News.git
cd Daily-Forex-News

# ติดตั้ง Dependencies จาก requirements.txt
pip install -r requirements.txt

# ติดตั้ง IQ Option API โดยตรงจาก GitHub
pip install -U git+https://github.com/iqoptionapi/iqoptionapi.git@7.1.1

# ติดตั้ง Browsers สำหรับ Playwright
npx playwright install --with-deps

# สร้างไฟล์ .env สำหรับเก็บข้อมูลสำคัญ
# คัดลอก .env.example (ถ้ามี) หรือสร้างไฟล์ใหม่
```

### 2\. ตั้งค่า Environment Variables

สร้างไฟล์ชื่อ `.env` ในโฟลเดอร์หลักของโปรเจกต์ แล้วใส่ข้อมูลของนายลงไป:

```env
# สำหรับ Gemini API
GEMINI_API_KEY="your_google_gemini_api_key"

# สำหรับ Telegram Bot
TELEGRAM_TOKEN="your_telegram_bot_token"
CHAT_ID="your_telegram_chat_id"

# สำหรับ IQ Option API
IQ_USER="your_iqoption_email"
IQ_PASS="your_iqoption_password"
```

### 3\. ตั้งค่าสำหรับ GitHub Actions

#### Required Secrets

ไปที่หน้า Repository ของนายบน GitHub \> **Settings** \> **Secrets and variables** \> **Actions** แล้วเพิ่ม Secrets ทั้งหมด 5 ตัวนี้:

- `GEMINI_API_KEY`
- `TELEGRAM_TOKEN`
- `CHAT_ID`
- `IQ_USER`
- `IQ_PASS`

-----

### 4\. ตารางเวลาการทำงาน (Workflow Schedule)

บอทถูกตั้งค่าให้ทำงานอัตโนมัติ **1 ครั้งต่อวัน** ในเวลา **6:00 น. ตามเวลาประเทศไทย** (23:00 UTC)

### 5\. การสั่งให้ทำงานด้วยตนเอง (Manual Trigger)

นายสามารถสั่งให้บอททำงานทันทีเพื่อทดสอบได้โดย:

1. ไปที่แท็บ **Actions** ในหน้า GitHub repository
2. เลือก **Run Daily Forex Analysis** ในเมนูด้านซ้าย
3. กดปุ่ม **Run workflow**

## 📈 การปรับแต่ง (Customization)

### แก้ไขตารางเวลา

แก้ไข `cron` ในไฟล์ `.github/workflows/run_forex_new_6am.yml` เพื่อเปลี่ยนเวลาทำงาน

### ปรับเปลี่ยนการวิเคราะห์ของ AI

แก้ไข `SYSTEM_PROMPT` ในไฟล์ `forex_daily_news.py` เพื่อปรับเปลี่ยนบุคลิกหรือเป้าหมายการวิเคราะห์ของ Gemini

### เพิ่ม/ลดคู่เงิน

แก้ไขลิสต์ `target_pairs` ในไฟล์ `forex_daily_news.py` เพื่อกำหนดคู่เงินที่ต้องการวิเคราะห์

## 📝 โครงสร้างไฟล์ (File Structure)

```text
├── .github/
│   └── workflows/
│       └── run_forex_new_6am.yml    # ไฟล์ควบคุม GitHub Actions
├── get_data.py                      # ไฟล์สำหรับดึงข้อมูลจาก IQ Option
├── forex_daily_news.py              # สคริปต์หลัก
├── requirements.txt                 # รายชื่อ Python dependencies
├── .env                             # ไฟล์เก็บข้อมูลสำคัญ (ไม่ควร push ขึ้น GitHub)
└── README.md                        # ไฟล์นี้
```

## 📄 ใบอนุญาต (License)

This project is licensed under the MIT License.

## ⚠️ คำเตือน (Disclaimer)

เครื่องมือนี้สร้างขึ้นเพื่อวัตถุประสงค์ในการศึกษาและเป็นข้อมูลเท่านั้น ควรตรวจสอบข้อมูลจากแหล่งที่เป็นทางการเสมอและตัดสินใจลงทุนด้วยความระมัดระวัง
