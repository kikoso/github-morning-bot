# GitHub Morning Bot 🚀

A Python-based bot that runs every morning on your Mac Mini to notify you of your latest GitHub activity, summarized by a local LLM via LM Studio.

## Features
- **GitHub CLI Integration**: Uses `gh` to fetch mentions and pending Pull Requests.
- **Google Calendar Integration**: Fetches your today's schedule for a holistic daily briefing.
- **Local AI Summarization**: Connects to **LM Studio** to provide a concise, prioritized summary of both tasks and schedule.
- **Dual Notifications**: macOS and Telegram.

## Setup

1. **Clone the repository**:
   ```bash
   git clone git@github.com:kikoso/github-morning-bot.git
   cd github-morning-bot
   ```

2. **Configure the bot**:
   - Create `github_bot_config.json` with your details.
   - For Google Calendar:
     1. Create a "Desktop app" project in [Google Cloud Console](https://console.cloud.google.com/).
     2. Enable **Google Calendar API**.
     3. Download the credentials as `credentials.json` into this folder.
     4. On first run, follow the browser login to create `token.pickle`.

3. **Install dependencies**:
   ```bash
   pip3 install requests google-api-python-client google-auth-httplib2 google-auth-oauthlib --user
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
