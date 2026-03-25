import json
import requests
import subprocess
import os

CONFIG_PATH = os.path.expanduser("~/Documents/github-morning-bot/github_bot_config.json")

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
    prompt = "Summarize the following GitHub activity for me. Keep it concise and prioritize things I need to act on. Format as a short bulleted list.\n\n"
    
    has_activity = False
    if data["mentions"]:
        has_activity = True
        prompt += "Mentions:\n"
        for item in data["mentions"]:
            prompt += f"- {item['title']} ({item['url']})\n"
            
    if data["review_requested"]:
        has_activity = True
        prompt += "\nReview Requests:\n"
        for item in data["review_requested"]:
            prompt += f"- {item['title']} ({item['url']})\n"
            
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
    if bot_token == "YOUR_TELEGRAM_BOT_TOKEN":
        print("Telegram bot token not configured.")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": f"🚀 *GitHub Morning Update*\n\n{summary}",
        "parse_mode": "Markdown"
    }
    
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

def send_macos_notification(summary):
    short_summary = (summary[:200] + '...') if len(summary) > 200 else summary
    apple_script = f'display notification "{short_summary}" with title "GitHub Morning Update"'
    subprocess.run(["osascript", "-e", apple_script])

def main():
    try:
        config = load_config()
        
        # Use GH CLI
        data = fetch_github_data_via_gh(config["github_username"])
        
        # Summarize with LM Studio
        summary = summarize_with_lm_studio(data, config["lm_studio_base_url"])
        
        # Send notifications
        send_macos_notification(summary)
        send_telegram_message(summary, config["telegram_bot_token"], config["telegram_chat_id"])
        
        print("Done! Check your Telegram and macOS notifications.")
        
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
