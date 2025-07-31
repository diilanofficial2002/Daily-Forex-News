import requests

class TyphoonForexAnalyzer:
    def __init__(self, api_key, model="typhoon-v2.1-12b-instruct", base_url="https://api.opentyphoon.ai/v1"):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.endpoint = f"{self.base_url}/chat/completions"

    def build_prompt(self, analysis_text):
        return f"""
        You must extract only the trading plan details from the provided analysis and structure them precisely as specified below. Do not include any additional commentary, explanations, or introductory/concluding remarks.
    
        **Pip Calculation Rules:**
        - For JPY pairs (e.g., USD/JPY, EUR/JPY), 1 pip = 0.01.
        - For all other pairs (e.g., EUR/USD, GBP/USD), 1 pip = 0.0001.
        - All pip differences must be calculated as the **absolute difference from the identified Entry Price**.
    
        **Output Format (Strictly Adhere):**
    
        **Currency:** [Currency Pair, e.g., EUR/USD]
    
        **Primary Trading Plan:**
        [Order Type, e.g., BUY or SELL]: [Entry Price Level, e.g., 1.07540]
        - TP1: [Target Price Level, e.g., 1.07680] ([Absolute Pip Difference from Entry, e.g., +14 pips])
        - TP2: [Target Price Level, e.g., 1.07750] ([Absolute Pip Difference from Entry, e.g., +21 pips]) (If available, otherwise omit)
        - SL: [Stop Loss Price Level, e.g., 1.07450] ([Absolute Pip Difference from Entry, e.g., -9 pips])
    
        **Secondary Trading Plan (Optional):**
        [Order Type, e.g., SELL or BUY]: [Entry Price Level, e.g., 1.07300]
        - TP1: [Target Price Level, e.g., 1.07100] ([Absolute Pip Difference from Entry, e.g., -20 pips])
        - SL: [Stop Loss Price Level, e.g., 1.07400] ([Absolute Pip Difference from Entry, e.g., +10 pips])
        (If no secondary plan or "No Trade" is recommended in the analysis, this section should be omitted entirely or stated as "No secondary plan available.")
    
        Here is the analysis to extract data from:
        {analysis_text}
        """

    def analyze(self, analysis_text, max_tokens=3072, temperature=0.3):
        prompt = self.build_prompt(analysis_text)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a formatter assistant. Never include any sentence outside the structure."},
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
