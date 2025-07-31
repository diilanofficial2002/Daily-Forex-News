import requests

class TyphoonForexAnalyzer:
    def __init__(self, api_key, model="typhoon-v2.1-12b-instruct", base_url="https://api.opentyphoon.ai/v1"):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.endpoint = f"{self.base_url}/chat/completions"

    def build_prompt(self, analysis_text):
        return f"""
    You must return only the following structured format without any additional explanation or commentary.
    - Use 1 pip = 0.01 for JPY pairs.
    - Calculate pip distance from entry point (use nearest support for bullish, nearest resistance for bearish).
    - If multiple take-profit targets are given, include them all as TP1, TP2, etc.

    Use the following format only:

    **Currency:**  
    **Support Zones:**  
    **Resistance Zones:**  

    **Today order:**  
    [Order type]:[price level]
    - TP1: (price and pip difference from order)  
    - TP2: (price and pip difference from order, if available)  
    - SL: (price and pip difference from order)  

    ...

    Here is the analysis:
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
