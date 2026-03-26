import json
import requests
import subprocess
import os
import re
import keyring
import datetime
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# If modifying these scopes, delete the token from Keychain.
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "github_bot_config.json")
SERVICE_NAME = "github-morning-bot"

def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def get_google_creds():
    """Retrieves Google Calendar credentials from Keychain or local file."""
    # 1. Try to get the OAuth Token from Keychain
    token_json = keyring.get_password(SERVICE_NAME, "google_oauth_token")
    creds = None
    if token_json:
        creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)

    # 2. Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        keyring.set_password(SERVICE_NAME, "google_oauth_token", creds.to_json())

    # 3. If no valid creds, start the flow
    if not creds or not creds.valid:
        # Check if we have client secrets in Keychain
        client_id = keyring.get_password(SERVICE_NAME, "google_client_id")
        client_secret = keyring.get_password(SERVICE_NAME, "google_client_secret")
        
        if client_id and client_secret:
            client_config = {
                "installed": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token"
                }
            }
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        else:
            # Fallback to credentials.json if it exists (for initial setup)
            credentials_path = os.path.expanduser("~/Documents/github-morning-bot/credentials.json")
            if not os.path.exists(credentials_path):
                print("Missing Google credentials in Keychain or credentials.json. Skipping calendar.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            
            # Optional: Migrate secrets to Keychain
            with open(credentials_path, 'r') as f:
                secrets = json.load(f).get('installed', {})
                if secrets:
                    keyring.set_password(SERVICE_NAME, "google_client_id", secrets['client_id'])
                    keyring.set_password(SERVICE_NAME, "google_client_secret", secrets['client_secret'])

        creds = flow.run_local_server(port=0)
        # Store the new token in Keychain
        keyring.set_password(SERVICE_NAME, "google_oauth_token", creds.to_json())
    
    return creds

def fetch_calendar_events():
    """Fetches today's events from Google Calendar using Keychain creds."""
    creds = get_google_creds()
    if not creds: return []

    service = build('calendar', 'v3', credentials=creds)
    now = datetime.datetime.utcnow().isoformat() + 'Z'
    end_of_day = (datetime.datetime.utcnow().replace(hour=23, minute=59, second=59)).isoformat() + 'Z'
    
    try:
        events_result = service.events().list(calendarId='primary', timeMin=now,
                                            timeMax=end_of_day, singleEvents=True,
                                            orderBy='startTime').execute()
        return events_result.get('items', [])
    except Exception as e:
        print(f"Calendar API error: {e}")
        return []

def fetch_github_data_via_gh(username):
    """Uses the GitHub CLI (gh) to fetch data."""
    gh_path = "/opt/homebrew/bin/gh"
    def run_gh_search(query):
        try:
            cmd = [gh_path, "search", "issues", "--json", "title,url", "--limit", "10"] + query.split()
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return json.loads(result.stdout)
            return []
        except Exception:
            return []

    return {
        "mentions": run_gh_search(f"mentions:{username} is:open"),
        "review_requested": run_gh_search(f"review-requested:{username} is:pr is:open")
    }

def summarize_with_lm_studio(github_data, calendar_data, base_url):
    prompt = "Summarize my day. First, list my upcoming Google Calendar events for today. Then, summarize my GitHub activity (mentions and PRs). Keep it concise and prioritize things I need to act on. Format as a short bulleted list. IMPORTANT: For each GitHub item you list, YOU MUST include its corresponding URL. DO NOT include any follow-up questions or offers for further assistance.\n\n"
    
    prompt += "CALENDAR EVENTS TODAY:\n"
    if calendar_data:
        for event in calendar_data:
            start = event['start'].get('dateTime', event['start'].get('date'))
            # Format time for readability if it exists
            time_str = start
            if 'T' in start:
                time_obj = datetime.datetime.fromisoformat(start.replace('Z', '+00:00'))
                time_str = time_obj.strftime("%H:%M")
            prompt += f"- {event['summary']} (at {time_str})\n"
    else:
        prompt += "- No events scheduled for today.\n"

    prompt += "\nGITHUB ACTIVITY:\n"
    has_github = False
    if github_data["mentions"]:
        has_github = True
        prompt += "Mentions:\n"
        for item in github_data["mentions"]:
            prompt += f"- {item['title']} (URL: {item['url']})\n"
            
    if github_data["review_requested"]:
        has_github = True
        prompt += "\nReview Requests:\n"
        for item in github_data["review_requested"]:
            prompt += f"- {item['title']} (URL: {item['url']})\n"
            
    if not has_github and not calendar_data:
        return "Nothing much going on today! Enjoy your morning."

    payload = {
        "model": "model-identifier",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that summarizes a senior engineer's day (Calendar & GitHub)."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }
    
    try:
        response = requests.post(f"{base_url}/chat/completions", json=payload)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        return f"Error from LM Studio: {response.status_code}"
    except Exception as e:
        return f"Could not connect to LM Studio: {e}"

def send_telegram_message(summary, bot_token, chat_id):
    if not bot_token: return
    html_summary = summary.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html_summary = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', html_summary)
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": f"☀️ <b>Morning Daily Update</b>\n\n{html_summary}",
        "parse_mode": "HTML"
    }
    requests.post(url, json=payload)

def send_macos_notification(summary):
    short_summary = (summary[:200] + '...') if len(summary) > 200 else summary
    apple_script = f'display notification "{short_summary}" with title "Morning Daily Update"'
    subprocess.run(["osascript", "-e", apple_script])

def main():
    try:
        config = load_config()
        if config.get("use_keychain"):
            telegram_bot_token = keyring.get_password(SERVICE_NAME, "telegram_bot_token")
            telegram_chat_id = keyring.get_password(SERVICE_NAME, "telegram_chat_id")
        else:
            telegram_bot_token = config.get("telegram_bot_token")
            telegram_chat_id = config.get("telegram_chat_id")

        calendar_data = fetch_calendar_events()
        github_data = fetch_github_data_via_gh(config["github_username"])
        summary = summarize_with_lm_studio(github_data, calendar_data, config["lm_studio_base_url"])
        
        send_macos_notification(summary)
        send_telegram_message(summary, telegram_bot_token, telegram_chat_id)
        print("Success! Morning update sent (Keychain secured).")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
