iimport os
mport telebot
import sqlite3
import time
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 5385495093
FORCE_CHANNELS = ["@techbittu69"]
REF_BONUS = 5
MIN_WITHDRAW = 50
# =========================================

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ================= DATABASE =================
def get_db():
    conn = sqlite3.connect("data.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn, conn.cursor()

conn, db = get_db()

db.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    referrals INTEGER DEFAULT 0,
    upi TEXT
)
""")

db.execute("""
CREATE TABLE IF NOT EXISTS promo (
    code TEXT PRIMARY KEY,
    amount INTEGER
)
""")

db.execute("""
CREATE TABLE IF NOT EXISTS withdraw (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount INTEGER,
    upi TEXT,
    status TEXT
)
""")

conn.commit()

# ================= HELPERS =================
def get_user(uid):
    conn, db = get_db()
    db.execute("SELECT balance, referrals, upi FROM users WHERE user_id=?", (uid,))
    row = db.fetchone()
    if not row:
        db.execute(
            "INSERT INTO users (user_id, balance, referrals, upi) VALUES (?,?,?,?)",
            (uid, 0, 0, None)
        )
        conn.commit()
        return 0, 0, None
    return row["balance"], row["referrals"], row["upi"]

# ================= FORCE JOIN =================
def is_joined(uid):
    for ch in FORCE_CHANNELS:
        try:
            if bot.get_chat_member(ch, uid).status in ["left", "kicked"]:
                return False
        except:
            return False
    return True

def force_join_kb():
    kb = InlineKeyboardMarkup()
    for ch in FORCE_CHANNELS:
        kb.add(InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{ch[1:]}"))
    kb.add(InlineKeyboardButton("✅ Joined", callback_data="check_join"))
    return kb

# ================= MENUS =================
def main_menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("👤 Profile", callback_data="profile"),
        InlineKeyboardButton("🔗 Refer & Earn", callback_data="refer"),
        InlineKeyboardButton("🎁 Promo Code", callback_data="promo"),
        InlineKeyboardButton("💸 Withdraw", callback_data="withdraw")
    )
    return kb

def back_menu():
    return InlineKeyboardMarkup().add(
        InlineKeyboardButton("⬅️ Back", callback_data="back")
    )

def withdraw_back_menu():
    return InlineKeyboardMarkup().add(
        InlineKeyboardButton("⬅️ Back", callback_data="withdraw_back")
    )

def admin_menu():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("⏳ Pending Withdrawals", callback_data="admin_pending"),
        InlineKeyboardButton("📜 Withdrawal History", callback_data="admin_history"),
        InlineKeyboardButton("🎁 Active Promo Codes", callback_data="admin_promos"),
        InlineKeyboardButton("⬅️ Back", callback_data="back")
    )
    return kb

# ================= START =================
@bot.message_handler(commands=["start"])
def start(message):
    uid = message.from_user.id
    if not is_joined(uid):
        bot.send_message(uid, "🚨 <b>Join channels first</b>", reply_markup=force_join_kb())
        return
    get_user(uid)
    bot.send_message(uid, "✅ <b>Welcome</b>", reply_markup=main_menu())

# ================= ADMIN =================
@bot.message_handler(commands=["admin"])
def admin_cmd(message):
    if message.from_user.id != ADMIN_ID:
        return
    bot.send_message(message.chat.id, "👑 <b>Admin Panel</b>", reply_markup=admin_menu())

@bot.message_handler(commands=["addpromo"])
def addpromo(message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) != 3 or not parts[2].isdigit():
        bot.send_message(message.chat.id, "Usage:\n/addpromo CODE AMOUNT")
        return
    code = parts[1].upper()
    amount = int(parts[2])
    conn, db = get_db()
    db.execute("INSERT OR REPLACE INTO promo VALUES (?,?)", (code, amount))
    conn.commit()
    bot.send_message(message.chat.id, f"✅ Promo {code} added (₹{amount})")

# ================= CALLBACK ROUTER =================
@bot.callback_query_handler(func=lambda c: True)
def router(call):
    uid = call.from_user.id
    data = call.data

    if data == "check_join":
        if is_joined(uid):
            bot.edit_message_text("✅ Access granted", uid, call.message.message_id, reply_markup=main_menu())
        else:
            bot.answer_callback_query(call.id, "Join all channels")

    elif data == "profile":
        bal, refs, upi = get_user(uid)
        bot.edit_message_text(
            f"👤 <b>Profile</b>\n\n💰 ₹{bal}\n👥 {refs}\n💳 {upi or 'Not set'}",
            uid, call.message.message_id, reply_markup=back_menu()
        )

    elif data == "refer":
        link = f"https://t.me/{bot.get_me().username}?start={uid}"
        bot.edit_message_text(
            f"🔗 <b>Your Link</b>\n\n{link}\n\n₹{REF_BONUS} per referral",
            uid, call.message.message_id, reply_markup=back_menu()
        )

    elif data == "promo":
        bot.edit_message_text("🎁 Send promo code:", uid, call.message.message_id, reply_markup=back_menu())
        bot.register_next_step_handler_by_chat_id(uid, redeem_promo)

    elif data == "withdraw":
        bal, _, upi = get_user(uid)
        if not upi:
            bot.edit_message_text("💳 Send your UPI ID:", uid, call.message.message_id, reply_markup=withdraw_back_menu())
            bot.register_next_step_handler_by_chat_id(uid, save_upi)
        elif bal < MIN_WITHDRAW:
            bot.answer_callback_query(call.id, "Minimum ₹50 required", True)
        else:
            bot.edit_message_text("💸 Send withdraw amount:", uid, call.message.message_id, reply_markup=withdraw_back_menu())
            bot.register_next_step_handler_by_chat_id(uid, withdraw_amount)

    elif data == "withdraw_back":
        bot.edit_message_text("🏠 Main Menu", uid, call.message.message_id, reply_markup=main_menu())

    elif data == "back":
        bot.edit_message_text("🏠 Main Menu", uid, call.message.message_id, reply_markup=main_menu())

    # ===== ADMIN LIST WITH APPROVE / REJECT =====
    elif data == "admin_pending" and uid == ADMIN_ID:
        conn, db = get_db()
        db.execute("SELECT * FROM withdraw WHERE status='pending'")
        rows = db.fetchall()
        if not rows:
            bot.edit_message_text("✅ No pending withdrawals", uid, call.message.message_id, reply_markup=admin_menu())
            return

        text = "⏳ <b>Pending Withdrawals</b>\n\n"
        kb = InlineKeyboardMarkup()

        for r in rows:
            text += f"ID:{r['id']} | ₹{r['amount']}\nUser:{r['user_id']}\nUPI:{r['upi']}\n\n"
            kb.add(
                InlineKeyboardButton(f"✅ Approve {r['id']}", callback_data=f"ap_{r['id']}"),
                InlineKeyboardButton(f"❌ Reject {r['id']}", callback_data=f"rej_{r['id']}")
            )

        kb.add(InlineKeyboardButton("⬅️ Back", callback_data="admin_back"))
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb)

    elif data == "admin_back":
        bot.edit_message_text("👑 Admin Panel", uid, call.message.message_id, reply_markup=admin_menu())

    elif data == "admin_history" and uid == ADMIN_ID:
        conn, db = get_db()
        db.execute("SELECT * FROM withdraw ORDER BY id DESC LIMIT 20")
        rows = db.fetchall()
        text = "📜 <b>Withdrawal History</b>\n\n"
        for r in rows:
            text += f"{r['user_id']} | ₹{r['amount']} | {r['status']}\n"
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=admin_menu())

    elif data == "admin_promos" and uid == ADMIN_ID:
        conn, db = get_db()
        db.execute("SELECT * FROM promo")
        rows = db.fetchall()
        if not rows:
            bot.edit_message_text("No promo codes", uid, call.message.message_id, reply_markup=admin_menu())
            return
        text = "🎁 <b>Active Promo Codes</b>\n\n"
        for r in rows:
            text += f"{r['code']} → ₹{r['amount']}\n"
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=admin_menu())

    # ===== APPROVE / REJECT =====
    elif data.startswith(("ap_", "rej_")) and uid == ADMIN_ID:
        wid = int(data.split("_")[1])
        conn, db = get_db()
        db.execute("SELECT * FROM withdraw WHERE id=?", (wid,))
        row = db.fetchone()
        if not row:
            return

        if data.startswith("ap_"):
            db.execute("UPDATE withdraw SET status='approved' WHERE id=?", (wid,))
            bot.send_message(row["user_id"], "✅ Withdraw approved")
        else:
            db.execute("UPDATE withdraw SET status='rejected' WHERE id=?", (wid,))
            db.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (row["amount"], row["user_id"]))
            bot.send_message(row["user_id"], "❌ Withdraw rejected (refunded)")

        conn.commit()
        bot.answer_callback_query(call.id, "Done")
        bot.edit_message_text("✅ Action completed", uid, call.message.message_id, reply_markup=admin_menu())

# ================= PROMO =================
def redeem_promo(message):
    conn, db = get_db()
    db.execute("SELECT amount FROM promo WHERE code=?", (message.text.strip(),))
    row = db.fetchone()
    if not row:
        bot.send_message(message.chat.id, "❌ Invalid promo", reply_markup=main_menu())
        return
    db.execute("DELETE FROM promo WHERE code=?", (message.text.strip(),))
    db.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (row["amount"], message.chat.id))
    conn.commit()
    bot.send_message(message.chat.id, f"✅ ₹{row['amount']} added", reply_markup=main_menu())

# ================= UPI =================
def is_valid_upi(upi: str) -> bool:
    upi = upi.strip()
    if "@" not in upi:
        return False
    if len(upi) < 6:
        return False
    if upi.count("@") != 1:
        return False
    name, bank = upi.split("@")
    if not name or not bank:
        return False
    return True

def save_upi(message):
    upi = message.text.strip()

    if not is_valid_upi(upi):
        bot.send_message(
            message.chat.id,
            "❌ <b>Invalid UPI ID</b>\n\nExample:\nname@paytm\nname@upi\nname@okaxis",
            parse_mode="HTML"
        )
        bot.register_next_step_handler_by_chat_id(message.chat.id, save_upi)
        return

    conn, db = get_db()
    db.execute("UPDATE users SET upi=? WHERE user_id=?", (upi, message.chat.id))
    conn.commit()

    bot.send_message(message.chat.id, "✅ <b>UPI saved successfully</b>", reply_markup=main_menu())

# ================= WITHDRAW =================
def withdraw_amount(message):
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Invalid amount", reply_markup=main_menu())
        return
    amt = int(message.text)
    bal, _, upi = get_user(message.chat.id)
    if amt > bal:
        bot.send_message(message.chat.id, "Insufficient balance", reply_markup=main_menu())
        return
    conn, db = get_db()
    db.execute("INSERT INTO withdraw (user_id, amount, upi, status) VALUES (?,?,?,?)",
               (message.chat.id, amt, upi, "pending"))
    db.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amt, message.chat.id))
    conn.commit()
    bot.send_message(message.chat.id, "⏳ Withdraw request sent", reply_markup=main_menu())

# ================= RUN =================
while True:
    try:
        print("🤖 Bot running...")
        bot.infinity_polling(timeout=20, long_polling_timeout=20)
    except Exception as e:
        print("⚠️ Restarting:", e)
        time.sleep(5)