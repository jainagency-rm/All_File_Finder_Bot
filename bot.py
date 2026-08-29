import os
import asyncio
import aiohttp
import urllib.parse
import requests
from bs4 import BeautifulSoup
from aiohttp import web

from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery

# --- Credentials ---
try:
    API_ID = int(os.environ.get("API_ID", 0))
except ValueError:
    API_ID = 0
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

app = Client("AllFileFinderBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

user_search_cache = {}
MAX_DIRECT_SIZE = 1.5 * 1024 * 1024 * 1024  # 1.5 GB limit

def format_size(size_in_bytes):
    try:
        size = int(size_in_bytes)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
    except ValueError:
        return "Unknown Size"

# ==========================================
# 🔍 STAGE 1: DIRECT FILE SEARCH (LIBGEN)
# ==========================================
async def search_libgen(query):
    url = f"https://libgen.is/search.php?req={urllib.parse.quote(query)}&res=5&view=simple&phrase=1&column=def"
    headers = {"User-Agent": "Mozilla/5.0"}
    results = []
    try:
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, lambda: requests.get(url, headers=headers, timeout=15))
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
        print(f"Libgen Error: {e}")
    return results

def get_libgen_direct_link(md5):
    url = f"http://library.lol/main/{md5}"
    try:
        res = requests.get(url, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        dl_link = soup.find('a', string='GET')
        if dl_link: return dl_link['href']
    except: pass
    return None

# ==========================================
# 🔍 STAGE 3: TORRENT FALLBACK (APIBAY)
# ==========================================
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
    except Exception as e:
        print(f"API Error: {e}")
    return results

# ==========================================
# 🎛️ BOT HANDLERS & MENUS
# ==========================================
def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("📚 Books & Documents (< 1.5GB Direct)", callback_data="cat_books")],
        [InlineKeyboardButton("🎬 Movies & Media (Hybrid links)", callback_data="cat_movies")],
        [InlineKeyboardButton("💻 Software & Games (Hybrid links)", callback_data="cat_software")]
    ]
    return InlineKeyboardMarkup(keyboard)

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id in user_search_cache: del user_search_cache[user_id]
    await message.reply_text("👋 **Welcome to All File Finder!**\n\nSelect a category below to start:", reply_markup=get_main_menu())

@app.on_callback_query(filters.regex("^cat_"))
async def category_selection(client: Client, callback_query: CallbackQuery):
    cat = callback_query.data
    user_id = callback_query.from_user.id
    user_search_cache[user_id] = {"category": cat}
    
    cat_names = {"cat_books": "📚 Books", "cat_movies": "🎬 Movies", "cat_software": "💻 Software"}
    await callback_query.message.edit_text(f"🔍 **Selected:** `{cat_names[cat]}`\n\n⌨️ Send the **name** of the item you want to search:")

@app.on_message(filters.text & filters.private & ~filters.command("start"))
async def handle_search_query(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in user_search_cache or "category" not in user_search_cache[user_id]:
        await message.reply_text("⚠️ Please select a category from /start first.")
        return

    query = message.text
    cat = user_search_cache[user_id]["category"]
    status_msg = await message.reply_text(f"🔍 Searching databases for **{query}**...")
    
    results = []
    if cat == "cat_books":
        results = await search_libgen(query)
    else:
        results = await search_torrent(query)

    if results:
        user_search_cache[user_id]["results"] = results
        text = f"✅ **Results for:** `{query}`\n\n"
        buttons = []
        for i, res in enumerate(results):
            text += f"**{i+1}.** {res['title']}\n📁 {res['format']} | 💾 **{res['size']}**\n\n"
            buttons.append([InlineKeyboardButton(f"📥 Get File {i+1}", callback_data=f"leech_{i}")])
            
        await status_msg.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await status_msg.edit_text("❌ No results found. Try changing the spelling.")

@app.on_callback_query(filters.regex("^leech_"))
async def process_delivery(client: Client, callback_query: CallbackQuery):
    index = int(callback_query.data.split("_")[1])
    user_id = callback_query.from_user.id
    user_data = user_search_cache.get(user_id)
    
    if not user_data or "results" not in user_data:
        await callback_query.answer("⚠️ Session expired.", show_alert=True)
        return
        
    res = user_data["results"][index]
    status_msg = await callback_query.message.reply_text("🔄 **Analyzing delivery method...**")
    
    # 🎯 STAGE 1: Direct File Delivery (< 1.5 GB)
    if res["source"] == "libgen" and res["raw_size"] <= MAX_DIRECT_SIZE:
        await status_msg.edit_text(f"📥 **Downloading file (Under 1.5GB limit)...**\n`{res['title']}`")
        loop = asyncio.get_event_loop()
        dl_link = await loop.run_in_executor(None, get_libgen_direct_link, res["md5"])
        
        if dl_link:
            filename = f"{res['md5']}.pdf"
            try:
                def fetch_file():
                    with requests.get(dl_link, stream=True, timeout=30) as r:
                        r.raise_for_status()
                        with open(filename, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
                await loop.run_in_executor(None, fetch_file)
                await status_msg.edit_text("📤 **Uploading file to Telegram...**")
                await client.send_document(chat_id=user_id, document=filename, caption=f"✅ {res['title']}")
                os.remove(filename)
                await status_msg.delete()
            except Exception as e:
                await status_msg.edit_text(f"❌ **Download Failed:** {e}")
        else:
            await status_msg.edit_text("❌ No secure direct link found.")

    # 🎯 STAGE 3: Magnet Fallback
    elif res["source"] == "torrent":
        magnet = f"magnet:?xt=urn:btih:{res['hash']}&dn={urllib.parse.quote(res['title'])}"
        
        msg_text = f"📋 **File Delivery Protocol:**\n\n📁 **Name:** `{res['title']}`\n💾 **Size:** {res['size']}\n\n"
        if res["raw_size"] > MAX_DIRECT_SIZE:
            msg_text += f"⚠️ *File is larger than 1.5 GB limit. Direct download skipped to prevent crash.*\n\n"
            
        msg_text += f"🔗 **Magnet Link:**\n`{magnet}`\n\n💡 *Tip: Open this in Safari or Documents app via Seedr.cc for fast download.*"
        await status_msg.edit_text(msg_text)

# ==========================================
# 🌐 SERVER & LOOP FIX (The Engine)
# ==========================================
async def health_check(request):
    return web.Response(text="Bot is running with 3-Stage Logic!")

async def main():
    port = int(os.environ.get("PORT", 10000))
    
    server = web.Application()
    server.router.add_get('/', health_check)
    runner = web.AppRunner(server)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Web server started on port {port}")
    
    # 🚀 Pyrogram Start
    await app.start()
    print("Bot is successfully running with 3-Stage Logic!")
    
    # Kept alive gracefully
    await idle()
    
    await app.stop()
    await runner.cleanup()

if __name__ == "__main__":
    # Clean Loop Execution
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("Bot stopped.")
    except Exception as e:
        print(f"Error: {e}")
