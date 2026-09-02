import os
import asyncio
import aiohttp
import urllib.parse
import requests
from bs4 import BeautifulSoup
from aiohttp import web
from curl_cffi import requests as cffi_requests

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

# SEQUENCE FIX: App ko pehle define karna hai
app = Client("AllFileFinderBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
userbot = Client("SearchUserbot", api_id=API_ID, api_hash=API_HASH, session_string=USER_SESSION_STRING)

user_search_cache = {}
user_state = {}
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
# ⚡ SEARCH ENGINES (WITH CLOUDFLARE BYPASS)
# ==========================================

async def search_libgen(query):
    url = f"https://libgen.rs/search.php?req={urllib.parse.quote(query)}&res=5&view=simple&phrase=1&column=def"
    results = []
    try:
        loop = asyncio.get_event_loop()
        # MAGIC FIX: curl_cffi impersonating Chrome
        res = await loop.run_in_executor(None, lambda: cffi_requests.get(url, impersonate="chrome", timeout=15))
        
        soup = BeautifulSoup(res.text, 'html.parser')
        table = soup.find('table', class_='c')
        if not table: return results
        
        for row in table.find_all('tr')[1:]:
            cols = row.find_all('td')
            if len(cols) < 9: continue
            
            md5_link = cols[2].find('a', href=True)
            if not md5_link or 'md5=' not in md5_link['href'].lower(): continue
            md5 = md5_link['href'].split('md5=')[-1][:32]
            
            title = cols[2].text.strip()
            size_str = cols[7].text.strip()
            ext = cols[8].text.strip().lower()
            
            raw_size = 0
            if 'kb' in size_str.lower(): raw_size = float(size_str.lower().replace('kb', '').strip()) * 1024
            elif 'mb' in size_str.lower(): raw_size = float(size_str.lower().replace('mb', '').strip()) * 1024 * 1024
            elif 'gb' in size_str.lower(): raw_size = float(size_str.lower().replace('gb', '').strip()) * 1024 * 1024 * 1024
            
            results.append({
                "title": title,
                "raw_size": raw_size,
                "size": size_str,
                "md5": md5,
                "format": f"📚 {ext.upper()}",
                "source": "libgen"
            })
            if len(results) >= 5: break
    except Exception as e:
        print(f"Libgen Search Error: {e}")
    return results

def get_libgen_direct_link(md5):
    url = f"http://library.lol/main/{md5}"
    try:
        # MAGIC FIX: curl_cffi impersonating Chrome
        res = cffi_requests.get(url, impersonate="chrome", timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        dl_link = soup.find('a', string='GET')
        if dl_link: return dl_link['href']
    except: pass
    return None

async def search_telegram(query):
    results = []
    try:
        async for msg in userbot.search_global(query, limit=3):
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
    except: pass
    return results

async def search_filepursuit(query):
    results = []
    if not FILEPURSUIT_API_KEY: return results
    url = f"https://filepursuit.p.rapidapi.com/?q={urllib.parse.quote(query)}"
    headers = {"x-rapidapi-host": "filepursuit.p.rapidapi.com", "x-rapidapi-key": FILEPURSUIT_API_KEY}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "success":
                        for item in data.get("files_found", [])[:3]:
                            raw_size = int(item.get("size_bytes", 0))
                            results.append({
                                "title": item.get("file_name", "Unknown File"),
                                "raw_size": raw_size,
                                "size": format_size(raw_size),
                                "link": item.get("file_link", ""),
                                "format": "🌐 Web DDL",
                                "source": "filepursuit"
                            })
    except: pass
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
                                "format": "🧲 Torrent",
                                "source": "torrent"
                            })
    except: pass
    return results

# ==========================================
# 🎛️ NEW SMART UI & ROUTER
# ==========================================

@app.on_message(filters.command("start"))
async def start_command(client, message):
    user_id = message.from_user.id
    if user_id in user_search_cache: del user_search_cache[user_id]
    if user_id in user_state: del user_state[user_id]
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Books & PDF", callback_data="cat_books")],
        [InlineKeyboardButton("🎬 Movies & Series", callback_data="cat_movies")],
        [InlineKeyboardButton("🎮 Games & Software", callback_data="cat_torrents")]
    ])
    
    await message.reply_text(
        "🚀 **Welcome to Ultimate Super-Bot Pro!**\n\n"
        "Aapko kya download karna hai? Niche ek category select karein, aur main uske best server se direct link nikal launga! 👇",
        reply_markup=keyboard
    )

@app.on_callback_query(filters.regex("^cat_"))
async def category_selection(client, callback_query):
    user_id = callback_query.from_user.id
    category = callback_query.data.split("_")[1]
    user_state[user_id] = category
    
    cat_names = {
        "books": "📚 Books & PDF",
        "movies": "🎬 Movies & Series",
        "torrents": "🎮 Games & Software"
    }
    
    await callback_query.message.edit_text(
        f"✅ Aapne **{cat_names[category]}** select kiya hai!\n\n"
        f"⌨️ Ab bas mujhe us cheez ka naam likh kar bhejiye (Jaise: *The Magic* ya *Inception*)."
    )

@app.on_message(filters.text & filters.private & ~filters.command("start"))
async def smart_search_router(client, message):
    user_id = message.from_user.id
    query = message.text
    
    if user_id not in user_state:
        await message.reply_text("⚠️ Pehle `/start` daba kar ek category chuniye!")
        return
        
    category = user_state[user_id]
    status_msg = await message.reply_text(f"⚡ **Searching for:** `{query}`...")
    
    results = []
    
    if category == "books":
        await status_msg.edit_text(f"📚 Libgen Server par `{query}` dhoondh raha hoon...")
        results = await search_libgen(query)
        
    elif category == "movies":
        await status_msg.edit_text(f"🎬 Telegram aur Web par `{query}` dhoondh raha hoon...")
        t_res = await search_telegram(query)
        f_res = await search_filepursuit(query)
        results = t_res + f_res
        
    elif category == "torrents":
        await status_msg.edit_text(f"🎮 Torrent Network par `{query}` dhoondh raha hoon...")
        results = await search_torrent(query)

    if results:
        user_search_cache[user_id] = {"results": results}
        text = f"✅ **Best Matches Found for:** `{query}`\n\n"
        buttons = []
        for i, res in enumerate(results[:5]):
            text += f"**{i+1}.** {res['title']}\n📁 {res['format']} | 💾 **{res['size']}**\n\n"
            buttons.append([InlineKeyboardButton(f"📥 Process File {i+1}", callback_data=f"leech_{i}")])
            
        await status_msg.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await status_msg.edit_text("❌ No results found. Try checking the spelling or change category.")

@app.on_callback_query(filters.regex("^leech_"))
async def process_delivery(client, callback_query):
    index = int(callback_query.data.split("_")[1])
    user_id = callback_query.from_user.id
    user_data = user_search_cache.get(user_id)
    
    if not user_data or "results" not in user_data:
        await callback_query.answer("⚠️ Session expired. Please search again.", show_alert=True)
        return
        
    res = user_data["results"][index]
    status_msg = await callback_query.message.reply_text("🔄 **Executing Direct Delivery Protocol...**")
    
    # 1. Libgen
    if res["source"] == "libgen" and res["raw_size"] <= MAX_DIRECT_SIZE:
        await status_msg.edit_text(f"📥 **Downloading Book/Document...**\n`{res['title']}`")
        loop = asyncio.get_event_loop()
        dl_link = await loop.run_in_executor(None, get_libgen_direct_link, res["md5"])
        if dl_link:
            filename = f"book_{index}.pdf"
            try:
                def fetch_file():
                    with cffi_requests.get(dl_link, stream=True, impersonate="chrome", timeout=30) as r:
                        r.raise_for_status()
                        with open(filename, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
                await loop.run_in_executor(None, fetch_file)
                await status_msg.edit_text("📤 **Uploading file to Telegram...**")
                await client.send_document(chat_id=user_id, document=filename, caption=f"✅ {res['title']}")
                os.remove(filename)
                await status_msg.delete()
                return
            except Exception as e:
                if os.path.exists(filename): os.remove(filename)
                await status_msg.edit_text(f"❌ Download failed: {e}")

    # 2. Telegram Drive
    elif res["source"] == "telegram":
        await status_msg.edit_text("📤 **Extracting from Telegram Drive...**")
        try:
            msg = await userbot.get_messages(res["chat_id"], res["msg_id"])
            await msg.copy(user_id, caption=f"✅ {res['title']}")
            await status_msg.delete()
            return
        except Exception as e:
            await status_msg.edit_text(f"❌ Failed: {e}")

    # 3. Web DDL
    elif res["source"] == "filepursuit":
        if res["raw_size"] > 0 and res["raw_size"] <= MAX_DIRECT_SIZE:
            await status_msg.edit_text(f"📥 **Downloading from Web DDL...**\n`{res['title']}`")
            loop = asyncio.get_event_loop()
            filename = f"file_{index}.bin"
            try:
                def fetch_web():
                    with requests.get(res["link"], stream=True, timeout=30) as r:
                        r.raise_for_status()
                        with open(filename, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
                await loop.run_in_executor(None, fetch_web)
                await status_msg.edit_text("📤 **Uploading to Telegram...**")
                await client.send_document(chat_id=user_id, document=filename, caption=f"✅ {res['title']}")
                os.remove(filename)
                await status_msg.delete()
                return
            except:
                if os.path.exists(filename): os.remove(filename)
        
        await status_msg.edit_text(
            f"🔗 **Direct Web Download Link:**\n\n"
            f"📁 **Name:** `{res['title']}`\n"
            f"📥 **Link:** [Click Here to Download]({res['link']})",
            disable_web_page_preview=True
        )

    # 4. Torrent Fallback
    elif res["source"] == "torrent":
        magnet = f"magnet:?xt=urn:btih:{res['hash']}&dn={urllib.parse.quote(res['title'])}"
        await status_msg.edit_text(
            f"🔗 **Magnet Link:**\n\n"
            f"📁 **Name:** `{res['title']}`\n"
            f"🧲 **Link:**\n`{magnet}`"
        )

# ==========================================
# 🌐 WEB SERVER & RUNNER
# ==========================================
async def health_check(request):
    return web.Response(text="Super-Bot Pro is Running with Smart Category Routing!")

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
    print("🚀 SUPER-BOT PRO LIVE WITH SMART ROUTING!")
    
    await idle()
    
    await app.stop()
    await userbot.stop()
    runner.cleanup()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
