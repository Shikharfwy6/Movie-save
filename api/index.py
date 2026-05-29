import os
import re
import asyncio
from json import loads
from pyrogram import Client, filters
from pyrogram.types import Update, InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from http.server import BaseHTTPRequestHandler
import urllib.parse

# --- पर्यावरण चर (Environment Variables) लोड करना ---
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "moviegiver918_bot")

# --- पासवर्ड को ऑटो-फिक्स करने का लॉजिक ---
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

# --- डेटाबेस सेटअप ---
db_client = MongoClient(MONGO_URI)
db = db_client["telegram_bot_db"]
videos_collection = db["saved_videos"]

# ⚠️ एरर फिक्स: यहाँ in_memory=True जोड़ दिया गया है
bot_client = Client(
    "my_vercel_bot", 
    api_id=API_ID, 
    api_hash=API_HASH, 
    bot_token=BOT_TOKEN, 
    workers=1,
    in_memory=True
)

# --- बॉट का मुख्य लॉजिक (Async Function) ---
async def handle_telegram_update(update_dict):
    await bot_client.start()
    try:
        update = Update.read(bot_client, update_dict)
        
        if update and update.message:
            message = update.message

            # 1. चैनल से वीडियो और कैप्शन को ऑटो-सेव करना
            if message.chat and message.chat.type == "channel" and message.video:
                video_id = message.id
                caption = message.caption if message.caption else "No Caption"
                bot_start_link = f"https://t.me/{BOT_USERNAME}?start=video_id_{video_id}"
                
                video_data = {
                    "video_id": video_id,
                    "caption": caption,
                    "link": bot_start_link
                }
                videos_collection.update_one({"video_id": video_id}, {"$set": video_data}, upsert=True)
                print("Video successfully saved in MongoDB!")

            # 2. ग्रुप में कीवर्ड सर्च करना
            elif message.chat and message.chat.type in ["group", "supergroup"] and message.text:
                user_query = message.text.strip()
                if len(user_query) >= 3:
                    search_pattern = re.compile(re.escape(user_query), re.IGNORECASE)
                    results = videos_collection.find({"caption": search_pattern})
                    
                    buttons = []
                    for movie in results:
                        buttons.append([InlineKeyboardButton(text=movie["caption"], url=movie["link"])])
                    
                    if buttons:
                        await message.reply_text(
                            text=f"🔍 आपके कीवर्ड **'{user_query}'** के लिए ये वीडियो मिले हैं:",
                            reply_markup=InlineKeyboardMarkup(buttons)
                        )
    except Exception as e:
        print(f"Processing Error: {e}")
    finally:
        await bot_client.stop()

# --- वर्सेल सर्वरलेस हैंडलर ---
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        try:
            update_dict = loads(post_data.decode('utf-8'))
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(handle_telegram_update(update_dict))
            loop.close()
            
        except Exception as e:
            print(f"Post Error: {e}")
            
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"OK")

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is running via Webhook!")
