import os
import re
import asyncio
from json import loads
from pyrogram import Client
from pyrogram.types import Update, InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from http.server import BaseHTTPRequestHandler
import urllib.parse

# --- Environment Variables ---
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "moviegiver918_bot")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))  # आपकी टेलीग्राम आईडी यहाँ आएगी

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

# Vercel-Optimized Pyrogram Client
bot_client = Client("my_vercel_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=1, in_memory=True)

# --- सहायक फ़ंक्शन (Telegram पर लॉग भेजने के लिए) ---
async def send_log_to_owner(text):
    if OWNER_ID != 0:
        try:
            await bot_client.send_message(chat_id=OWNER_ID, text=text)
        except Exception as e:
            print(f"Log sending failed: {e}")

# --- Main Bot Logic ---
async def handle_telegram_update(update_dict):
    await bot_client.start()
    try:
        update = Update.read(bot_client, update_dict)
        
        # 1. पर्सनल मैसेज में /start कमांड हैंडल करना
        message = update_dict.get("message") or (update.message if hasattr(update, "message") else None)
        if message:
            if isinstance(message, dict):
                chat_type = message.get("chat", {}).get("type", "")
                text = message.get("text", "").strip()
                chat_id = message.get("chat", {}).get("id")
                msg_id = message.get("message_id")
                first_name = message.get("from", {}).get("first_name", "User")
            else:
                chat_type = message.chat.type if message.chat else ""
                text = message.text.strip() if message.text else ""
                chat_id = message.chat.id if message.chat else None
                msg_id = message.id
                first_name = message.from_user.first_name if message.from_user else "User"

            # अगर यूजर ने पर्सनल में /start भेजा है
            if chat_type == "private" and text.startswith("/start"):
                # चेक करें कि क्या यह किसी मूवी लिंक के थ्रू आया है (जैसे /start video_id_12)
                if "video_id_" in text:
                    v_id = int(text.split("video_id_")[1])
                    saved_video = videos_collection.find_one({"video_id": v_id})
                    if saved_video:
                        await bot_client.send_message(
                            chat_id=chat_id,
                            text=f"🍿 **आपकी मांगी गई वीडियो तैयार है!**\n\n📝 **कैप्शन:** {saved_video['caption']}\n\nयह वीडियो हमारे डेटाबेस से सुरक्षित खोजी गई है।"
                        )
                        # ओनर को लॉग भेजें कि किसी यूजर ने वीडियो ली
                        await send_log_to_owner(f"👤 यूजर [{first_name}](tg://user?id={chat_id}) ने वीडियो ID `{v_id}` को डाउनलोड किया।")
                    else:
                        await bot_client.send_message(chat_id=chat_id, text="❌ क्षमा करें! यह वीडियो हमारे डेटाबेस में नहीं मिली।")
                else:
                    # साधारण /start मैसेज
                    await bot_client.send_message(
                        chat_id=chat_id,
                        text=f"👋 हेलो {first_name}!\n\n🤖 मैं एक **ऑटोमैटिक मूवी सेव बॉट** हूँ।\n\n🟢 **बॉट स्थिति:** एक्टिव और चालू है!\n✨ **मेरा काम:** जब भी हमारे चैनल में कोई वीडियो अपलोड होगी, मैं उसे डेटाबेस में सुरक्षित रख लूँगा और आपके ग्रुप में कीवर्ड सर्च करने पर तुरंत निकाल कर दे दूँगा।"
                    )
                return

            # ग्रुप सर्च को हैंडल करने का तरीका
            if chat_type in ["group", "supergroup"] and text and len(text) >= 3:
                search_pattern = re.compile(re.escape(text), re.IGNORECASE)
                results = videos_collection.find({"caption": search_pattern})
                
                buttons = []
                for movie in results:
                    buttons.append([InlineKeyboardButton(text=movie["caption"], url=movie["link"])])
                
                if buttons and chat_id:
                    await bot_client.send_message(
                        chat_id=chat_id,
                        text=f"🔍 आपके कीवर्ड **'{text}'** के लिए ये वीडियो मिले हैं:",
                        reply_markup=InlineKeyboardMarkup(buttons),
                        reply_to_message_id=msg_id
                    )
                return

        # 2. चैनल पोस्ट को हैंडल करना (वीडियो सेविंग और लाइव ओनर लॉग्स)
        channel_post = update_dict.get("channel_post") or (update.channel_post if hasattr(update, "channel_post") else None)
        if channel_post:
            if isinstance(channel_post, dict) and "video" in channel_post:
                video_id = channel_post["message_id"]
                caption = channel_post.get("caption", "No Caption")
                channel_title = channel_post.get("chat", {}).get("title", "चैनल")
            elif hasattr(channel_post, "video") and channel_post.video:
                video_id = channel_post.id
                caption = channel_post.caption if channel_post.caption else "No Caption"
                channel_title = channel_post.chat.title if channel_post.chat else "चैनल"
            else:
                video_id = None

            if video_id:
                bot_start_link = f"https://t.me/{BOT_USERNAME}?start=video_id_{video_id}"
                video_data = {
                    "video_id": video_id,
                    "caption": caption,
                    "link": bot_start_link
                }
                
                # MongoDB में डेटा सेव करना
                videos_collection.update_one({"video_id": video_id}, {"$set": video_data}, upsert=True)
                
                # 📢 लाइव टेलीग्राम लॉग: सीधे आपको मैसेज आ जाएगा
                log_message = (
                    f"📢 **बॉट लाइव लॉग रिपोर्ट** 📢\n\n"
                    f"✅ **डेटाबेस स्थिति:** सफलतापूर्वक सेव हुआ (MongoDB)\n"
                    f"📺 **चैनल का नाम:** {channel_title}\n"
                    f"🆔 **वीडियो संदेश ID:** `{video_id}`\n"
                    f"📝 **कैप्शन:** `{caption}`\n\n"
                    f"🔗 **बॉट जनरेटेड लिंक:** {bot_start_link}"
                )
                await send_log_to_owner(log_message)
                return

    except Exception as e:
        # अगर कोई गड़बड़ होती है तो एरर रिपोर्ट भी आपको टेलीग्राम पर मिल जाएगी
        await send_log_to_owner(f"⚠️ **बॉट एरर रिपोर्ट:**\n`{str(e)}`")
    finally:
        await bot_client.stop()

# --- Vercel Serverless HTTP Handler ---
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
