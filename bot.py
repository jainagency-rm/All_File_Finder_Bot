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
user_search_states = {}

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

# --- REAL SEARCH ENGINES ---
async def search_google_drive(query):
    # Dummy delay to simulate search, aage chal kar ise Custom Search API se replace kar sakte hain
    await asyncio.sleep(1)
    return [] # Abhi ise khali rakhte hain taaki bot seedha Torrent API par jaye

async def search_torrent(query):
    # APIBay (The Pirate Bay API) ka use karke real data nikalna
    url = f"https://apibay.org/q.php?q={query}"
    results = []
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    # Agar id '0' aati hai, matlab koi result nahi mila
                    if data and isinstance(data, list) and data[0].get("id") != "0":
                        # Top 3 results nikalenge
                        for item in data[:3]:
                            results.append({
                                "title": item.get("name", "Unknown File"),
                                "size": format_size(item.get("size", 0)),
                                "seeders": item.get("seeders", "0"),
                                "hash": item.get("info_hash", "")
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
    if message.from_user.id in user_search_states:
        del user_search_states[message.from_user.id]
    welcome_text = "👋 **Welcome to All File Finder Bot!**\n\nSecure, fast, and automated cloud downloader. Please select a category below to start your search:"
    await message.reply_text(welcome_text, reply_markup=get_main_menu())

@app.on_callback_query()
async def handle_callbacks(client: Client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    
    if data == "main_menu":
        if user_id in user_search_states:
            del user_search_states[user_id]
        await callback_query.message.edit_text("📁 **Main Menu:** Please select a category:", reply_markup=get_main_menu())
    elif data in SUB_MENUS:
        await callback_query.message.edit_text("📂 **Sub-Category Selection:** Choose a specific section:", reply_markup=InlineKeyboardMarkup(SUB_MENUS[data]))
    elif data.startswith("sub_"):
        sub_category_name = data.replace("sub_", "").upper()
        user_search_states[user_id] = sub_category_name
        await callback_query.message.edit_text(f"🔍 **Selected Category:** `{sub_category_name}`\n\n⌨️ Now, please send the **name** of the item you want to search for:")
    elif data.startswith("leech_"):
        await callback_query.answer("☁️ Leeching feature is under development! File will be downloaded soon.", show_alert=True)

@app.on_message(filters.text & filters.private & ~filters.command("start"))
async def handle_search_query(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in user_search_states:
        await message.reply_text("⚠️ Please select a category from /start first.")
        return

    category = user_search_states[user_id]
    query = message.text

    status_msg = await message.reply_text(f"🔍 Searching real databases for **{query}**...\n\n🔄 Please wait...")
    
    # Torrent API Search
    torrent_results = await search_torrent(query)

    if torrent_results:
        # Pura message format karna
        result_text = f"✅ **Top Real Results for:** `{query}`\n\n"
        buttons = []
        
        for i, res in enumerate(torrent_results):
            result_text += f"**{i+1}.** {res['title']}\n"
            result_text += f"💾 **Size:** {res['size']} | 🌱 **Seeders:** {res['seeders']}\n\n"
            
            # Har file ke niche ek alag button taaki future me exact wo file leech ho sake
            buttons.append([InlineKeyboardButton(f"☁️ Leech File {i+1}", callback_data=f"leech_{i}")])

        result_text += "🛡 *Note: Click below to fetch the specific file via cloud.*"
        
        await status_msg.edit_text(result_text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await status_msg.edit_text("❌ Sorry, no results found on public trackers. Try a different name.")
    
    del user_search_states[user_id]

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
    print("Bot is successfully running with Real API!")
    await idle()
    await app.stop()
    await runner.cleanup()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except Exception as e:
        print(f"Critical Error: {e}")
