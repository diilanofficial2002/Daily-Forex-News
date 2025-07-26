# get_data.py
import os
import time
import pandas as pd
import pandas_ta as ta
from iqoptionapi.stable_api import IQ_Option
from dotenv import load_dotenv

# โหลดค่าจาก .env
load_dotenv()

class IQDataFetcher:
    """
    คลาสสำหรับเชื่อมต่อ IQ Option, ดึงข้อมูลราคา และคำนวณ Indicators
    """
    def __init__(self):
        """
        Constructor: โหลดข้อมูล login และเตรียมเชื่อมต่อ API
        """
        print("🤖 Initializing IQ Option Data Fetcher...")
        self.user = os.getenv("IQ_USER")
        self.password = os.getenv("IQ_PASS")
        self.api = None
        self.connect()

    def connect(self):
        """
        เชื่อมต่อกับ IQ Option API และเลือกบัญชี Practice
        """
        if not self.user or not self.password:
            print("❌ IQ_USER or IQ_PASS not found in .env file. Cannot connect.")
            return

        print(f"🔗 Connecting to IQ Option as {self.user}...")
        self.api = IQ_Option(self.user, self.password)
        check, reason = self.api.connect()

        if check:
            print("✅ Connection successful!")
            # เปลี่ยนเป็นบัญชีเงินฝึกหัด (Practice Account)
            # หากต้องการใช้เงินจริงให้เปลี่ยนเป็น "REAL"
            self.api.change_balance("PRACTICE") 
            print("💰 Switched to PRACTICE account.")
        else:
            print(f"❌ Connection failed. Reason: {reason}")
            self.api = None

    def _fetch_candles(self, pair, timeframe, count):
        """
        ฟังก์ชันภายในสำหรับดึงข้อมูลแท่งเทียน (Candles)
        """
        if not self.api:
            return None
            
        print(f"🕯️  Fetching {count} candles for {pair} on {timeframe}s timeframe...")
        self.api.start_candles_stream(pair, timeframe, count)
        time.sleep(3) # รอให้ API ดึงข้อมูลเสร็จ
        candles = self.api.get_realtime_candles(pair, timeframe)
        self.api.stop_candles_stream(pair, timeframe)
        
        # แปลงข้อมูลเป็น List of Dictionaries ที่ใช้งานง่าย
        candle_list = []
        for timestamp in candles:
            candle_data = candles[timestamp]
            # ไม่เอาข้อมูลที่ไม่สมบูรณ์และทำการแปลงชื่อ Key
            if 'open' in candle_data and candle_data.get('open') is not None:
                standardized_candle = {
                    'open': candle_data.get('open'),
                    'high': candle_data.get('max'),
                    'low': candle_data.get('min'),
                    'close': candle_data.get('close'),
                    'volume': candle_data.get('volume')
                }
                candle_list.append(standardized_candle)
        
        print(f"📊 Found {len(candle_list)} candles.")
        return candle_list
    def _calculate_indicators(self, candles):
        """
        ฟังก์ชันภายในสำหรับคำนวณ Indicators ด้วย Pandas
        """
        if not candles or len(candles) < 50: # ต้องการข้อมูลอย่างน้อย 50 แท่งเพื่อคำนวณ EMA50
            print("⚠️ Not enough data to calculate indicators.")
            return None

        # แปลงเป็น DataFrame ของ Pandas
        df = pd.DataFrame(candles)
        
        # ใช้ pandas-ta ในการคำนวณ (ง่ายและเร็วมาก)
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)
        df.ta.rsi(length=14, append=True)
        
        # ดึงค่าล่าสุดออกมา
        latest = df.iloc[-1]
        return {
            "ohlc": df[['open', 'high', 'low', 'close']].tail(5).to_json(orient='records'),
            "ema20": f"{latest['EMA_20']:.5f}" if 'EMA_20' in latest else "N/A",
            "ema50": f"{latest['EMA_50']:.5f}" if 'EMA_50' in latest else "N/A",
            "rsi": f"{latest['RSI_14']:.2f}" if 'RSI_14' in latest else "N/A",
        }

    def get_technical_data(self, pair):
        """
        ฟังก์ชันหลักที่เรียกใช้จากภายนอก เพื่อรวบรวมข้อมูลทั้งหมด
        """
        if not self.api:
            return None # หากเชื่อมต่อไม่สำเร็จ ให้คืนค่า None

        # แปลงชื่อคู่เงินให้เป็นรูปแบบที่ API ต้องการ (เช่น EUR/USD -> EURUSD)
        api_pair_name = pair.replace("/", "")
        
        # Timeframe ใน IQ Option ใช้หน่วยเป็นวินาที (H1=3600, M15=900)
        
        # 1. ดึงข้อมูล H1 และคำนวณ
        h1_candles = self._fetch_candles(api_pair_name, 3600, 100) # ดึง 100 แท่ง
        h1_data = self._calculate_indicators(h1_candles)
        
        # 2. ดึงข้อมูล M15 และคำนวณ
        m15_candles = self._fetch_candles(api_pair_name, 900, 100) # ดึง 100 แท่ง
        m15_data = self._calculate_indicators(m15_candles)

        if not h1_data or not m15_data:
            print(f"❌ Could not retrieve full technical data for {pair}.")
            return None
        
        # 3. ประกอบร่างข้อมูลทั้งหมดเพื่อส่งคืน
        return {
            "h1_ohlc": h1_data['ohlc'],
            "h1_ema20": h1_data['ema20'],
            "h1_ema50": h1_data['ema50'],
            "h1_rsi": h1_data['rsi'],
            "m15_ohlc": m15_data['ohlc'],
            "m15_rsi": m15_data['rsi'],
        }

    def close_connection(self):
        """
        ปิดการเชื่อมต่อ API อย่างชัดเจน
        """
        if self.api:
            print("🔌 Logging out and closing connection...")
            self.api.logout()