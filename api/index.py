import os
import re
import asyncio
from json import loads
from pyrogram import Client, filters
from pyrogram.types import Update, InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from http.server import BaseHTTPRequestHandler

# --- पर्यावरण चर (Environment Variables) लोड करना ---
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "Getvideo81827_bot")

# --- डेटाबेस और बॉट सेटअप ---
db_client = MongoClient(MONGO_URI)
db = db_client["telegram_bot_db"]
videos_collection = db["saved_videos"]

# ध्यान दें: वैबहुक में हमें workers=0 रखना होता है ताकि यह सर्वरलेस पर क्रैश न हो
app = Client("my_vercel_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=0)

# --- बॉट का मुख्य लॉजिक (Async Functions) ---

async def handle_telegram_update(update_dict):
    """टेलीग्राम से आए मैसेज को प्रोसेस करने का फंक्शन"""
    await app.start()
    try:
        # कनवर्ट करें डिक्शनरी को पायथन ऑब्जेक्ट में
        update = Update.read(app, update_dict)
        message = update.message
        
        if not message:
            return

        # 1. चैनल से वीडियो और कैप्शन को ऑटो-से文व करना
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
    finally:
        await app.stop()

# --- वर्सेल सर्वरलेस हैंडलर (HTTP Server) ---
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        """जब टेलीग्राम वर्सेल को डेटा भेजेगा"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        try:
            update_dict = loads(post_data.decode('utf-8'))
            # वर्सेल के सिंक्रोनस एनवायरनमेंट में एसिंक कोड चलाना
            asyncio.run(handle_telegram_update(update_dict))
        except Exception as e:
            print(f"Error: {e}")
            
        # टेलीग्राम को बताना कि मैसेज मिल गया है (200 OK)
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"OK")

    def do_GET(self):
        """वेबसाइट लिंक खोलने पर दिखने वाला मैसेज"""
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is running via Webhook!")
  
