import os
import asyncio
import aiohttp
import urllib.parse
import requests
from aiohttp import web

from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==========================================
# 🔑 CREDENTIALS & SETUP
# ==========================================
try:
    API_ID = int(os.environ.get("API_ID", 0))
except ValueError:
    API_ID = 0
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
FILEPURSUIT_API_KEY = os.environ.get("FILEPURSUIT_API_KEY", "")
USER_SESSION_STRING = os.environ.get("USER_SESSION_STRING", "")

# Initialize the main Bot AND the background Userbot
app = Client("AllFileFinderBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
userbot = Client("SearchUserbot", api_id=API_ID, api_hash=API_HASH, session_string=USER_SESSION_STRING)

user_search_cache = {}
MAX_DIRECT_SIZE = 1.5 * 1024 * 1024 * 1024  # 1.5 GB limit

def format_size(size_in_bytes):
    try:
        size = int(size_in_bytes)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
    except:
        return "Unknown Size"

# ==========================================
# 🔍 THE 4-STAGE SEARCH ENGINE
# ==========================================

async def search_telegram(query):
    results = []
    try:
        async for msg in userbot.search_global(query, limit=5):
            if msg.document or msg.video or msg.audio:
                file_obj = msg.document or msg.video or msg.audio
                results.append({
                    "title": getattr(file_obj, "file_name", None) or "Telegram Media File",
                    "raw_size": file_obj.file_size,
                    "size": format_size(file_obj.file_size),
                    "msg_id": msg.id,
                    "chat_id": msg.chat.id,
                    "format": "✈️ Telegram Drive",
                    "source": "telegram"
                })
    except Exception as e:
        print(f"Userbot Search Error: {e}")
    return results

async def search_filepursuit(query):
    results = []
    if not FILEPURSUIT_API_KEY: return results
    
    url = f"https://filepursuit.p.rapidapi.com/?q={urllib.parse.quote(query)}"
    headers = {
        "x-rapidapi-host": "filepursuit.p.rapidapi.com",
        "x-rapidapi-key": FILEPURSUIT_API_KEY
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "success":
                        for item in data.get("files_found", [])[:5]:
                            raw_size = int(item.get("size_bytes", 0))
                            results.append({
                                "title": item.get("file_name", "Unknown File"),
                                "raw_size": raw_size,
                                "size": format_size(raw_size),
                                "link": item.get("file_link", ""),
                                "format": "🌐 Web DDL / G-Drive",
                                "source": "filepursuit"
                            })
    except Exception as e:
        print(f"FilePursuit Error: {e}")
    return results

async def search_torrent(query):
    url = f"https://apibay.org/q.php?q={urllib.parse.quote(query)}"
    results = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and isinstance(data, list) and data[0].get("id") != "0":
                        for item in data[:5]:
                            raw_size = int(item.get("size", 0))
                            results.append({
                                "title": item.get("name", "Unknown File"),
                                "raw_size": raw_size,
                                "size": format_size(raw_size),
                                "hash": item.get("info_hash", ""),
                                "format": "🧲 Torrent / Magnet",
                                "source": "torrent"
                            })
    except: pass
    return results

# ==========================================
# 🎛️ BOT INTERFACE & ROUTING
# ==========================================

@app.on_message(filters.command("start"))
async def start_command(client, message):
    user_id = message.from_user.id
    if user_id in user_search_cache: del user_search_cache[user_id]
    await message.reply_text(
        "👋 **Welcome to the Ultimate 4-Stage File Finder!**\n\n"
        "Just send me the name of any Movie, Software, or Book you want to find. "
        "I will search Telegram Drives, Web DDLs, and Torrents automatically."
    )

@app.on_message(filters.text & filters.private & ~filters.command("start"))
async def handle_search_query(client, message):
    query = message.text
    user_id = message.from_user.id
    status_msg = await message.reply_text(f"🔍 **Stage 1:** Searching Telegram Drives for `{query}`...")
    
    results = await search_telegram(query)
    
    if not results:
        await status_msg.edit_text(f"🔍 **Stage 2:** No Telegram files found. Scanning Web DDLs...")
        results = await search_filepursuit(query)
        
    if not results:
        await status_msg.edit_text(f"🔍 **Stage 4:** No direct links found. Switching to Torrent databases...")
        results = await search_torrent(query)

    if results:
        user_search_cache[user_id] = {"results": results}
        text = f"✅ **Found Best Matches for:** `{query}`\n\n"
        buttons = []
        for i, res in enumerate(results):
            text += f"**{i+1}.** {res['title']}\n📁 {res['format']} | 💾 **{res['size']}**\n\n"
            buttons.append([InlineKeyboardButton(f"📥 Process File {i+1}", callback_data=f"leech_{i}")])
            
        await status_msg.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await status_msg.edit_text("❌ No results found on any database. Try changing the spelling.")

@app.on_callback_query(filters.regex("^leech_"))
async def process_delivery(client, callback_query):
    index = int(callback_query.data.split("_")[1])
    user_id = callback_query.from_user.id
    user_data = user_search_cache.get(user_id)
    
    if not user_data or "results" not in user_data:
        await callback_query.answer("⚠️ Session expired.", show_alert=True)
        return
        
    res = user_data["results"][index]
    status_msg = await callback_query.message.reply_text("🔄 **Executing Delivery Protocol...**")
    
    # Protocol 1: Telegram File Transfer (Ultra Fast)
    if res["source"] == "telegram":
        await status_msg.edit_text("📤 **Extracting file from Telegram Drive & Forwarding...**")
        try:
            msg = await userbot.get_messages(res["chat_id"], res["msg_id"])
            await msg.copy(user_id, caption=f"✅ {res['title']}")
            await status_msg.delete()
        except Exception as e:
            await status_msg.edit_text(f"❌ Failed to extract Telegram file: {e}")
            
    # Protocol 2: Web DDL Delivery (Smart Download for small files < 1.5GB)
    elif res["source"] == "filepursuit":
        if res["raw_size"] > 0 and res["raw_size"] <= MAX_DIRECT_SIZE:
            await status_msg.edit_text(f"📥 **Downloading file from Web DDL...**\n`{res['title']}`")
            loop = asyncio.get_event_loop()
            filename = f"file_{index}.bin"
            try:
                def fetch_web_file():
                    with requests.get(res["link"], stream=True, timeout=30) as r:
                        r.raise_for_status()
                        with open(filename, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
                await loop.run_in_executor(None, fetch_web_file)
                await status_msg.edit_text("📤 **Uploading file to Telegram...**")
                await client.send_document(chat_id=user_id, document=filename, caption=f"✅ {res['title']}")
                os.remove(filename)
                await status_msg.delete()
                return
            except Exception:
                if os.path.exists(filename): os.remove(filename)
        
        # Fallback to web link if download fails or file is large (> 1.5GB)
        await status_msg.edit_text(
            f"🔗 **Direct Web Download Link:**\n\n"
            f"📁 **Name:** `{res['title']}`\n"
            f"📥 **Link:** [Click Here to Download]({res['link']})\n\n"
            f"*(Server-bypassed direct link via FilePursuit API)*",
            disable_web_page_preview=True
        )
        
    # Protocol 3: Magnet Fallback
    elif res["source"] == "torrent":
        magnet = f"magnet:?xt=urn:btih:{res['hash']}&dn={urllib.parse.quote(res['title'])}"
        await status_msg.edit_text(
            f"🔗 **Magnet Link (Torrent Fallback):**\n\n"
            f"📁 **Name:** `{res['title']}`\n"
            f"🧲 **Link:**\n`{magnet}`\n\n"
            f"💡 *Tip: Copy this link into Seedr.cc or a torrent client for instant download.*"
        )

# ==========================================
# 🌐 WEB SERVER & RUNNER
# ==========================================
async def health_check(request):
    return web.Response(text="Super-Bot is Running with FilePursuit & Userbot!")

async def main():
    port = int(os.environ.get("PORT", 10000))
    server = web.Application()
    server.router.add_get('/', health_check)
    runner = web.AppRunner(server)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    await app.start()
    await userbot.start()
    print("🚀 SUPER-BOT IS LIVE WITH USERBOT AND FILEPURSUIT!")
    
    await idle()
    
    await app.stop()
    await userbot.stop()
    await runner.cleanup()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("Bot stopped.")
    except Exception as e:
        print(f"Critical Error: {e}")
