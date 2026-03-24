import sqlite3
import requests
import json
import io
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# --- CONFIGURATION ---
TOKEN = '8184247502:AAGvaZ6dwmuyEdb_qMs_BBDmlDiq98U7Y7M'
ADMIN_ID = 6328650912 
API_URL = "https://ffgestapisrc.vercel.app/gen"
CHANNELS = ["@tufan95aura"] # Add your channel username here

# States
REGION, NAME, COUNT, REDEEM_INP, BCAST, ADD_ID, ADD_AMT, PROMO_CODE, PROMO_VAL, PROMO_LIMIT = range(10)

# Logging (To prevent bot from stopping on errors)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- DATABASE SETUP ---
def get_db_connection():
    conn = sqlite3.connect('kamod_bot.db', timeout=30, check_same_thread=False)
    conn.execute('PRAGMA journal_mode=WAL;') 
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 20, referred_by INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS promo_codes 
                 (code TEXT PRIMARY KEY, value INTEGER, uses_left INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS redeemed_history 
                 (user_id INTEGER, code TEXT, PRIMARY KEY (user_id, code))''')
    conn.commit()
    conn.close()

def get_user_data(user_id):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        res = c.fetchone()
        conn.close()
        return res[0] if res else 0
    except: return 0

def update_balance(user_id, amount):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        conn.close()
    except: pass

# --- KEYBOARDS ---
def get_main_keyboard():
    keyboard = [
        ["🔥 GENERATE ACCOUNTS"],
        ["💰 BALANCE", "🎁 REDEEM"],
        ["👤 OWNER", "👥 REFER"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_keyboard():
    keyboard = [
        ["📊 STATS", "📢 BROADCAST"],
        ["➕ ADD COINS", "🎟 CREATE PROMO"],
        ["🏠 EXIT ADMIN"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- FORCE JOIN ---
async def is_subscribed(bot, user_id):
    if user_id == ADMIN_ID: return True
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in ['left', 'kicked']: return False
        except: return False
    return True

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        init_db()
        
        # New user & referral
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        if not c.fetchone():
            ref_id = int(context.args[0]) if context.args and context.args[0].isdigit() else None
            if ref_id and ref_id != user_id:
                update_balance(ref_id, 20)
                try: await context.bot.send_message(chat_id=ref_id, text="🎁 Referral Bonus! You got +20 coins.")
                except: pass
            c.execute("INSERT INTO users (user_id, balance, referred_by) VALUES (?, ?, ?)", (user_id, 20, ref_id))
            conn.commit()
        conn.close()

        if not await is_subscribed(context.bot, user_id):
            join_btn = [[InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNELS[0].replace('@','')}")],
                        [InlineKeyboardButton("✅ Verified", callback_data="verify")]]
            await update.message.reply_text("❌ Please join our channel first to use this bot!", reply_markup=InlineKeyboardMarkup(join_btn))
            return

        await update.message.reply_text(f"👋 Welcome to Account Generator!\n💰 Your Balance: `{get_user_data(user_id)}` coins.", reply_markup=get_main_keyboard(), parse_mode="Markdown")
    except Exception as e: logging.error(f"Error in start: {e}")

# --- ADMIN FUNCTIONS ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("🛠 **ADMIN PANEL ACTIVATED**\nUse the buttons below to manage the bot.", reply_markup=get_admin_keyboard(), parse_mode="Markdown")

async def admin_handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if update.effective_user.id != ADMIN_ID: return

    if text == "📊 STATS":
        conn = get_db_connection()
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        conn.close()
        await update.message.reply_text(f"📊 **Total Users:** `{total}`", parse_mode="Markdown")
    
    elif text == "📢 BROADCAST":
        await update.message.reply_text("Enter message to broadcast (or type /cancel):")
        return BCAST

    elif text == "➕ ADD COINS":
        await update.message.reply_text("Enter User ID to add coins:")
        return ADD_ID

    elif text == "🎟 CREATE PROMO":
        await update.message.reply_text("Enter Promo Code name (e.g., FREE50):")
        return PROMO_CODE

    elif text == "🏠 EXIT ADMIN":
        await update.message.reply_text("Exited Admin Mode.", reply_markup=get_main_keyboard())
        return ConversationHandler.END

# --- CONVERSATION HANDLERS (ADMIN & USER) ---
async def bcast_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    if msg == "/cancel": return ConversationHandler.END
    conn = get_db_connection()
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    await update.message.reply_text("🚀 Sending messages...")
    count = 0
    for user in users:
        try:
            await context.bot.send_message(chat_id=user[0], text=f"📢 **NOTIFICATION**\n\n{msg}", parse_mode="Markdown")
            count += 1
            await asyncio.sleep(0.05)
        except: continue
    await update.message.reply_text(f"✅ Broadcast sent to {count} users.")
    return ConversationHandler.END

async def get_add_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['target_id'] = update.message.text
    await update.message.reply_text("Enter amount of coins to add:")
    return ADD_AMT

async def get_add_amt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amt = int(update.message.text)
        uid = int(context.user_data['target_id'])
        update_balance(uid, amt)
        await update.message.reply_text(f"✅ Success! Added {amt} coins to {uid}.")
        try: await context.bot.send_message(chat_id=uid, text=f"💰 Admin added {amt} coins to your balance!")
        except: pass
    except: await update.message.reply_text("❌ Error: Use numbers only.")
    return ConversationHandler.END

async def get_promo_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['p_name'] = update.message.text
    await update.message.reply_text("Enter coin value for this code:")
    return PROMO_VAL

async def get_promo_val(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['p_val'] = update.message.text
    await update.message.reply_text("Enter user limit for this code:")
    return PROMO_LIMIT

async def get_promo_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        code = context.user_data['p_name']
        val = int(context.user_data['p_val'])
        limit = int(update.message.text)
        conn = get_db_connection()
        conn.execute("INSERT OR REPLACE INTO promo_codes VALUES (?, ?, ?)", (code, val, limit))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ **Promo Created!**\nCode: `{code}`\nValue: `{val}`\nLimit: `{limit}`", parse_mode="Markdown")
    except: await update.message.reply_text("❌ Error in data.")
    return ConversationHandler.END

# --- USER GENERATION PROCESS ---
async def user_btn_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, user_id = update.message.text, update.effective_user.id
    if text == "🔥 GENERATE ACCOUNTS":
        if get_user_data(user_id) <= 0:
            await update.message.reply_text("❌ Low Balance!")
            return ConversationHandler.END
        await update.message.reply_text("🌍 Enter Region (IND, BRA, ID):")
        return REGION
    elif text == "💰 BALANCE":
        await update.message.reply_text(f"💰 Your Balance: `{get_user_data(user_id)}` Coins", parse_mode="Markdown")
    elif text == "🎁 REDEEM":
        await update.message.reply_text("🎁 Enter your promo code:")
        return REDEEM_INP
    elif text == "👤 OWNER":
        await update.message.reply_text("👤 Owner: @kamod90")
    elif text == "👥 REFER":
        b_name = (await context.bot.get_me()).username
        await update.message.reply_text(f"🔗 **Referral Link:**\n`https://t.me/{b_name}?start={user_id}`\n\nGet **20 coins** per refer!", parse_mode="Markdown")

async def process_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Logic for Region -> Name -> Count (Already handled in states)
    pass

async def get_region(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['reg'] = update.message.text
    await update.message.reply_text("👤 Enter Name:")
    return NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nam'] = update.message.text
    await update.message.reply_text("🔢 How many accounts?")
    return COUNT

async def get_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        count = int(update.message.text)
        user_id = update.effective_user.id
        if count > get_user_data(user_id) or count <= 0:
            await update.message.reply_text("❌ Invalid count or low balance.")
            return ConversationHandler.END
        
        m = await update.message.reply_text(f"🚀 Generating {count} accounts...")
        final_list = []
        for i in range(count):
            try:
                r = requests.get(API_URL, params={'name': context.user_data['nam'], 'region': context.user_data['reg'], 'count': 1}, timeout=10)
                if r.status_code == 200: final_list.append(r.json())
                await asyncio.sleep(0.5)
            except: continue
        
        update_balance(user_id, -count)
        f_io = io.BytesIO(json.dumps(final_list, indent=4).encode())
        f_io.name = "accounts.json"
        await update.message.reply_document(document=f_io, caption=f"✅ Generated {len(final_list)} accounts!")
    except: pass
    return ConversationHandler.END

async def handle_redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code, user_id = update.message.text.strip(), update.effective_user.id
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT 1 FROM redeemed_history WHERE user_id = ? AND code = ?", (user_id, code))
    if c.fetchone():
        await update.message.reply_text("❌ You already used this code!")
    else:
        c.execute("SELECT value, uses_left FROM promo_codes WHERE code = ?", (code,))
        res = c.fetchone()
        if res and res[1] > 0:
            c.execute("UPDATE promo_codes SET uses_left = uses_left - 1 WHERE code = ?", (code,))
            c.execute("INSERT INTO redeemed_history VALUES (?, ?)", (user_id, code))
            conn.commit()
            update_balance(user_id, res[0])
            await update.message.reply_text(f"✅ Success! +{res[0]} coins added.")
        else: await update.message.reply_text("❌ Invalid or Expired Code!")
    conn.close()
    return ConversationHandler.END

# --- GLOBAL ERROR HANDLER ---
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"Update {update} caused error {context.error}")

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex('^(🔥 GENERATE ACCOUNTS|🎁 REDEEM)$'), user_btn_handler),
            MessageHandler(filters.Regex('^(📢 BROADCAST|➕ ADD COINS|🎟 CREATE PROMO)$'), admin_handle_buttons)
        ],
        states={
            REGION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_region)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_count)],
            REDEEM_INP: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_redeem)],
            BCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, bcast_msg)],
            ADD_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_add_id)],
            ADD_AMT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_add_amt)],
            PROMO_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_promo_name)],
            PROMO_VAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_promo_val)],
            PROMO_LIMIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_promo_limit)],
        },
        fallbacks=[CommandHandler('start', start), MessageHandler(filters.Regex('^🏠 EXIT ADMIN$'), admin_handle_buttons)],
        allow_reentry=True
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, user_btn_handler))
    app.add_handler(MessageHandler(filters.ALL, lambda u, c: None)) # Handle wrong inputs
    app.add_error_handler(error_handler)
    
    print("Bot is running...")
    app.run_polling()

if __name__ == '__main__': main()