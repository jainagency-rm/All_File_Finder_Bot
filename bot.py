import os
import asyncio
import aiohttp
from aiohttp import web

# --- STRICT FIX FOR PYROGRAM ON RENDER (PYTHON 3.14) ---
try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery

# --- Fetching Credentials Safely ---
try:
    API_ID = int(os.environ.get("API_ID", 0))
except ValueError:
    API_ID = 0
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

app = Client("AllFileFinderBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# User search memory to store results for leeching
user_search_cache = {}

# --- HELPER FUNCTION: Convert Bytes to MB/GB ---
def format_size(size_in_bytes):
    try:
        size = int(size_in_bytes)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
    except ValueError:
        return "Unknown Size"

# --- REAL SEARCH ENGINE WITH SMART FORMAT DETECTION ---
async def search_torrent(query):
    url = f"https://apibay.org/q.php?q={query}"
    results = []
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and isinstance(data, list) and data[0].get("id") != "0":
                        for item in data[:3]:
                            title = item.get("name", "Unknown File")
                            
                            # Smart Format Detector based on title keywords
                            ext = "Unknown Format"
                            lower_title = title.lower()
                            if any(k in lower_title for k in ['.pdf', 'pdf', 'book', 'novel']):
                                ext = "📄 PDF / Document"
                            elif any(k in lower_title for k in ['.mp3', 'audiobook', 'm4b', 'podcast']):
                                ext = "🎵 Audiobook / Audio"
                            elif any(k in lower_title for k in ['.epub', 'mobi', 'cbz']):
                                ext = "📚 E-Book / Comic"
                            elif any(k in lower_title for k in ['.mp4', '.mkv', '1080p', '720p', 'web-dl', 'bluray']):
                                ext = "🎬 Video / Movie"
                            elif any(k in lower_title for k in ['.exe', '.apk', 'iso', 'repack']):
                                ext = "💻 Software / Game"

                            results.append({
                                "title": title,
                                "size": format_size(item.get("size", 0)),
                                "seeders": item.get("seeders", "0"),
                                "hash": item.get("info_hash", ""),
                                "format": ext
                            })
    except Exception as e:
        print(f"API Error: {e}")
        
    return results

# --- UI & LOGIC ---
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

# --- BOT HANDLERS ---
@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id in user_search_cache:
        del user_search_cache[user_id]
    welcome_text = "👋 **Welcome to All File Finder Bot!**\n\nSecure, fast, and automated cloud downloader. Please select a category below to start your search:"
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
        await callback_query.message.edit_text(f"🔍 **Selected Category:** `{sub_category_name}`\n\n⌨️ Now, please send the **name** of the item you want to search for:")
    elif data.startswith("leech_"):
        try:
            index = int(data.split("_")[1])
            user_data = user_search_cache.get(user_id)
            if not user_data or "results" not in user_data:
                await callback_query.answer("⚠️ Session expired. Please search again.", show_alert=True)
                return
                
            selected_file = user_data["results"][index]
            file_name = selected_file["title"]
            info_hash = selected_file["hash"]
            
            # Generate Magnet Link
            magnet_link = f"magnet:?xt=urn:btih:{info_hash}&dn={file_name.replace(' ', '+')}"
            
            await callback_query.message.reply_text(
                f"⚡ **Cloud Leech Initiated!**\n\n"
                f"📦 **File:** {file_name}\n"
                f"💾 **Size:** {selected_file['size']}\n\n"
                f"🔗 **Magnet Link Generated:**\n`{magnet_link}`\n\n"
                f"⚙️ *Server is preparing to download and pack this file for Telegram delivery...*",
            )
            await callback_query.answer("Leech task started!", show_alert=False)
        except Exception as e:
            await callback_query.answer(f"Error: {str(e)}", show_alert=True)

@app.on_message(filters.text & filters.private & ~filters.command("start"))
async def handle_search_query(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in user_search_cache or "category" not in user_search_cache[user_id]:
        await message.reply_text("⚠️ Please select a category from /start first.")
        return

    query = message.text
    status_msg = await message.reply_text(f"🔍 Searching databases for **{query}**...\n\n🔄 Inspecting formats and seeders...")
    
    torrent_results = await search_torrent(query)

    if torrent_results:
        # Cache results in user memory for leeching reference
        user_search_cache[user_id]["results"] = torrent_results
        
        result_text = f"✅ **Results for:** `{query}`\n\n"
        buttons = []
        
        for i, res in enumerate(torrent_results):
            result_text += f"**{i+1}.** {res['title']}\n"
            result_text += f"📁 **Type:** {res['format']} | 💾 **Size:** {res['size']} | 🌱 **Seeders:** {res['seeders']}\n\n"
            buttons.append([InlineKeyboardButton(f"☁️ Leech File {i+1}", callback_data=f"leech_{i}")])

        result_text += "🛡 *Click below to start cloud downloading.*"
        await status_msg.edit_text(result_text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await status_msg.edit_text("❌ Sorry, no results found. Try a different name.")

# --- AIOHTTP WEB SERVER & ASYNC LOOP ---
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
    print("Bot is successfully running with Smart Format Detection!")
    await idle()
    await app.stop()
    await runner.cleanup()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except Exception as e:
        print(f"Critical Error: {e}")
