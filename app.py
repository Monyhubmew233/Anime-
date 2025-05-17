from flask import Flask, request
import os
import json
import requests

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))
API_URL = f"https://api.telegram.org/bot{TOKEN}"
JOIN_CHANNEL = "@for4ever_friends"
JOIN_URL = "https://t.me/for4ever_friends"
DB_FILE = "anime_db.json"

app = Flask(__name__)

# Load or initialize DB
def load_db():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w") as f:
            json.dump({}, f)
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2)

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

def send_message(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    requests.post(f"{API_URL}/sendMessage", data=data)

def send_video(chat_id, file_id, caption):
    data = {"chat_id": chat_id, "video": file_id, "caption": caption}
    requests.post(f"{API_URL}/sendVideo", data=data)

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json()

    if "message" in update:
        message = update["message"]
        chat_id = message["chat"]["id"]
        text = message.get("text", "").strip()
        reply = message.get("reply_to_message")
        user_id = message["from"]["id"]
        username = message["from"].get("username", "NoUsername")

        # Start command with join check
        if text.lower() == "/start":
            if not is_member(user_id):
                keyboard = {
                    "inline_keyboard": [[
                        {"text": "Join Channel", "url": JOIN_URL}
                    ]]
                }
                send_message(chat_id, "Please join our channel to use the bot:", reply_markup=keyboard)
                return "ok"
            send_message(chat_id, "Welcome! You can:\n- Type anime name to get video\n- Reply to a video and use /addanime <name> to add\nEnjoy!", reply_markup={
                "inline_keyboard": [[
                    {"text": "Join our Anime Community", "url": JOIN_URL}
                ]]
            })
            return "ok"

        db = load_db()

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
                    save_db(db)
                    send_message(chat_id, f"Anime '{anime_name}' added successfully!")
                else:
                    send_message(chat_id, "Reply must contain a video.")
            else:
                send_message(chat_id, "Usage: /addanime <name>")

        elif text:
            anime_name = text.lower()
            if anime_name in db:
                data = db[anime_name]
                send_video(chat_id, data["file_id"], data.get("caption", ""))
            else:
                keyboard = {
                    "inline_keyboard": [[
                        {"text": "Request to Add", "callback_data": f"req_{anime_name}"}
                    ]]
                }
                send_message(chat_id, f"Anime '{anime_name}' not found.", reply_markup=keyboard)

    elif "callback_query" in update:
        query = update["callback_query"]
        data = query["data"]
        user = query["from"]

        if data.startswith("req_"):
            anime_req = data[4:]
            send_message(user["id"], f"Request sent for: {anime_req}")
            send_message(ADMIN_ID, f"@{user.get('username', 'Unknown')} requested: {anime_req}")

    return "ok"

@app.route("/")
def index():
    return "Bot is running!"

if __name__ == "__main__":
    app.run(debug=True)
  
