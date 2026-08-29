import os
import asyncio
import aiohttp
from aiohttp import web

try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery

try:
    API_ID = int(os.environ.get("API_ID", 0))
except ValueError:import os
import asyncio
import aiohttp
import urllib.parse
import requests
from bs4 import BeautifulSoup
from aiohttp import web

# --- STRICT FIX FOR PYTHON RUNTIME LOOP ---
try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery

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
            
            # Convert size to bytes roughly for our logic
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
# (Stage 2 DDL logic will be inserted here next)
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
                                "format": "🧲 Torrent Fallback",
                                "source": "torrent"
                            })
    except Exception as e:
        print(f"API Error: {e}")
    return results

# ==========================================
# 🎛️ UI & MENUS
# ==========================================
def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("📚 Books & Documents (Direct Delivery)", callback_data="cat_books")],
        [InlineKeyboardButton("🎬 Movies & Media (DDL/Magnet)", callback_data="cat_movies")],
        [InlineKeyboardButton("💻 Software & Games (DDL/Magnet)", callback_data="cat_software")]
    ]
    return InlineKeyboardMarkup(keyboard)

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id in user_search_cache: del user_search_cache[user_id]
    await message.reply_text("👋 **Welcome to All File Finder!**\n\nSelect a category below:", reply_markup=get_main_menu())

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
    status_msg = await message.reply_text(f"🔍 Searching high-speed databases for **{query}**...")
    
    # 🚦 Category-Based Routing
    results = []
    if cat == "cat_books":
        results = await search_libgen(query)
    else:
        results = await search_torrent(query) # Will integrate Stage 2 (DDL) here next

    if results:
        user_search_cache[user_id]["results"] = results
        text = f"✅ **Results for:** `{query}`\n\n"
        buttons = []
        for i, res in enumerate(results):
            text += f"**{i+1}.** {res['title']}\n📁 {res['format']} | 💾 **{res['size']}**\n\n"
            buttons.append([InlineKeyboardButton(f"📥 Process File {i+1}", callback_data=f"leech_{i}")])
            
        await status_msg.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await status_msg.edit_text("❌ No safe results found. Try changing the spelling.")

@app.on_callback_query(filters.regex("^leech_"))
async def process_delivery(client: Client, callback_query: CallbackQuery):
    index = int(callback_query.data.split("_")[1])
    user_id = callback_query.from_user.id
    user_data = user_search_cache.get(user_id)
    
    if not user_data or "results" not in user_data:
        await callback_query.answer("⚠️ Session expired.", show_alert=True)
        return
        
    res = user_data["results"][index]
    status_msg = await callback_query.message.reply_text("🔄 **Analyzing routing protocol...**")
    
    # 🎯 STAGE 1: Direct Document Delivery (< 1.5 GB, Libgen Source)
    if res["source"] == "libgen" and res["raw_size"] <= MAX_DIRECT_SIZE:
        await status_msg.edit_text(f"📥 **Downloading direct file to server...**\n`{res['title']}`")
        loop = asyncio.get_event_loop()
        dl_link = await loop.run_in_executor(None, get_libgen_direct_link, res["md5"])
        
        if dl_link:
            filename = f"downloads/{res['md5']}.pdf"
            os.makedirs("downloads", exist_ok=True)
            try:
                def fetch_file():
                    with requests.get(dl_link, stream=True, timeout=30) as r:
                        r.raise_for_status()
                        with open(filename, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
                await loop.run_in_executor(None, fetch_file)
                await status_msg.edit_text("📤 **Uploading safely to Telegram...**")
                await client.send_document(chat_id=user_id, document=filename, caption=f"✅ {res['title']}")
                os.remove(filename)
                await status_msg.delete()
            except Exception as e:
                await status_msg.edit_text(f"❌ **Direct Delivery Failed:** {e}")
        else:
            await status_msg.edit_text("❌ No secure download link found for this document.")

    # 🎯 STAGE 3: Torrent Fallback (Magnet Link)
    elif res["source"] == "torrent":
        magnet = f"magnet:?xt=urn:btih:{res['hash']}&dn={urllib.parse.quote(res['title'])}"
        await status_msg.edit_text(
            f"📋 **File Delivery Protocol (Fallback):**\n\n"
            f"📁 **Name:** `{res['title']}`\n"
            f"💾 **Size:** {res['size']}\n\n"
            f"🔗 **Magnet Link:**\n`{magnet}`\n\n"
            f"💡 *Tip: Open this in Safari / Documents app via Seedr.cc.*"
        )

# ==========================================
# 🌐 WEB SERVER & RUNNER
# ==========================================
async def health_check(request):
    return web.Response(text="Bot is running perfectly!")

async def main():
    port = int(os.environ.get("PORT", 10000))
    server = web.Application()
    server.router.add_get('/', health_check)
    runner = web.AppRunner(server)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    await app.start()
    print("Bot is successfully running with 3-Stage Logic!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped.")
    API_ID = 0
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

app = Client("AllFileFinderBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

user_search_cache = {}

def format_size(size_in_bytes):
    try:
        size = int(size_in_bytes)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
    except ValueError:
        return "Unknown Size"

async def search_torrent(query):
    url = f"https://apibay.org/q.php?q={query}"
    results = []
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and isinstance(data, list) and data[0].get("id") != "0":
                        for item in data[:5]:
                            title = item.get("name", "Unknown File")
                            lower_title = title.lower()
                            raw_size = int(item.get("size", 0))
                            
                            ext = "📁 Other / Archive"
                            if any(k in lower_title for k in ['audiobook', '.mp3', '.m4b', 'podcast']):
                                ext = "🎵 Audiobook / Audio"
                            elif any(k in lower_title for k in ['.pdf', 'epub', 'mobi', 'cbz', 'novel']):
                                ext = "📚 E-Book / Document"
                            elif any(k in lower_title for k in ['.mp4', '.mkv', '1080p', '720p', 'web-dl', 'bluray']):
                                ext = "🎬 Video / Movie"
                            elif any(k in lower_title for k in ['.exe', '.apk', 'iso', 'repack']):
                                ext = "💻 Software / Game"

                            results.append({
                                "title": title,
                                "raw_size": raw_size,
                                "size": format_size(raw_size),
                                "seeders": item.get("seeders", "0"),
                                "hash": item.get("info_hash", ""),
                                "format": ext
                            })
    except Exception as e:
        print(f"API Error: {e}")
        
    return results

def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("🎬 Movies & Series", callback_data="cat_movies"), InlineKeyboardButton("📚 Books & Education", callback_data="cat_books")],
        [InlineKeyboardButton("💻 PC/Mac Software", callback_data="cat_software"), InlineKeyboardButton("🎮 Games (PC/Android)", callback_data="cat_games")],
        [InlineKeyboardButton("🎓 Paid Courses", callback_data="cat_courses"), InlineKeyboardButton("🎵 Audio & Music", callback_data="cat_audio")]
    ]
    return InlineKeyboardMarkup(keyboard)

SUB_MENUS = {
    "cat_movies": [[InlineKeyboardButton("Bollywood", callback_data="sub_bolly"), InlineKeyboardButton("Hollywood", callback_data="sub_holly")], [InlineKeyboardButton("Web Series", callback_data="sub_series"), InlineKeyboardButton("Anime", callback_data="sub_anime")], [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]],
    "cat_books": [[InlineKeyboardButton("Textbooks & Academic", callback_data="sub_academics"), InlineKeyboardButton("Novels & Fiction", callback_data="sub_novels")], [InlineKeyboardButton("Tech & Programming", callback_data="sub_techbooks"), InlineKeyboardButton("Comics & Manga", callback_data="sub_comics")], [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]],
    "cat_software": [[InlineKeyboardButton("Windows Apps", callback_data="sub_winapps"), InlineKeyboardButton("macOS Apps", callback_data="sub_macapps")], [InlineKeyboardButton("Design & Editing (Adobe)", callback_data="sub_design"), InlineKeyboardButton("Utilities & Antivirus", callback_data="sub_utils")], [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]],
    "cat_games": [[InlineKeyboardButton("PC Games (Repacks)", callback_data="sub_pcgames"), InlineKeyboardButton("Android Games (APKs)", callback_data="sub_apkgames")], [InlineKeyboardButton("Emulators & ROMs", callback_data="sub_roms")], [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]],
    "cat_courses": [[InlineKeyboardButton("Coding & Dev", callback_data="sub_devcourses"), InlineKeyboardButton("Business & Marketing", callback_data="sub_bizcourses")], [InlineKeyboardButton("Design & UI/UX", callback_data="sub_designcourses")], [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]],
    "cat_audio": [[InlineKeyboardButton("FLAC / Lossless", callback_data="sub_flac"), InlineKeyboardButton("MP3 Albums", callback_data="sub_mp3")], [InlineKeyboardButton("Audiobooks & Podcasts", callback_data="sub_audiobooks")], [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]]
}

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id in user_search_cache:
        del user_search_cache[user_id]
    welcome_text = "👋 **Welcome to All File Finder Bot!**\n\nSelect a category below to start your search:"
    await message.reply_text(welcome_text, reply_markup=get_main_menu())

@app.on_callback_query()
async def handle_callbacks(client: Client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    
    if data == "main_menu":
        if user_id in user_search_cache:
            del user_search_cache[user_id]
        await callback_query.message.edit_text("📁 **Main Menu:** Please select a category:", reply_markup=get_main_menu())
    elif data in SUB_MENUS:
        await callback_query.message.edit_text("📂 **Sub-Category Selection:** Choose a specific section:", reply_markup=InlineKeyboardMarkup(SUB_MENUS[data]))
    elif data.startswith("sub_"):
        sub_category_name = data.replace("sub_", "").upper()
        user_search_cache[user_id] = {"category": sub_category_name}
        await callback_query.message.edit_text(f"🔍 **Selected Category:** `{sub_category_name}`\n\n⌨️ Now, send the **name** of the item you want to search for:")
    elif data.startswith("leech_"):
        try:
            index = int(data.split("_")[1])
            user_data = user_search_cache.get(user_id)
            
            if not user_data or "results" not in user_data:
                await callback_query.answer("⚠️ Session expired. Please search again.", show_alert=True)
                return
                
            results_list = user_data["results"]
            if index >= len(results_list):
                await callback_query.answer("⚠️ Invalid selection.", show_alert=True)
                return
                
            selected_file = results_list[index]
            file_name = selected_file["title"]
            raw_size = selected_file["raw_size"]
            info_hash = selected_file["hash"]
            
            MAX_DIRECT_SIZE = 1.5 * 1024 * 1024 * 1024  # 1.5 GB in bytes
            
            status_msg = await callback_query.message.reply_text(
                f"🔍 **Analyzing file requirements...**\n\n📦 `{file_name}`\n💾 Size: {selected_file['size']}"
            )
            await callback_query.answer("Processing file...", show_alert=False)
            
            # Smart Priority Check
            if raw_size > 0 and raw_size <= MAX_DIRECT_SIZE:
                # Priority 1: Try Direct Download / Processing if available, 
                # Since Apibay only provides torrent hashes, we route to fallback or direct link generation.
                # Note: Apibay does not provide native DDLs, so we present the magnet link with size confirmation.
                pass

            # Fallback to Magnet Link since Apibay is a torrent indexer (No native DDLs)
            magnet_link = f"magnet:?xt=urn:btih:{info_hash}&dn={urllib_quote(file_name)}" if info_hash else "Not available"
            
            await status_msg.edit_text(
                f"📋 **File Details & Delivery Option:**\n\n"
                f"📁 **Name:** `{file_name}`\n"
                f"💾 **Size:** {selected_file['size']}\n\n"
                f"🔗 **Magnet / Direct Link:**\n`{magnet_link}`\n\n"
                f"💡 *Tip: Copy this link and open it in your iPhone's Documents app or Seedr.cc to start instant download.*"
            )
            
        except Exception as e:
            await callback_query.answer(f"Error: {str(e)}", show_alert=True)

# Simple url quote helper
import urllib.parse
def urllib_quote(text):
    return urllib.parse.quote(text)

@app.on_message(filters.text & filters.private & ~filters.command("start"))
async def handle_search_query(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in user_search_cache or "category" not in user_search_cache[user_id]:
        await message.reply_text("⚠️ Please select a category from /start first.")
        return

    query = message.text
    status_msg = await message.reply_text(f"🔍 Searching databases for **{query}**...")
    
    torrent_results = await search_torrent(query)

    if torrent_results:
        user_search_cache[user_id]["results"] = torrent_results
        
        result_text = f"✅ **Results for:** `{query}`\n\n"
        buttons = []
        
        for i, res in enumerate(torrent_results):
            result_text += f"**{i+1}.** {res['title']}\n"
            result_text += f"📁 **Type:** {res['format']} | 💾 **Size:** {res['size']} | 🌱 **Seeders:** {res['seeders']}\n\n"
            buttons.append([InlineKeyboardButton(f"📥 Get Link / File {i+1}", callback_data=f"leech_{i}")])

        result_text += "🛡 *Select an option above to get download links.*"
        await status_msg.edit_text(result_text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await status_msg.edit_text("❌ No results found. Try a different search term.")

async def health_check(request):
    return web.Response(text="Bot is running perfectly on Render!")

async def main():
    server = web.Application()
    server.router.add_get('/', health_check)
    runner = web.AppRunner(server)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    await app.start()
    print("Bot is successfully running!")
    await idle()
    await app.stop()
    await runner.cleanup()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except Exception as e:
        print(f"Critical Error: {e}")
