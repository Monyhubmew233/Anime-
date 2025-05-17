from flask import Flask, request
import os
import json
import requests
import time
import threading
import re
import difflib
from collections import defaultdict

# Environment Variables
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))
API_URL = f"https://api.telegram.org/bot{TOKEN}"
JOIN_CHANNEL = "@for4ever_friends"
JOIN_URL = "https://t.me/for4ever_friends"
DB_FILE = "anime_db.json"
REQ_FILE = "requests.json"

app = Flask(__name__)

# JSON DB Helpers
def load_json(file):
    if not os.path.exists(file):
        with open(file, "w") as f:
            json.dump({}, f)
    with open(file, "r") as f:
        return json.load(f)

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

# Chat member check
def is_member(user_id):
    try:
        resp = requests.get(f"{API_URL}/getChatMember", params={
            "chat_id": JOIN_CHANNEL,
            "user_id": user_id
        }).json()
        status = resp.get("result", {}).get("status", "")
        return status in ["member", "administrator", "creator"]
    except:
        return False

# Send message
def send_message(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    requests.post(f"{API_URL}/sendMessage", data=data)

# Send video + auto-delete
def send_video(chat_id, file_id, caption):
    full_caption = f"{caption}\n\nAaye! Please forward this video. It will be deleted in 2 minutes due to copyright."
    data = {
        "chat_id": chat_id,
        "video": file_id,
        "caption": full_caption,
        "parse_mode": "HTML"
    }
    resp = requests.post(f"{API_URL}/sendVideo", data=data).json()
    if resp.get("ok"):
        msg_id = resp["result"]["message_id"]
        threading.Thread(target=delete_message_later, args=(chat_id, msg_id)).start()

def delete_message_later(chat_id, message_id, delay=120):
    time.sleep(delay)
    requests.post(f"{API_URL}/deleteMessage", data={
        "chat_id": chat_id,
        "message_id": message_id
    })

# Extract title from caption
def extract_anime_title(caption):
    match = re.search(r"(.+?)\s*(season\s*\d+)?\s*(episode\s*\d+)?", caption, re.IGNORECASE)
    if match:
        parts = [p.strip().lower() for p in match.groups() if p]
        return ' '.join(parts)
    return None

# Grouping for buttons
def group_animes(anime_list):
    grouped = defaultdict(list)
    for name in anime_list:
        season_match = re.search(r"(season\s*\d+)", name, re.IGNORECASE)
        key = season_match.group(1).lower() if season_match else "others"
        grouped[key].append(name)
    return grouped

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json()
    db = load_json(DB_FILE)
    req_db = load_json(REQ_FILE)

    if "message" in update:
        message = update["message"]
        chat_id = message["chat"]["id"]
        text = message.get("text", "").strip()
        reply = message.get("reply_to_message")
        user_id = message["from"]["id"]
        username = message["from"].get("username", "NoUsername")

        # Join check
        if text.lower() == "/start":
            if not is_member(user_id):
                keyboard = {
                    "inline_keyboard": [[
                        {"text": "Join Channel", "url": JOIN_URL}
                    ]]
                }
                send_message(chat_id, "Please join our channel to use the bot:", reply_markup=keyboard)
                return "ok"
            send_message(chat_id, "Welcome! You can:\n- Type anime name to get video\n- Reply to video + use /addanime <name>\nEnjoy!", reply_markup={
                "inline_keyboard": [[
                    {"text": "Join our Anime Community", "url": JOIN_URL}
                ]]
            })
            return "ok"

        # Manual /addanime
        if text.lower().startswith("/addanime") and reply:
            parts = text.split(" ", 1)
            if len(parts) == 2:
                anime_name = parts[1].strip().lower()
                video = reply.get("video")
                caption = reply.get("caption", "")
                if video:
                    db[anime_name] = {
                        "file_id": video["file_id"],
                        "caption": caption
                    }
                    save_json(DB_FILE, db)
                    send_message(chat_id, f"✅ Anime '{anime_name}' added successfully!")
                    if anime_name in req_db:
                        requester_id = req_db[anime_name]
                        send_message(requester_id, f"✅ Anime '{anime_name}' has been added!")
                        del req_db[anime_name]
                        save_json(REQ_FILE, req_db)
                else:
                    send_message(chat_id, "Reply must contain a video.")
            else:
                send_message(chat_id, "Usage: /addanime <name>")
            return "ok"

        # Auto-add from captioned video
        if "video" in message and "caption" in message:
            title = extract_anime_title(message["caption"])
            if title:
                if title not in db:
                    db[title] = {
                        "file_id": message["video"]["file_id"],
                        "caption": message["caption"]
                    }
                    save_json(DB_FILE, db)
                    send_message(chat_id, f"✅ Auto-added anime: <b>{title}</b>")
            return "ok"

        # Smart Anime Search
        if text:
            anime_name = text.lower()
            keys = list(db.keys())
            best_matches = difflib.get_close_matches(anime_name, keys, n=20, cutoff=0.3)

            if len(best_matches) == 1:
                data = db[best_matches[0]]
                send_video(chat_id, data["file_id"], data.get("caption", ""))

            elif len(best_matches) > 1:
                grouped = group_animes(best_matches)
                buttons = []
                for season, names in grouped.items():
                    for name in names:
                        buttons.append([{"text": name.title(), "callback_data": f"anime_{name}"}])
                send_message(chat_id, "Multiple results found:", reply_markup={"inline_keyboard": buttons})

            else:
                keyboard = {
                    "inline_keyboard": [[
                        {"text": "Request to Add", "callback_data": f"req_{anime_name}"}
                    ]]
                }
                send_message(chat_id, f"❌ Anime '{anime_name}' not found.", reply_markup=keyboard)

    # Handle Callback Buttons
    elif "callback_query" in update:
        query = update["callback_query"]
        data = query["data"]
        user = query["from"]
        chat_id = query["message"]["chat"]["id"]

        if data.startswith("req_"):
            anime_req = data[4:]
            req_db[anime_req] = user["id"]
            save_json(REQ_FILE, req_db)
            send_message(user["id"], f"Your request for '<b>{anime_req}</b>' has been sent to admin.")
            send_message(ADMIN_ID, f"📥 New Request from @{user.get('username', 'Unknown')}:\n<code>{anime_req}</code>")

        elif data.startswith("anime_"):
            key = data[6:]
            anime_data = db.get(key)
            if anime_data:
                send_video(chat_id, anime_data["file_id"], anime_data.get("caption", ""))

    return "ok"

@app.route("/")
def index():
    return "Bot is running!"

if __name__ == "__main__":
    app.run(debug=True)
