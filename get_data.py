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
        # ต้องการข้อมูลอย่างน้อย 50 แท่งสำหรับ EMA50, 14 แท่งสำหรับ RSI, และอย่างน้อย 26 แท่งสำหรับ MACD (ค่าเริ่มต้น)
        if not candles or len(candles) < 26: # ใช้ 26 เป็นขั้นต่ำสุดสำหรับ MACD
            print("⚠️ Not enough data to calculate indicators. Minimum 26 candles required for MACD.")
            return {
                "ohlc": pd.DataFrame(candles)[['open', 'high', 'low', 'close', 'volume']].tail(5).to_json(orient='records') if candles else "[]",
                "ema20": "N/A",
                "ema50": "N/A",
                "rsi": "N/A",
                "macd": "N/A",
                "macdh": "N/A",
                "macds": "N/A",
            }

        # แปลงเป็น DataFrame ของ Pandas
        df = pd.DataFrame(candles)
        
        # ใช้ pandas-ta ในการคำนวณ (ง่ายและเร็วมาก)
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)
        df.ta.rsi(length=14, append=True)
        df.ta.macd(append=True) # คำนวณ MACD ด้วยค่าเริ่มต้น (12, 26, 9)

        # ดึงค่าล่าสุดออกมา
        latest = df.iloc[-1]
        
        return {
            "ohlc": df[['open', 'high', 'low', 'close', 'volume']].tail(5).to_json(orient='records'), # เพิ่ม volume
            "ema20": f"{latest['EMA_20']:.5f}" if 'EMA_20' in latest and pd.notna(latest['EMA_20']) else "N/A",
            "ema50": f"{latest['EMA_50']:.5f}" if 'EMA_50' in latest and pd.notna(latest['EMA_50']) else "N/A",
            "rsi": f"{latest['RSI_14']:.2f}" if 'RSI_14' in latest and pd.notna(latest['RSI_14']) else "N/A",
            "macd": f"{latest['MACD_12_26_9']:.5f}" if 'MACD_12_26_9' in latest and pd.notna(latest['MACD_12_26_9']) else "N/A", # เพิ่ม MACD
            "macdh": f"{latest['MACDH_12_26_9']:.5f}" if 'MACDH_12_26_9' in latest and pd.notna(latest['MACDH_12_26_9']) else "N/A", # เพิ่ม MACD Histogram
            "macds": f"{latest['MACDS_12_26_9']:.5f}" if 'MACDS_12_26_9' in latest and pd.notna(latest['MACDS_12_26_9']) else "N/A", # เพิ่ม MACD Signal
        }

    def _calculate_pivot_points(self, high, low, close):
        """Calculates Standard Daily Pivot Points."""
        pp = (high + low + close) / 3
        r1 = (2 * pp) - low
        s1 = (2 * pp) - high
        r2 = pp + (high - low)
        s2 = pp - (high - low)
        r3 = high + 2 * (pp - low)
        s3 = low - 2 * (high - pp)
        return {
            "pp": f"{pp:.5f}", "r1": f"{r1:.5f}", "s1": f"{s1:.5f}",
            "r2": f"{r2:.5f}", "s2": f"{s2:.5f}", "r3": f"{r3:.5f}", "s3": f"{s3:.5f}"
        }

    def get_technical_data(self, pair):
        """
        ฟังก์ชันหลักที่เรียกใช้จากภายนอก เพื่อรวบรวมข้อมูลทั้งหมด
        """
        if not self.api:
            return None # หากเชื่อมต่อไม่สำเร็จ ให้คืนค่า None

        api_pair_name = pair.replace("/", "")
        
        # 1. ดึงข้อมูล H4 และคำนวณ
        h4_candles = self._fetch_candles(api_pair_name, 14400, 100) # ดึง 100 แท่ง
        h4_data = self._calculate_indicators(h4_candles)
        
        # 2. ดึงข้อมูล H1 และคำนวณ
        h1_candles = self._fetch_candles(api_pair_name, 3600, 100) # ดึง 100 แท่ง
        h1_data = self._calculate_indicators(h1_candles)

        # 3. ดึงข้อมูล M15 และคำนวณ
        m15_candles = self._fetch_candles(api_pair_name, 900, 100) # ดึง 100 แท่ง
        m15_data = self._calculate_indicators(m15_candles)
        
        # 4. ดึงข้อมูลแท่งเทียนรายวัน (D1) เพื่อหา Previous Day's High/Low/Close
        #    ต้องการอย่างน้อย 2 แท่ง เพื่อให้แน่ใจว่าได้แท่งที่สมบูรณ์ของวันก่อนหน้า
        d1_candles = self._fetch_candles(api_pair_name, 86400, 2) 
        prev_day_high = "N/A"
        prev_day_low = "N/A"
        prev_day_close = "N/A"
        daily_pivots = {
            "pp": "N/A", "r1": "N/A", "s1": "N/A",
            "r2": "N/A", "s2": "N/A", "r3": "N/A", "s3": "N/A"
        }

        if d1_candles and len(d1_candles) >= 2:
            # แท่งที่สองจากท้ายคือแท่งของวันก่อนหน้า
            prev_day_candle = d1_candles[-2] 
            prev_day_high = f"{prev_day_candle['high']:.5f}"
            prev_day_low = f"{prev_day_candle['low']:.5f}"
            prev_day_close = f"{prev_day_candle['close']:.5f}"
            
            # คำนวณ Pivot Points จากข้อมูลวันก่อนหน้า
            daily_pivots = self._calculate_pivot_points(
                prev_day_candle['high'], 
                prev_day_candle['low'], 
                prev_day_candle['close']
            )

        if not h1_data or not m15_data or not h4_data: # ตรวจสอบ m5_data ด้วย
            print(f"❌ Could not retrieve full technical data for {pair}.")
            return None
        
        # 5. ประกอบร่างข้อมูลทั้งหมดเพื่อส่งคืน
        return {
            "h4_ohlc": h4_data['ohlc'],
            "h4_ema20": h4_data['ema20'],
            "h4_ema50": h4_data['ema50'],
            "h4_rsi": h4_data['rsi'],
            "h4_macd": h4_data['macd'], # เพิ่มใหม่
            "h4_macdh": h4_data['macdh'], # เพิ่มใหม่
            "h4_macds": h4_data['macds'], # เพิ่มใหม่
            "prev_day_high": prev_day_high,
            "prev_day_low": prev_day_low,
            "prev_day_close": prev_day_close,
            "daily_pivot_pp": daily_pivots["pp"],
            "daily_pivot_r1": daily_pivots["r1"],
            "daily_pivot_r2": daily_pivots["r2"],
            "daily_pivot_r3": daily_pivots["r3"],
            "daily_pivot_s1": daily_pivots["s1"],
            "daily_pivot_s2": daily_pivots["s2"],
            "daily_pivot_s3": daily_pivots["s3"],
            "m15_ohlc": m15_data['ohlc'],
            "m15_ema20": m15_data['ema20'],
            "m15_ema50": m15_data['ema50'],
            "m15_rsi": m15_data['rsi'],
            "m15_macd": m15_data['macd'], # เพิ่มใหม่
            "m15_macdh": m15_data['macdh'], # เพิ่มใหม่
            "m15_macds": m15_data['macds'], # เพิ่มใหม่
            "h1_ohlc": h1_data['ohlc'],
            "h1_ema20": h1_data['ema20'],
            "h1_ema50": h1_data['ema50'],
            "h1_rsi": h1_data['rsi'],
            "h1_macd": h1_data['macd'], # เพิ่มใหม่
            "h1_macdh": h1_data['macdh'], # เพิ่มใหม่
            "h1_macds": h1_data['macds'], # เพิ่มใหม่
        }

    def close_connection(self):
        """
        ปิดการเชื่อมต่อ API อย่างชัดเจน
        """
        if self.api:
            print("🔌 Logging out and closing connection...")
            self.api.logout()