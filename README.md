# GitHub Morning Bot 🚀

A Python-based bot that runs every morning on your Mac Mini to notify you of your latest GitHub activity, summarized by a local LLM via LM Studio.

## Features
- **GitHub CLI Integration**: Uses `gh` to fetch mentions and pending Pull Requests without needing manual tokens.
- **Local AI Summarization**: Connects to **LM Studio** (OpenAI-compatible API) to provide a concise, prioritized summary.
- **Dual Notifications**:
  - Native macOS system notifications.
  - Telegram messages via a custom bot.
- **Automated Scheduling**: Runs daily at 9:00 AM using macOS `launchd`.

## Prerequisites
- **GitHub CLI**: `gh` must be installed and authenticated (`gh auth login`).
- **LM Studio**: Must be running with the Local Server enabled on port 1234.
- **Python 3**: With the `requests` library installed (`pip3 install requests`).

## Setup

1. **Clone the repository**:
   ```bash
   git clone git@github.com:kikoso/github-morning-bot.git
   cd github-morning-bot
   ```

2. **Configure the bot**:
   Create a `github_bot_config.json` in the same directory (this file is gitignored for security):
   ```json
   {
     "github_username": "YOUR_USERNAME",
     "lm_studio_base_url": "http://localhost:1234/v1",
     "telegram_bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
     "telegram_chat_id": "YOUR_TELEGRAM_CHAT_ID",
     "notification_time": "09:00"
   }
   ```

3. **Install dependencies**:
   ```bash
   pip3 install requests --user
   ```

## Scheduling (macOS)
To schedule the bot to run every morning at 9:00 AM:

1. Copy the `.plist` file to your LaunchAgents directory:
   ```bash
   cp ~/Documents/github-morning-bot/com.user.github_morning_bot.plist ~/Library/LaunchAgents/
   ```

2. Load the agent:
   ```bash
   launchctl load ~/Library/LaunchAgents/com.user.github_morning_bot.plist
   ```

## Manual Run
You can test the bot at any time by running:
```bash
/usr/bin/python3 ~/Documents/github-morning-bot/github_morning_bot.py
```

## Security
The `github_bot_config.json` file contains your private API tokens and is excluded from the repository via `.gitignore`. Never commit this file.
