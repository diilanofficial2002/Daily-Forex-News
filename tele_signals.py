import requests

class TyphoonForexAnalyzer:
    def __init__(self, api_key, model="typhoon-v2.1-12b-instruct", base_url="https://api.opentyphoon.ai/v1"):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.endpoint = f"{self.base_url}/chat/completions"

    def build_prompt(self, analysis_text):
        return f"""
        Extract the essential intraday trading plan from the following analysis. Focus on actionable information only.

        **ANALYSIS TO PROCESS:**
        {analysis_text}

        **REQUIRED OUTPUT FORMAT (STRICT ADHERENCE):**

        **PAIR:** [Currency Pair]
        **DATE:** [Trading Date]  
        **BIAS:** [Bullish/Bearish/Neutral/Range-bound] - [Ultra-brief rationale]

        **KEY ZONES:**
        **SUPPORTS:** [Zone 1: Price-Source] | [Zone 2: Price-Source] (if applicable)
        **RESISTANCES:** [Zone 1: Price-Source] | [Zone 2: Price-Source] (if applicable)

        **SETUPS (SAME-DAY CLOSE):**
        🐂 **LONG SETUP:**
        **ENTRY:** [Precise conditions - max 25 words]
        **TP:** [Target zone with brief rationale - max 15 words]  
        **SL:** [Stop zone with brief rationale - max 15 words]

        🐻 **SHORT SETUP:**
        **ENTRY:** [Precise conditions - max 25 words]
        **TP:** [Target zone with brief rationale - max 15 words]
        **SL:** [Stop zone with brief rationale - max 15 words]  

        **RISK ALERTS:** [Critical timing/volatility warnings - max 30 words total, or "None"]

        **INSTRUCTIONS:**
        - Preserve exact price levels and technical conditions
        - Eliminate all unnecessary words while maintaining meaning
        - If any section lacks clear information in the analysis, state "Insufficient data"
        - Prioritize actionability over explanation
        """
    
    def system_prompter(self):
        return """
        You are a precision formatter specializing in extracting essential trading information from comprehensive market analysis. Your task is to distill complex analysis into ultra-concise, actionable trading plans while preserving all critical decision-making information.

        **Key Requirements:**
        - Extract ONLY essential information needed for trading decisions
        - Maintain precision in price levels and conditions
        - Preserve logical rationale in condensed form
        - Ensure output is immediately actionable for traders
        - Eliminate redundancy and filler language
        """

    def analyze(self, analysis_text, max_tokens=2048, temperature=0.3):
        prompt = self.build_prompt(analysis_text)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompter()}, 
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