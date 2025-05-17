from flask import Flask, request
import os
import json
import requests
import time
import threading
import re
import difflib
from collections import defaultdict

app = Flask(__name__)

# Environment Variables
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))
API_URL = f"https://api.telegram.org/bot{TOKEN}"
JOIN_CHANNEL = "@for4ever_friends"
JOIN_URL = "https://t.me/for4ever_friends"
DB_FILE = "anime_db.json"
REQ_FILE = "requests.json"

# JSON Helpers
def load_json(file):
    if not os.path.exists(file):
        with open(file, "w") as f:
            json.dump({}, f)
    with open(file, "r") as f:
        return json.load(f)

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

# Check user is member
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

# Send basic message
def send_message(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    requests.post(f"{API_URL}/sendMessage", data=data)

# Send video
def send_video(chat_id, file_id, caption):
    full_caption = f"{caption}\n\n⚠️ Please forward this video. It will be deleted in 2 minutes due to copyright."
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

# Title extractor
def parse_title_parts(text):
    title = re.sub(r"[\s_]+", " ", text.lower()).strip()
    match = re.match(r"(.+?)\s*(season\s*\d+)?\s*(ep(isode)?\s*\d+)?", title)
    if match:
        base = match.group(1).strip()
        season = match.group(2).strip() if match.group(2) else None
        episode = match.group(3).strip() if match.group(3) else None
        return base, season, episode
    return title, None, None

# Group by season
def get_seasons(db, base_title):
    seasons = set()
    for key in db:
        if key.startswith(base_title):
            _, s, _ = parse_title_parts(key)
            if s:
                seasons.add(s)
    return sorted(seasons)

def get_episodes(db, base_title, season):
    eps = []
    for key in db:
        bt, s, e = parse_title_parts(key)
        if bt == base_title and s == season:
            eps.append((key, e))
    return sorted(eps, key=lambda x: x[1])

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

        if text.lower() == "/start":
            if not is_member(user_id):
                keyboard = {"inline_keyboard": [[{"text": "Join Channel", "url": JOIN_URL}]]}
                send_message(chat_id, "❗ Please join the channel to use this bot:", reply_markup=keyboard)
                return "ok"
            photo_url = "https://i.ibb.co/fJwRQXZ/IMG-20250516-095810-290.jpg"
            caption = (
                "🎉 <b>Welcome to Anime Video Bot!</b>\n\n"
                "➤ Type any anime name to get the video.\n"
                "➤ If not found, press 'Request to Add'.\n"
                "➤ Or reply to any video and use <code>/addanime &lt;name&gt;</code>."
            )
            data = {
                "chat_id": chat_id,
                "photo": photo_url,
                "caption": caption,
                "parse_mode": "HTML",
                "reply_markup": json.dumps({"inline_keyboard": [[{"text": "Join our Anime Community", "url": JOIN_URL}]]})
            }
            requests.post(f"{API_URL}/sendPhoto", data=data)
            return "ok"

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
                    send_message(chat_id, "❗ Reply must contain a video.")
            else:
                send_message(chat_id, "Usage: /addanime <name>")
            return "ok"

        if "video" in message and "caption" in message:
            title, season, episode = parse_title_parts(message["caption"])
            key = f"{title} {season} {episode}".strip()
            if key not in db:
                db[key] = {
                    "file_id": message["video"]["file_id"],
                    "caption": message["caption"]
                }
                save_json(DB_FILE, db)
                send_message(chat_id, f"✅ Auto-added anime: <b>{key}</b>")
            return "ok"

        if text:
            base_title, _, _ = parse_title_parts(text)
            matches = difflib.get_close_matches(base_title, [parse_title_parts(k)[0] for k in db.keys()], n=1, cutoff=0.3)
            if matches:
                matched = matches[0]
                seasons = get_seasons(db, matched)
                if seasons:
                    keyboard = {"inline_keyboard": [[{"text": s.title(), "callback_data": f"s_{matched}_{s}"}] for s in seasons]}
                    send_message(chat_id, f"📺 Found anime: <b>{matched.title()}</b>\nSelect season:", reply_markup=keyboard)
                else:
                    send_message(chat_id, f"❌ No seasons found for '{matched}'")
            else:
                keyboard = {"inline_keyboard": [[{"text": "Request to Add", "callback_data": f"req_{base_title}"}]]}
                send_message(chat_id, f"❌ Anime '{base_title}' not found.", reply_markup=keyboard)
        return "ok"

    elif "callback_query" in update:
        query = update["callback_query"]
        data = query["data"]
        user = query["from"]
        chat_id = query["message"]["chat"]["id"]

        if data.startswith("req_"):
            anime_req = data[4:]
            req_db[anime_req] = user["id"]
            save_json(REQ_FILE, req_db)
            send_message(user["id"], f"✅ Your request for '<b>{anime_req}</b>' has been sent to admin.")
            send_message(ADMIN_ID, f"📥 New Anime Request from @{user.get('username', 'Unknown')}:\n<code>{anime_req}</code>")

        elif data.startswith("s_"):
            _, title, season = data.split("_", 2)
            db = load_json(DB_FILE)
            episodes = get_episodes(db, title, season)
            if episodes:
                keyboard = {"inline_keyboard": [[{"text": e[1].title(), "callback_data": f"ep_{e[0]}"}] for e in episodes]}
                send_message(chat_id, f"📼 Season: <b>{season.title()}</b>\nChoose episode:", reply_markup=keyboard)
            else:
                send_message(chat_id, "❌ No episodes found.")

        elif data.startswith("ep_"):
            key = data[3:]
            db = load_json(DB_FILE)
            anime_data = db.get(key)
            if anime_data:
                send_video(chat_id, anime_data["file_id"], anime_data.get("caption", ""))

    return "ok"

@app.route("/")
def index():
    return "Bot is running!"

if __name__ == "__main__":
    app.run(debug=True)
