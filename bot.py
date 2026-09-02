from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Ek naya dictionary bot ko yaad rakhne ke liye ki user ne kya select kiya
user_state = {}

@app.on_message(filters.command("start"))
async def start_command(client, message):
    user_id = message.from_user.id
    
    # Purana kooda saaf karna
    if user_id in user_search_cache: del user_search_cache[user_id]
    if user_id in user_state: del user_state[user_id]
    
    # 🎛️ Naye chamakte hue buttons
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Books & PDF", callback_data="cat_books")],
        [InlineKeyboardButton("🎬 Movies (YTS)", callback_data="cat_movies")],
        [InlineKeyboardButton("🐼 Anime (Nyaa)", callback_data="cat_anime")],
        [InlineKeyboardButton("🎮 Games & Software", callback_data="cat_torrents")]
    ])
    
    await message.reply_text(
        "🚀 **Welcome to Ultimate Super-Bot Pro!**\n\n"
        "Aapko kya download karna hai? Niche ek category select karein, aur main uske best server se direct link nikal launga! 👇",
        reply_markup=keyboard
    )

# 👇 Jab user kisi button par click karega
@app.on_callback_query(filters.regex("^cat_"))
async def category_selection(client, callback_query):
    user_id = callback_query.from_user.id
    category = callback_query.data.split("_")[1] # books, movies, anime, ya torrents
    
    # Bot ko yaad dilana ki user ne kya chuna
    user_state[user_id] = category
    
    cat_names = {
        "books": "📚 Books",
        "movies": "🎬 Movies",
        "anime": "🐼 Anime",
        "torrents": "🎮 Games & Software"
    }
    
    await callback_query.message.edit_text(
        f"✅ Aapne **{cat_names[category]}** select kiya hai!\n\n"
        f"⌨️ Ab bas mujhe us cheez ka naam likh kar bhejiye (Jaise: *The Magic* ya *Inception*)."
    )

# 👇 Naya Smart Router (Jo sirf selected category mein dhoondhega)
@app.on_message(filters.text & filters.private & ~filters.command("start"))
async def smart_search_router(client, message):
    user_id = message.from_user.id
    query = message.text
    
    if user_id not in user_state:
        await message.reply_text("⚠️ Pehle `/start` daba kar ek category chuniye!")
        return
        
    category = user_state[user_id]
    status_msg = await message.reply_text(f"⚡ **Searching for:** `{query}`...")
    
    # Yahan hum engines ko alag-alag daudayenge
    results = []
    if category == "books":
        await status_msg.edit_text(f"📚 Libgen aur Archives mein `{query}` dhoondh raha hoon...")
        # results = await search_libgen(query) # (Aage add karenge)
        
    elif category == "movies":
        await status_msg.edit_text(f"🎬 YTS Database mein `{query}` dhoondh raha hoon...")
        # results = await search_yts(query) # (Aage add karenge)
        
    elif category == "anime":
        await status_msg.edit_text(f"🐼 Nyaa Database mein `{query}` dhoondh raha hoon...")
        # results = await search_nyaa(query) # (Aage add karenge)
        
    elif category == "torrents":
        await status_msg.edit_text(f"🎮 1337x par `{query}` dhoondh raha hoon...")
        # results = await search_1337x(query) # (Aage add karenge)
        
    # Abhi ke liye bas test message
    await status_msg.edit_text("⚙️ UI Setup ho gaya! Ab backend lagana baaki hai.")
