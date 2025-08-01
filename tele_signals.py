import requests

class TyphoonForexAnalyzer:
    def __init__(self, api_key, model="typhoon-v2.1-12b-instruct", base_url="https://api.opentyphoon.ai/v1"):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.endpoint = f"{self.base_url}/chat/completions"

    def build_prompt(self, analysis_text):
        # Prompt นี้จะเน้นให้กระชับและตรงประเด็นมากขึ้น
        return f"""
        You are a highly concise formatter. Extract ONLY the essential intraday trading plan details from the provided analysis. Remove all unnecessary words, explanations, or filler phrases. Adhere strictly to the specified format below.

        **Output Format (Strictly Adhere - Minimize Text):**

        **PAIR:** [Currency Pair, e.g., EUR/USD]
        **BIAS:** [Overall Intraday Bias, e.g., Bullish / Bearish / Neutral / Range-bound]

        **KEY ZONES:**
        - **SUPPORTS:** [List 1-2 important price zones, e.g., 1.0700-1.0710 (Pivot)]
        - **RESISTANCES:** [List 1-2 important price zones, e.g., 1.0800-1.0810 (Daily R1)]

        **TRADING SETUPS (Same-Day Close):**

        🐂 **BULLISH:**
        - **ENTRY:** [Specific conditions for LONG entry, CONCISE. e.g., "Price rejects 1.0700-1.0710 (Support) with M5/M15 bullish engulfing candle & RSI confirms momentum, MACD crossover/divergence, or increasing volume."]
        - **TP:** [Logical Profit Target Area, CONCISE. e.g., "Towards 1.0750-1.0760 (Resistance/R1)."]
        - **SL:** [Logical Stop Loss Area, CONCISE. e.g., "Below 1.0690 (Invalidates setup)."]

        🐻 **BEARISH:**
        - **ENTRY:** [Specific conditions for SHORT entry, CONCISE. e.g., "Price tests 1.0800-1.0810 (Resistance) with M5/M15 bearish rejection, RSI overbought/turning down, MACD crossover/divergence, or increasing volume."]
        - **TP:** [Logical Profit Target Area, CONCISE. e.g., "Towards 1.0750-1.0740 (Support/S1)."]
        - **SL:** [Logical Stop Loss Area, CONCISE. e.g., "Above 1.0820 (Invalidates setup)."]

        **CONSIDERATIONS:** [1-2 critical points for the day, CONCISE. e.g., "Expect volatility around [Time of News Event] - adjust size or avoid." If no specific considerations, state "None.""]

        Here is the analysis to extract data from:
        {analysis_text}
        """

    def analyze(self, analysis_text, max_tokens=3072, temperature=0.3):
        prompt = self.build_prompt(analysis_text)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a formatter assistant. Never include any sentence outside the structure and be extremely concise."}, # เพิ่มคำสั่งให้กระชับมากยิ่งขึ้นใน system role
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        response = requests.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload
        )
        response.raise_for_status()
        resp_json = response.json()
        return resp_json["choices"][0]["message"]["content"]

class TelegramNotifier:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send_message(self, message, parse_mode="Markdown"):
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        resp = requests.post(url, data={
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": parse_mode
        })
        resp.raise_for_status()
        return resp.json()

class ForexBot:
    def __init__(self, analyzer: TyphoonForexAnalyzer, notifier: TelegramNotifier):
        self.analyzer = analyzer
        self.notifier = notifier

    def send(self, raw_analysis_text):
        try:
            summary = self.analyzer.analyze(raw_analysis_text)
            self.notifier.send_message(summary)
            print("✅ Summary sent to Telegram!")
        except requests.HTTPError as http_err:
            print("❌ HTTP error during API call:", http_err)
            print("Response content:", http_err.response.text)
        except Exception as e:
            print("❌ Unexpected error:", e)