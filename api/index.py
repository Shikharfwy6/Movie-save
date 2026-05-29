import os
import re
import asyncio
import requests
from json import loads
from pymongo import MongoClient
from http.server import BaseHTTPRequestHandler
import urllib.parse

# --- Environment Variables ---
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "moviegiver918_bot")
OWNER_ID = os.environ.get("OWNER_ID", "0")

# --- MongoDB Password Auto-Fix ---
try:
    if "@" in MONGO_URI and "://" in MONGO_URI:
        scheme, rest = MONGO_URI.split("://", 1)
        user_pass, host_part = rest.split("@", 1)
        if ":" in user_pass:
            username, password = user_pass.split(":", 1)
            encoded_password = urllib.parse.quote_plus(password)
            MONGO_URI = f"{scheme}://{username}:{encoded_password}@{host_part}"
except Exception as e:
    print(f"URI Parsing Error: {e}")

# --- Database Setup ---
db_client = MongoClient(MONGO_URI)
db = db_client["telegram_bot_db"]
videos_collection = db["saved_videos"]

# --- टेलीग्राम API को सीधे बिना किसी लाइब्रेरी के मैसेज भेजने का सबसे पक्का तरीका ---
def telegram_api_request(method, payload):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Telegram API Error: {e}")
        return None

def send_log_to_owner(text):
    if OWNER_ID != "0":
        telegram_api_request("sendMessage", {"chat_id": int(OWNER_ID), "text": text})

# --- Main Bot Logic (बिना पायरोग्राम क्रैश के सीधे सर्वरलेस मोड) ---
def handle_telegram_update(update_dict):
    try:
        # 1. पर्सनल मैसेज और ग्रुप मैसेज को हैंडल करना
        if "message" in update_dict:
            message = update_dict["message"]
            chat_id = message.get("chat", {}).get("id")
            chat_type = message.get("chat", {}).get("type", "")
            text = message.get("text", "").strip()
            msg_id = message.get("message_id")
            first_name = message.get("from", {}).get("first_name", "User")

            # 🅰️ पर्सनल मैसेज में /start कमांड
            if chat_type == "private" and text.startswith("/start"):
                if "video_id_" in text:
                    try:
                        v_id = int(text.split("video_id_")[1])
                        saved_video = videos_collection.find_one({"video_id": v_id})
                        if saved_video:
                            reply_text = f"🍿 **आपकी मांगी गई वीडियो तैयार है!**\n\n📝 **कैप्शन:** {saved_video['caption']}\n\nयह वीडियो हमारे डेटाबेस से सुरक्षित खोजी गई है।"
                            telegram_api_request("sendMessage", {"chat_id": chat_id, "text": reply_text, "parse_mode": "Markdown"})
                            send_log_to_owner(f"👤 यूजर {first_name} (ID: {chat_id}) ने वीडियो ID {v_id} को निकाला।")
                        else:
                            telegram_api_request("sendMessage", {"chat_id": chat_id, "text": "❌ क्षमा करें! यह वीडियो हमारे डेटाबेस में नहीं मिली।"})
                    except Exception as e:
                        telegram_api_request("sendMessage", {"chat_id": chat_id, "text": "❌ लिंक अमान्य है।"})
                else:
                    # साधारण /start रिस्पॉन्स
                    reply_text = f"👋 हेलो {first_name}!\n\n🤖 मैं एक **ऑटोमैटिक मूवी सेव बॉट** हूँ।\n\n🟢 **बॉट स्थिति:** एक्टिव और चालू है!\n✨ **मेरा काम:** जब भी हमारे चैनल में कोई video अपलोड होगी, मैं उसे डेटाबेस में सुरक्षित रख लूँगा।"
                    telegram_api_request("sendMessage", {"chat_id": chat_id, "text": reply_text, "parse_mode": "Markdown"})
                return

            # 🅱️ ग्रुप में कीवर्ड सर्च करना
            if chat_type in ["group", "supergroup"] and text and len(text) >= 3:
                search_pattern = re.compile(re.escape(text), re.IGNORECASE)
                results = videos_collection.find({"caption": search_pattern})
                
                buttons = []
                for movie in results:
                    buttons.append([{"text": movie["caption"], "url": movie["link"]}])
                
                if buttons:
                    payload = {
                        "chat_id": chat_id,
                        "text": f"🔍 आपके कीवर्ड **'{text}'** के लिए ये वीडियो मिले हैं:",
                        "reply_markup": {"inline_keyboard": buttons},
                        "reply_to_message_id": msg_id,
                        "parse_mode": "Markdown"
                    }
                    telegram_api_request("sendMessage", payload)
                return

        # 2. चैनल पोस्ट को हैंडल करना (वीडियो ऑटो-सेविंग)
        if "channel_post" in update_dict:
            channel_post = update_dict["channel_post"]
            if "video" in channel_post:
                video_id = channel_post["message_id"]
                caption = channel_post.get("caption", "No Caption")
                channel_title = channel_post.get("chat", {}).get("title", "चैनल")
                
                bot_start_link = f"https://t.me/{BOT_USERNAME}?start=video_id_{video_id}"
                video_data = {
                    "video_id": video_id,
                    "caption": caption,
                    "link": bot_start_link
                }
                
                # MongoDB में डेटा इन्सर्ट करना
                videos_collection.update_one({"video_id": video_id}, {"$set": video_data}, upsert=True)
                
                # लाइव लॉग टेलीग्राम पर भेजना
                log_message = (
                    f"📢 **बॉट लाइव लॉग रिपोर्ट** 📢\n\n"
                    f"✅ **डेटाबेस स्थिति:** सफलतापूर्वक सेव हुआ (MongoDB)\n"
                    f"📺 **चैनल का नाम:** {channel_title}\n"
                    f"🆔 **वीडियो संदेश ID:** {video_id}\n"
                    f"📝 **कैप्शन:** {caption}\n\n"
                    f"🔗 **बॉट जनरेटेड लिंक:** {bot_start_link}"
                )
                send_log_to_owner(log_message)
                return

    except Exception as e:
        print(f"Error in handler logic: {e}")
        send_log_to_owner(f"⚠️ **बॉट के अंदर एरर आया:**\n`{str(e)}`")

# --- Vercel Serverless HTTP Handler ---
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        try:
            update_dict = loads(post_data.decode('utf-8'))
            # डायरेक्ट फंक्शन कॉल (बिना अटके हुए एसिंक लूप के)
            handle_telegram_update(update_dict)
        except Exception as e:
            print(f"POST Handler Error: {e}")
            
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"OK")

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is running via Webhook!")
