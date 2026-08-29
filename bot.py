import os
import asyncio
import threading
import traceback
import urllib.parse
import requests
from bs4 import BeautifulSoup
from http.server import BaseHTTPRequestHandler, HTTPServer
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget

# --- Render ke liye Fix Web Server (Port 10000 & HEAD/GET Support) ---
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is alive and running!")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    server.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()
# ---------------------------------------------------

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

app = Client(
    "HybridDownloaderBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# User session memory
user_download_cache = {}
book_search_cache = {}

def format_size(size_in_bytes):
    try:
        size = int(size_in_bytes)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
    except (TypeError, ValueError):
        return "Unknown Size"

# ==========================================
# 📚 MODULE 1: BOOK & DOCUMENT FINDER
# ==========================================
def search_libgen(query):
    url = f"https://libgen.is/search.php?req={urllib.parse.quote(query)}&res=25&view=simple&phrase=1&column=def"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        res = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        table = soup.find('table', class_='c')
        results = []
        if not table: return results
        
        rows = table.find_all('tr')[1:] # Skip header
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 9: continue
            
            # Extract MD5 hash which is required for direct download
            md5_link = cols[2].find('a', href=True)
            if not md5_link or 'md5=' not in md5_link['href'].lower(): continue
            md5 = md5_link['href'].split('md5=')[-1][:32]
            
            author = cols[1].text.strip()
            title = cols[2].text.strip()
            # Clean title if it has extra tags
            if cols[2].find('a', title=True):
                title = cols[2].find('a', title=True).text.strip()
                
            size = cols[7].text.strip()
            ext = cols[8].text.strip().lower()
            
            # Sirf PDF aur ePub allow karein taaki iPhone par asani se khule
            if ext not in ['pdf', 'epub']: continue 
            
            results.append({'md5': md5, 'author': author, 'title': title, 'size': size, 'ext': ext})
            if len(results) >= 5: break # Top 5 results only
            
        return results
    except Exception as e:
        print(f"Libgen Search Error: {e}")
        return []

def get_libgen_direct_link(md5):
    url = f"http://library.lol/main/{md5}"
    try:
        res = requests.get(url, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        download_link = soup.find('a', string='GET')
        if download_link:
            return download_link['href']
    except Exception:
        pass
    return None

@app.on_message(filters.command("book", prefixes=["/", "."]))
async def search_book_command(client, message):
    query = message.text.split(maxsplit=1)
    if len(query) < 2:
        await message.reply_text("❌ **Usage:** `.book [Book Ka Naam]`\nExample: `.book atomic habits`")
        return
        
    search_term = query[1]
    status_msg = await message.reply_text(f"🔍 **Searching Library Genesis for:** `{search_term}`...")
    
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, search_libgen, search_term)
    
    if not results:
        await status_msg.edit_text("❌ **Koi book nahi mili.** Spelling check karein ya koi aur naam try karein.")
        return
        
    user_id = message.from_user.id
    book_search_cache[user_id] = results
    
    buttons = []
    text = f"📚 **Search Results for:** `{search_term}`\n\n"
    
    for i, book in enumerate(results):
        text += f"**{i+1}.** {book['title']}\n👤 {book['author']} | 💾 {book['size']} | 📄 {book['ext'].upper()}\n\n"
        buttons.append([InlineKeyboardButton(f"📥 Download Option {i+1} ({book['ext'].upper()})", callback_data=f"bkdl_{i}")])
        
    await status_msg.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex("^bkdl_"))
async def download_book(client, callback_query: CallbackQuery):
    index = int(callback_query.data.split("_")[1])
    user_id = callback_query.from_user.id
    
    if user_id not in book_search_cache:
        await callback_query.answer("⚠️ Session expired. Book wapas search karein.", show_alert=True)
        return
        
    book = book_search_cache[user_id][index]
    await callback_query.answer("Link generate kar raha hoon...", show_alert=False)
    
    status_msg = await callback_query.message.edit_text(f"🔄 **Direct link extract kar raha hoon:** `{book['title']}`...")
    
    loop = asyncio.get_event_loop()
    direct_link = await loop.run_in_executor(None, get_libgen_direct_link, book['md5'])
    
    if not direct_link:
        await status_msg.edit_text("❌ **Error:** Is book ka direct server link abhi down hai. Koi dusra option try karein.")
        return
        
    await status_msg.edit_text(f"📥 **Downloading file to server...**")
    
    os.makedirs("downloads", exist_ok=True)
    filename = f"downloads/{book['md5']}.{book['ext']}"
    
    try:
        def download_file_requests():
            with requests.get(direct_link, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
        
        await loop.run_in_executor(None, download_file_requests)
        
        await status_msg.edit_text("📤 **Uploading to Telegram...**")
        
        await client.send_document(
            chat_id=callback_query.message.chat.id,
            document=filename,
            file_name=f"{book['title']} - {book['author']}.{book['ext']}",
            caption=f"📚 **Title:** {book['title']}\n👤 **Author:** {book['author']}\n✅ **Downloaded via Hybrid Bot**"
        )
        
        if os.path.exists(filename):
            os.remove(filename)
        await status_msg.delete()
        
    except Exception as e:
        if os.path.exists(filename): os.remove(filename)
        await status_msg.edit_text(f"❌ **Download failed:** {e}")

# ==========================================
# 🎬 MODULE 2: VIDEO DOWNLOADER (Existing)
# ==========================================
@app.on_message(filters.command("start", prefixes=["/", "."]))
async def start_command(client, message):
    await message.reply_text(
        "👋 **Hybrid Bot is Awake!**\n\n"
        "1. **Video Download:** Kisi bhi website ka video link bhejein.\n"
        "2. **Book Download:** `.book [Naam]` likh kar bhejein."
    )

@app.on_message(filters.text & ~filters.command(["start", "book"], prefixes=["/", "."]))
async def handle_link(client, message):
    url = message.text.strip()
    
    if "t.me" in url:
        return
    if not url.startswith("http"):
        return

    status_message = await message.reply_text("🔍 **Fetching available formats and sizes...** Please wait.")

    ydl_opts = {
        'noplaylist': True,
        'cookiefile': 'cookies.txt',
        'impersonate': ImpersonateTarget(client='chrome'),
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        }
    }

    try:
        def extract_formats():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)

        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, extract_formats)

        if not info:
            await status_message.edit_text("❌ **Error:** Kisi bhi format ki jankari nahi mili.")
            return

        title = info.get('title', 'Unknown Video')
        formats = info.get('formats', [])
        
        available_formats = []
        for f in formats:
            if f.get('vcodec') != 'none' and f.get('height'):
                height = f.get('height')
                resolution_str = f"{height}p"
                
                filesize = f.get('filesize') or f.get('filesize_approx')
                available_formats.append({
                    'format_id': f.get('format_id'),
                    'resolution': resolution_str,
                    'ext': f.get('ext'),
                    'size': format_size(filesize),
                    'raw_size': filesize or 0,
                    'height': height
                })

        if not available_formats:
            available_formats.append({
                'format_id': 'best',
                'resolution': 'Best Available Quality',
                'ext': info.get('ext', 'mp4'),
                'size': 'Unknown Size',
                'raw_size': 0,
                'height': 0
            })

        seen_res = set()
        unique_formats = []
        available_formats.sort(key=lambda x: x['height'], reverse=True)
        
        for fmt in available_formats:
            if fmt['resolution'] not in seen_res:
                seen_res.add(fmt['resolution'])
                unique_formats.append(fmt)

        user_id = message.from_user.id
        user_download_cache[user_id] = {
            "url": url,
            "title": title
        }

        buttons = []
        for i, fmt in enumerate(unique_formats[:6]):
            btn_text = f"📺 {fmt['resolution']} ({fmt['ext'].upper()}) - {fmt['size']}"
            buttons.append([InlineKeyboardButton(btn_text, callback_data=f"dl_{i}_{fmt['format_id']}")])

        user_download_cache[user_id]["formats"] = unique_formats[:6]

        await status_message.edit_text(
            f"🎬 **Title:** `{title[:50]}`\n\n👇 **Select quality & size to download:**",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    except Exception as e:
        error_trace = traceback.format_exc()
        if len(error_trace) > 1500: error_trace = error_trace[-1500:]
        await status_message.edit_text(f"❌ **Error:**\n```python\n{error_trace}\n```")

@app.on_callback_query(filters.regex("^dl_"))
async def download_selected_format(client, callback_query: CallbackQuery):
    data_parts = callback_query.data.split("_")
    index = int(data_parts[1])
    format_id = data_parts[2]
    user_id = callback_query.from_user.id

    if user_id not in user_download_cache:
        await callback_query.answer("⚠️ Session expired. Please send the link again.", show_alert=True)
        return

    cached_data = user_download_cache[user_id]
    url = cached_data["url"]
    selected_fmt = cached_data["formats"][index]

    await callback_query.answer(f"Downloading {selected_fmt['resolution']}...", show_alert=False)
    status_message = await callback_query.message.edit_text(f"🔄 **Downloading {selected_fmt['resolution']}...** Please wait.")

    os.makedirs("downloads", exist_ok=True)
    
    ydl_opts = {
        'format': f"{format_id}+bestaudio/best" if format_id != 'best' else 'best',
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'noplaylist': True,
        'cookiefile': 'cookies.txt',
        'impersonate': ImpersonateTarget(client='chrome'),
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        }
    }

    try:
        def download_file():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info, ydl.prepare_filename(info)

        loop = asyncio.get_event_loop()
        info, filename = await loop.run_in_executor(None, download_file)

        if not os.path.exists(filename) or os.path.getsize(filename) < 1024 * 1024:
            if os.path.exists(filename): os.remove(filename)
            await status_message.edit_text("❌ **Error:** File download fail ho gayi ya size bahut chota hai.")
            return

        await status_message.edit_text("📤 **Uploading to Telegram...**")

        width = info.get('width')
        height = info.get('height')
        duration = info.get('duration')

        video_data = {
            "chat_id": callback_query.message.chat.id,
            "video": filename,
            "caption": f"✅ **Downloaded Successfully!**\n📺 Quality: {selected_fmt['resolution']}\n💾 Size: {selected_fmt['size']}",
            "supports_streaming": True
        }

        if width and height:
            video_data["width"] = int(width)
            video_data["height"] = int(height)
        if duration:
            video_data["duration"] = int(duration)

        await client.send_video(**video_data)

        if os.path.exists(filename):
            os.remove(filename)
        await status_message.delete()

    except Exception as e:
        error_trace = traceback.format_exc()
        if len(error_trace) > 1500: error_trace = error_trace[-1500:]
        await status_message.edit_text(f"❌ **Download Error:**\n```python\n{error_trace}\n```")

if __name__ == "__main__":
    print("Hybrid Bot is starting...")
    try:
        app.run()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(app.start())
        asyncio.get_event_loop().run_forever()
