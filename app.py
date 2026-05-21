import requests
import os
import random
import urllib.parse
import time
import logging
import sqlite3
from datetime import datetime, date
from flask import Flask, request

app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ---------- CONFIG ----------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
ADMIN_ID = 1917675707  # ခင်ဗျား User ID ထည့်ပါ

TOPICS_FILE = "topics.txt"
DB_FILE = "bot_data.db"

# ---------- DATABASE ----------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS posts 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT, date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings 
                 (key TEXT PRIMARY KEY, value TEXT)''')
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_enabled', 'true')")
    conn.commit()
    conn.close()
    logging.info("Database initialized")

def is_auto_enabled():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='auto_enabled'")
    result = c.fetchone()
    conn.close()
    return result[0] == 'true' if result else True

def set_auto_enabled(enabled):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE settings SET value=? WHERE key='auto_enabled'", ('true' if enabled else 'false',))
    conn.commit()
    conn.close()

def already_posted_today(topic):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM posts WHERE topic=? AND date=?", (topic, date.today().isoformat()))
    exists = c.fetchone() is not None
    conn.close()
    return exists

def mark_posted(topic):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO posts (topic, date) VALUES (?, ?)", (topic, date.today().isoformat()))
    conn.commit()
    conn.close()

def get_today_post_count():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM posts WHERE date=?", (date.today().isoformat(),))
    count = c.fetchone()[0]
    conn.close()
    return count

# ---------- TOPIC FUNCTIONS ----------
def load_topics():
    if os.path.exists(TOPICS_FILE):
        with open(TOPICS_FILE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    return ["📱 ဖုန်းအသစ်ဝယ်မယ်ဆို သိထားသင့်တဲ့အချက် ၅ ချက်", "🔋 Battery health ကောင်းအောင်ထိန်းသိမ်းနည်း"]

def save_topics(topics):
    with open(TOPICS_FILE, "w", encoding="utf-8") as f:
        for topic in topics:
            f.write(topic + "\n")

def add_topic(topic):
    topics = load_topics()
    if topic in topics:
        return False, "❌ Topic ရှိပြီးသား"
    topics.append(topic)
    save_topics(topics)
    return True, f"✅ Topic ထည့်ပြီး\n{topic}"

def remove_topic(index):
    topics = load_topics()
    if 1 <= index <= len(topics):
        removed = topics.pop(index - 1)
        save_topics(topics)
        return True, f"✅ ဖျက်ပြီး\n{removed}"
    return False, "❌ မှားနေတယ်"

def get_topics_list():
    topics = load_topics()
    if not topics:
        return "📭 Topic မရှိသေး"
    text = f"📚 Topic စာရင်း ({len(topics)} ခု)\n\n"
    for i, topic in enumerate(topics[:50]):
        text += f"{i+1}. {topic}\n"
    return text

# ---------- GEMINI ----------
def gemini_request(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={GEMINI_API_KEY}"
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    for _ in range(2):
        try:
            r = requests.post(url, json=data, timeout=60)
            if r.status_code == 200:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except:
            time.sleep(2)
    return "⚠️ AI Error"

def generate_post(topic):
    prompt = f"""မင်းက ဖုန်းဆိုင် page admin။ Facebook post ရေးပါ။
Topic: {topic}
စည်းကမ်း: emoji သုံး၊ bullet points 3-5 ခု၊ မြန်မာလို၊ စာလုံး 800 အောက်။
အဆုံးမှာ 📱 မင်းမင်းဖုန်းဆိုင် - ဖုန်းအသစ်အစစ်များသာ ထည့်"""
    return gemini_request(prompt)

def generate_image(prompt):
    safe = urllib.parse.quote(f"smartphone advertisement, {prompt}")
    url = f"https://image.pollinations.ai/prompt/{safe}?width=1024&height=1024"
    try:
        r = requests.get(url, timeout=60)
        return r.content if r.status_code == 200 else None
    except:
        return None

# ---------- TELEGRAM ----------
def send_telegram(text, chat_id):
    if not chat_id:
        return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
                      json={"chat_id": chat_id, "text": text[:4000]}, timeout=30)
    except Exception as e:
        logging.error(f"Send error: {e}")

def send_photo(image_bytes, caption, chat_id):
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
                      files={"photo": ("img.jpg", image_bytes)},
                      data={"chat_id": chat_id, "caption": caption[:200]}, timeout=60)
    except:
        pass

# ---------- WEBHOOK ----------
@app.route(f"/webhook/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def webhook():
    update = request.get_json()
    if "message" in update:
        msg = update["message"]
        chat_id = str(msg["chat"]["id"])
        text = msg.get("text", "")
        
        if chat_id != str(ADMIN_ID):
            return "Unauthorized", 403
        
        logging.info(f"Command: {text}")
        
        # ----- COMMANDS -----
        if text in ["/start", "/help"]:
            send_telegram("📱 Commands:\n/view_topics\n/add_topic [topic]\n/remove_topic [num]\n/write [topic]\n/write_topic [num]\n/random_post\n/status", chat_id)
        
        elif text == "/view_topics":
            send_telegram(get_topics_list(), chat_id)
        
        elif text.startswith("/add_topic"):
            topic = text.replace("/add_topic", "").strip()
            if not topic:
                send_telegram("❌ Topic ထည့်ပါ", chat_id)
            else:
                ok, msg = add_topic(topic)
                send_telegram(msg, chat_id)
        
        elif text.startswith("/remove_topic"):
            parts = text.split()
            if len(parts) != 2 or not parts[1].isdigit():
                send_telegram("❌ /remove_topic 2", chat_id)
            else:
                ok, msg = remove_topic(int(parts[1]))
                send_telegram(msg, chat_id)
        
        elif text.startswith("/write_topic"):
            parts = text.split()
            if len(parts) != 2 or not parts[1].isdigit():
                send_telegram("❌ /write_topic 1", chat_id)
            else:
                topics = load_topics()
                idx = int(parts[1])
                if 1 <= idx <= len(topics):
                    topic = topics[idx-1]
                    send_telegram(f"⏳ {topic}", chat_id)
                    try:
                        post = generate_post(topic)
                        send_telegram(post, chat_id)
                        img = generate_image(topic)
                        if img:
                            send_photo(img, topic, chat_id)
                    except Exception as e:
                        send_telegram(f"❌ {e}", chat_id)
                else:
                    send_telegram("❌ မရှိဘူး", chat_id)
        
        elif text.startswith("/write"):
            topic = text.replace("/write", "").strip()
            if not topic:
                send_telegram("❌ /write iPhone 16", chat_id)
            else:
                send_telegram(f"⏳ {topic}", chat_id)
                try:
                    post = generate_post(topic)
                    send_telegram(post, chat_id)
                    img = generate_image(topic)
                    if img:
                        send_photo(img, topic, chat_id)
                except Exception as e:
                    send_telegram(f"❌ {e}", chat_id)
        
        elif text == "/random_post":
            topics = load_topics()
            if not topics:
                send_telegram("❌ Topic မရှိဘူး", chat_id)
            else:
                topic = random.choice(topics)
                send_telegram(f"🎲 {topic}", chat_id)
                try:
                    post = generate_post(topic)
                    send_telegram(post, chat_id)
                    img = generate_image(topic)
                    if img:
                        send_photo(img, topic, chat_id)
                except Exception as e:
                    send_telegram(f"❌ {e}", chat_id)
        
        elif text == "/status":
            topics = load_topics()
            today_posts = get_today_post_count()
            send_telegram(f"🤖 Bot Status\nTopics: {len(topics)}\nToday: {today_posts}\n✅ Running", chat_id)
    
    return "OK", 200

# ---------- MAIN ----------
if __name__ == "__main__":
    init_db()  # <-- ဒါကို သေချာထည့်ထားပါ
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
