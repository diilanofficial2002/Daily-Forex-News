# ForexFactory News Scraper

Automated scraper for ForexFactory economic news with AI analysis and Telegram notifications.

## 🚀 Features

- **Automated Scraping**: Scrapes ForexFactory economic calendar daily
- **AI Analysis**: Uses Typhoon AI to analyze economic events impact
- **Telegram Notifications**: Sends analyzed news to Telegram channel
- **Robust Error Handling**: Multiple fallback methods and retry logic
- **GitHub Actions**: Fully automated with scheduled runs

## 📋 Requirements

- Python 3.9+
- Playwright (for web scraping)
- BeautifulSoup4 (HTML parsing)
- OpenAI SDK (for Typhoon AI API)
- Telegram Bot Token
- Typhoon AI API Key

## 🔧 Setup Instructions

### 1. Local Setup

```bash
# Clone repository
git clone <your-repo-url>
cd forexfactory-scraper

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Create .env file
cp .env.example .env
# Edit .env with your credentials
```

### 2. Environment Variables

Create a `.env` file with:

```env
BOT_TOKEN=your_telegram_bot_token
CHAT_ID=your_telegram_chat_id
TYPHOON_API_KEY=your_typhoon_api_key
```

### 3. GitHub Actions Setup

#### Required Secrets

Add these secrets to your GitHub repository:

1. Go to **Settings** → **Secrets and variables** → **Actions**
2. Add the following secrets:
   - `BOT_TOKEN`: Your Telegram bot token
   - `CHAT_ID`: Your Telegram chat ID  
   - `TYPHOON_API_KEY`: Your Typhoon AI API key

#### Getting Telegram Credentials

1. **Create Telegram Bot**:
   - Message [@BotFather](https://t.me/BotFather) on Telegram
   - Send `/newbot` and follow instructions
   - Save the bot token

2. **Get Chat ID**:
   - Add your bot to a channel or group
   - Send a message to the channel/group
   - Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   - Find your chat ID in the response

#### Getting Typhoon AI API Key

1. Visit [OpenTyphoon.ai](https://opentyphoon.ai/)
2. Sign up for an account
3. Generate an API key
4. Copy the key for use in the environment variables

### 4. Workflow Schedule

The scraper runs automatically at:

- 8:00 AM Thailand time (01:00 UTC)
- 12:00 PM Thailand time (05:00 UTC)
- 4:00 PM Thailand time (09:00 UTC)
- 8:00 PM Thailand time (13:00 UTC)

### 5. Manual Trigger

You can manually trigger the workflow:

1. Go to **Actions** tab in GitHub
2. Select **ForexFactory News Scraper**
3. Click **Run workflow**
4. Optionally enable debug mode

## 🔍 Troubleshooting

### Common Issues

1. **Playwright timeout**:
   - GitHub Actions has slower network
   - Script includes extended timeouts and retries

2. **Cloudflare blocking**:
   - Script includes anti-detection measures
   - Falls back to requests method if Playwright fails

3. **Missing dependencies**:
   - All system dependencies are installed in workflow
   - Fonts and display drivers included

### Debug Mode

Run with debug mode enabled:

```bash
python forex_daily_news.py --debug
```

### Logs

Check GitHub Actions logs:

- Failed runs upload artifacts with detailed logs
- Telegram notifications sent on success/failure

## 📊 Monitoring

The workflow includes:

- **Health checks**: Verifies API endpoints before scraping
- **Success notifications**: Confirms successful completion
- **Failure notifications**: Alerts when scraping fails
- **Artifact uploads**: Saves logs for debugging failed runs

## 🛡️ Security

- All sensitive data stored as GitHub Secrets
- No credentials exposed in code or logs
- Environment variables properly isolated
- Timeout limits prevent runaway processes

## 📈 Customization

### Modify Schedule

Edit the `cron` expressions in `.github/workflows/scraper.yml`:

```yaml
schedule:
  - cron: '0 1 * * *'    # Your desired time in UTC
```

### Change Analysis Prompt

Modify the `SYSTEM_PROMPT` in `forex_daily_news.py` to customize AI analysis.

### Add More Currencies

Update the analysis prompt to include additional currencies beyond EUR, USD, GBP, CHF, JPY.

## 📝 File Structure

```
├── .github/
│   └── workflows/
│       └── scraper.yml          # GitHub Actions workflow
├── forex_daily_news.py          # Main scraper script
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment variables template
└── README.md                    # This file
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test locally
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

## ⚠️ Disclaimer

This tool is for educational and informational purposes only. Always verify economic data from official sources before making trading decisions.
