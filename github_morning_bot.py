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
SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/gmail.readonly'
]
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "github_bot_config.json")
SERVICE_NAME = "github-morning-bot"

def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def get_google_creds():
    """Retrieves Google Calendar and Gmail credentials from Keychain or local file."""
    # 1. Try to get the OAuth Token from Keychain
    token_json = keyring.get_password(SERVICE_NAME, "google_oauth_token")
    creds = None
    if token_json:
        print("Loading credentials from Keychain...")
        creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)

    # 2. Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            print("Refreshing expired credentials...")
            creds.refresh(Request())
            keyring.set_password(SERVICE_NAME, "google_oauth_token", creds.to_json())
        except Exception as e:
            print(f"Error refreshing credentials: {e}")
            creds = None

    # 3. If no valid creds, start the flow
    if not creds or not creds.valid:
        # If we are in a non-interactive shell (like launchd), do not try to start a local server
        import sys
        if not sys.stdin.isatty():
            print("Non-interactive session detected. Cannot start OAuth flow for Google services.")
            return None

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
            credentials_path = os.path.join(SCRIPT_DIR, "credentials.json")
            if not os.path.exists(credentials_path):
                print("Missing Google credentials in Keychain or credentials.json. Skipping Google services.")
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
    """Fetches today's events from Google Calendar."""
    creds = get_google_creds()
    if not creds: return []

    service = build('calendar', 'v3', credentials=creds)
    # Use local time with timezone awareness
    now_local = datetime.datetime.now().astimezone()
    now = now_local.isoformat()
    end_of_day = now_local.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()
    
    try:
        events_result = service.events().list(calendarId='primary', timeMin=now,
                                            timeMax=end_of_day, singleEvents=True,
                                            orderBy='startTime').execute()
        return events_result.get('items', [])
    except Exception as e:
        print(f"Calendar API error: {e}")
        return []

def fetch_unread_emails():
    """Fetches unread emails from Gmail."""
    creds = get_google_creds()
    if not creds: return []

    service = build('gmail', 'v1', credentials=creds)
    try:
        results = service.users().messages().list(userId='me', q='is:unread', maxResults=10).execute()
        messages = results.get('messages', [])
        
        email_summaries = []
        for msg in messages:
            msg_data = service.users().messages().get(userId='me', id=msg['id'], format='metadata', metadataHeaders=['From', 'Subject']).execute()
            headers = msg_data.get('payload', {}).get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(No Subject)')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), '(Unknown Sender)')
            email_summaries.append({"sender": sender, "subject": subject})
        return email_summaries
    except Exception as e:
        print(f"Gmail API error: {e}")
        return []

def fetch_macos_notes_todos(note_name):
    """Fetches TODO items from a specific macOS Note."""
    apple_script = f'tell application "Notes" to get body of note "{note_name}"'
    try:
        result = subprocess.run(["osascript", "-e", apple_script], capture_output=True, text=True)
        if result.returncode != 0:
            return []
        
        body = result.stdout
        # Basic extraction of <li> items from HTML-like body
        todos = re.findall(r'<li>(.*?)</li>', body)
        # Clean up any other HTML tags inside <li>
        todos = [re.sub(r'<.*?>', '', t).strip() for t in todos]
        return todos
    except Exception as e:
        print(f"macOS Notes error: {e}")
        return []

def summarize_with_lm_studio(calendar_data, email_data, todo_data, base_url):
    prompt = "Summarize my day. First, list my upcoming Google Calendar events for today. Then, list my TODOs from my notes. Finally, list my recent unread emails. Keep it concise and prioritize things I need to act on. Format as a short bulleted list. DO NOT include any follow-up questions or offers for further assistance.\n\n"
    
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

    prompt += "\nTODOS FROM NOTES:\n"
    if todo_data:
        for todo in todo_data:
            prompt += f"- {todo}\n"
    else:
        prompt += "- No TODOs found.\n"

    prompt += "\nUNREAD EMAILS:\n"
    if email_data:
        for email in email_data:
            prompt += f"- From: {email['sender']} | Subject: {email['subject']}\n"
    else:
        prompt += "- No unread emails.\n"

    if not calendar_data and not email_data and not todo_data:
        return "Nothing much going on today! Enjoy your morning."

    payload = {
        "model": "google/gemma-4-26b-a4b",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that summarizes a senior engineer's day (Calendar, Notes & Emails)."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        # Gemma 4 thinks before answering by default: ~1,400 reasoning tokens took over 6 minutes
        # on the Mac mini (timeouts from 2026-11-03); without it the summary takes under a minute
        "reasoning_effort": "none"
    }
    
    try:
        # A cold start loads the 26B model (~45 s), reads the prompt (~25 s with many emails) and
        # writes ~250 tokens at ~6/s: about 2 minutes, so 90 s cut the summary off (2026-11-06)
        response = requests.post(f"{base_url}/chat/completions", json=payload, timeout=300)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        
        error_msg = f"Error from LM Studio: {response.status_code}"
        try:
            error_detail = response.json()
            error_msg += f" - {json.dumps(error_detail)}"
        except:
            error_msg += f" - {response.text}"
            
        print(error_msg)
        return error_msg
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
    try:
        requests.post(url, json=payload, timeout=30)
    except requests.RequestException as e:
        # requests puts the full URL, token included, in its errors; never print it
        raise type(e)(str(e).replace(bot_token, "<telegram-token>")) from None

def send_macos_notification(summary):
    short_summary = (summary[:200] + '...') if len(summary) > 200 else summary
    apple_script = f'display notification "{short_summary}" with title "Morning Daily Update"'
    subprocess.run(["osascript", "-e", apple_script])

def push_kuma(ok, msg):
    """Heartbeat to the "Morning bot" push monitor in Uptime Kuma (portfolio-dashboard), which
    alerts on Telegram on a degraded run or when none reports for 25 hours. Best effort."""
    try:
        token = subprocess.run(["security", "find-generic-password", "-s", "uptime-kuma-push-morningbot", "-w"],
                               capture_output=True, text=True, timeout=10).stdout.strip()
        if token:
            requests.get(f"http://127.0.0.1:3001/api/push/{token}",
                         params={"status": "up" if ok else "down", "msg": msg[:200]}, timeout=10)
    except Exception:
        pass

def main():
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now_str}] Bot started...")
    try:
        config = load_config()
        if config.get("use_keychain"):
            telegram_bot_token = keyring.get_password(SERVICE_NAME, "telegram_bot_token")
            telegram_chat_id = keyring.get_password(SERVICE_NAME, "telegram_chat_id")
        else:
            telegram_bot_token = config.get("telegram_bot_token")
            telegram_chat_id = config.get("telegram_chat_id")

        calendar_data = fetch_calendar_events()
        email_data = fetch_unread_emails()
        todo_data = fetch_macos_notes_todos("TODO")
        summary = summarize_with_lm_studio(calendar_data, email_data, todo_data, config["lm_studio_base_url"])
        
        send_macos_notification(summary)
        send_telegram_message(summary, telegram_bot_token, telegram_chat_id)
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{now_str}] Success! Morning update sent (Keychain secured).")
        problems = []
        if get_google_creds() is None:
            problems.append("Google login expired: run github_morning_bot.py in a terminal")
        if "LM Studio was unavailable" in summary or summary.startswith("Error"):
            problems.append("LM Studio did not summarize")
        push_kuma(not problems, "; ".join(problems) or "sent")
    except Exception as e:
        print(f"Error: {e}")
        push_kuma(False, f"{type(e).__name__}: {e}")

if __name__ == "__main__":
    main()
