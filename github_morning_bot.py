import json
import requests
import subprocess
import os
import re
import keyring

CONFIG_PATH = os.path.expanduser("~/Documents/github-morning-bot/github_bot_config.json")

def escape_markdown_v2(text):
    """Escapes special characters for Telegram's MarkdownV2 format."""
    # Characters that need escaping in MarkdownV2
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def fetch_github_data_via_gh(username):
    """Uses the GitHub CLI (gh) to fetch data without needing a manual token."""
    
    def run_gh_search(query):
        try:
            cmd = ["gh", "search", "issues", "--json", "title,url", "--limit", "10"] + query.split()
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return json.loads(result.stdout)
            else:
                print(f"Error running gh search: {result.stderr}")
                return []
        except Exception as e:
            print(f"GH CLI error: {e}")
            return []

    return {
        "mentions": run_gh_search(f"mentions:{username} is:open"),
        "review_requested": run_gh_search(f"review-requested:{username} is:pr is:open")
    }

def summarize_with_lm_studio(data, base_url):
    prompt = "Summarize the following GitHub activity for me. Keep it concise and prioritize things I need to act on. Format as a short bulleted list. IMPORTANT: For each item you list, YOU MUST include its corresponding GitHub URL at the end of the bullet point.\n\n"
    
    has_activity = False
    if data["mentions"]:
        has_activity = True
        prompt += "Mentions:\n"
        for item in data["mentions"]:
            prompt += f"- {item['title']} (URL: {item['url']})\n"
            
    if data["review_requested"]:
        has_activity = True
        prompt += "\nReview Requests:\n"
        for item in data["review_requested"]:
            prompt += f"- {item['title']} (URL: {item['url']})\n"
            
    if not has_activity:
        return "No urgent GitHub activity found for this morning."

    payload = {
        "model": "model-identifier",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that summarizes GitHub notifications for a senior engineer."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }
    
    try:
        response = requests.post(f"{base_url}/chat/completions", json=payload)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            return f"Error from LM Studio: {response.status_code}"
    except Exception as e:
        return f"Could not connect to LM Studio: {e}"

def send_telegram_message(summary, bot_token, chat_id):
    if not bot_token or bot_token == "YOUR_TELEGRAM_BOT_TOKEN":
        print("Telegram bot token not configured.")
        return

    # Use HTML mode for much better reliability than Markdown
    html_summary = summary.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Properly replace markdown bold **text** with <b>text</b> using regex
    html_summary = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', html_summary)
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": f"🚀 <b>GitHub Morning Update</b>\n\n{html_summary}",
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            print(f"Telegram HTML failed ({response.status_code}): {response.text}")
            print("Retrying as plain text...")
            payload.pop("parse_mode")
            payload["text"] = f"🚀 GitHub Morning Update\n\n{summary}"
            second_attempt = requests.post(url, json=payload)
            if second_attempt.status_code == 200:
                print("Telegram message sent as plain text.")
            else:
                print(f"Telegram failed completely: {second_attempt.text}")
        else:
            print("Telegram message sent successfully with HTML formatting!")
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

def send_macos_notification(summary):
    short_summary = (summary[:200] + '...') if len(summary) > 200 else summary
    apple_script = f'display notification "{short_summary}" with title "GitHub Morning Update"'
    subprocess.run(["osascript", "-e", apple_script])

def main():
    try:
        config = load_config()
        
        # Fetch secrets from Keychain if enabled
        if config.get("use_keychain"):
            telegram_bot_token = keyring.get_password("github-morning-bot", "telegram_bot_token")
            telegram_chat_id = keyring.get_password("github-morning-bot", "telegram_chat_id")
        else:
            telegram_bot_token = config.get("telegram_bot_token")
            telegram_chat_id = config.get("telegram_chat_id")

        # Use GH CLI
        data = fetch_github_data_via_gh(config["github_username"])
        
        # Summarize with LM Studio
        summary = summarize_with_lm_studio(data, config["lm_studio_base_url"])
        
        # Send notifications
        send_macos_notification(summary)
        send_telegram_message(summary, telegram_bot_token, telegram_chat_id)
        
        print("Done! Check your Telegram and macOS notifications.")
        
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
