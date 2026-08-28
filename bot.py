import os
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery

# Verified Credentials from your setup
API_ID = 39172670
API_HASH = "4d9af38b80d07645a68ed98e2cbe27d4"
BOT_TOKEN = "8952239255:AAEKtDHWMtMv0AnWqfjGkZicr3pRy6Cwto"

app = Client("AllFileFinderBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Main Categories Keyboard
def get_main_menu():
    keyboard = [
        [
            InlineKeyboardButton("🎬 Movies & Series", callback_data="cat_movies"),
            InlineKeyboardButton("📚 Books & Education", callback_data="cat_books")
        ],
        [
            InlineKeyboardButton("💻 PC/Mac Software", callback_data="cat_software"),
            InlineKeyboardButton("🎮 Games (PC/Android)", callback_data="cat_games")
        ],
        [
            InlineKeyboardButton("🎓 Paid Courses", callback_data="cat_courses"),
            InlineKeyboardButton("🎵 Audio & Music", callback_data="cat_audio")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Sub-categories for precise filtering
SUB_MENUS = {
    "cat_movies": [
        [InlineKeyboardButton("Bollywood", callback_data="sub_bolly"), InlineKeyboardButton("Hollywood", callback_data="sub_holly")],
        [InlineKeyboardButton("Web Series", callback_data="sub_series"), InlineKeyboardButton("Anime", callback_data="sub_anime")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]
    ],
    "cat_books": [
        [InlineKeyboardButton("Textbooks & Academic", callback_data="sub_academics"), InlineKeyboardButton("Novels & Fiction", callback_data="sub_novels")],
        [InlineKeyboardButton("Tech & Programming", callback_data="sub_techbooks"), InlineKeyboardButton("Comics & Manga", callback_data="sub_comics")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]
    ],
    "cat_software": [
        [InlineKeyboardButton("Windows Apps", callback_data="sub_winapps"), InlineKeyboardButton("macOS Apps", callback_data="sub_macapps")],
        [InlineKeyboardButton("Design & Editing (Adobe)", callback_data="sub_design"), InlineKeyboardButton("Utilities & Antivirus", callback_data="sub_utils")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]
    ],
    "cat_games": [
        [InlineKeyboardButton("PC Games (Repacks)", callback_data="sub_pcgames"), InlineKeyboardButton("Android Games (APKs)", callback_data="sub_apkgames")],
        [InlineKeyboardButton("Emulators & ROMs", callback_data="sub_roms")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]
    ],
    "cat_courses": [
        [InlineKeyboardButton("Coding & Dev", callback_data="sub_devcourses"), InlineKeyboardButton("Business & Marketing", callback_data="sub_bizcourses")],
        [InlineKeyboardButton("Design & UI/UX", callback_data="sub_designcourses")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]
    ],
    "cat_audio": [
        [InlineKeyboardButton("FLAC / Lossless", callback_data="sub_flac"), InlineKeyboardButton("MP3 Albums", callback_data="sub_mp3")],
        [InlineKeyboardButton("Audiobooks & Podcasts", callback_data="sub_audiobooks")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]
    ]
}

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    welcome_text = (
        "👋 **Welcome to All File Finder Bot!**\n\n"
        "Secure, fast, and automated cloud downloader. "
        "Please select a category below to start your search:"
    )
    await message.reply_text(welcome_text, reply_markup=get_main_menu())

@app.on_callback_query()
async def handle_callbacks(client: Client, callback_query: CallbackQuery):
    data = callback_query.data
    
    if data == "main_menu":
        await callback_query.message.edit_text(
            "📁 **Main Menu:** Please select a category:",
            reply_markup=get_main_menu()
        )
    elif data in SUB_MENUS:
        await callback_query.message.edit_text(
            "📂 **Sub-Category Selection:** Choose a specific section:",
            reply_markup=InlineKeyboardMarkup(SUB_MENUS[data])
        )
    elif data.startswith("sub_"):
        sub_category_name = data.replace("sub_", "").upper()
        await callback_query.message.edit_text(
            f"🔍 **Selected:** `{sub_category_name}`\n\n"
            "Now, please send the **name** of the item you want to search for (e.g., *Interstellar*, *Photoshop*, *Python Guide*):"
        )

if __name__ == "__main__":
    print("Bot is running...")
    app.run()
