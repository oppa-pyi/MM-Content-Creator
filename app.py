import requests
import os
import random
import urllib.parse
import time
import logging
import sqlite3
from datetime import datetime, date
from flask import Flask, request
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# ---------------- LOGGING ---------------- #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ---------------- CONFIG ---------------- #
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
ADMIN_ID = 1917675707  # ခင်ဗျားရဲ့ Telegram User ID ထည့်ပါ

TOPICS_FILE = "topics.txt"
DB_FILE = "bot_data.db"

# ---------------- DATABASE FUNCTIONS ---------------- #
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
    today = date.today().isoformat()
    c.execute("SELECT * FROM posts WHERE topic=? AND date=?", (topic, today))
    exists = c.fetchone() is not None
    conn.close()
    return exists

def mark_posted(topic):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    today = date.today().isoformat()
    c.execute("INSERT INTO posts (topic, date) VALUES (?, ?)", (topic, today))
    conn.commit()
    conn.close()

def get_today_post_count():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    today = date.today().isoformat()
    c.execute("SELECT COUNT(*) FROM posts WHERE date=?", (today,))
    count = c.fetchone()[0]
    conn.close()
    return count

# ---------------- TOPIC FUNCTIONS ---------------- #
def load_topics():
    if os.path.exists(TOPICS_FILE):
        with open(TOPICS_FILE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    return [
        "📱 ဖုန်းအသစ်ဝယ်မယ်ဆို သိထားသင့်တဲ့အချက် ၅ ချက်",
        "🔋 Battery health ကောင်းအောင်ထိန်းသိမ်းနည်း",
        "📸 Camera ကောင်းတဲ့ဖုန်းရွေးနည်း",
    ]

def save_topics(topics):
    with open(TOPICS_FILE, "w", encoding="utf-8") as f:
        for topic in topics:
            f.write(topic + "\n")

def add_topic(topic):
    topics = load_topics()
    if topic in topics:
        return False, "❌ Topic ရှိပြီးသားပါ"
    topics.append(topic)
    save_topics(topics)
    return True, f"✅ Topic ထည့်ပြီးပါပြီ\n\n📌 {topic}"

def remove_topic(index):
    topics = load_topics()
    if 1 <= index <= len(topics):
        removed = topics.pop(index - 1)
        save_topics(topics)
        return True, f"✅ Topic ဖျက်ပြီးပါပြီ\n\n❌ {removed}"
    return False, "❌ Invalid topic number"

def get_topics_list_text():
    topics = load_topics()
    if not topics:
        return "📭 Topic မရှိသေးပါ"
    text = f"📚 Topic List ({len(topics)} ခု)\n\n"
    for i, topic in enumerate(topics[:50]):
        text += f"{i+1}. {topic}\n"
    return text

# ---------------- GEMINI ---------------- #
def gemini_text_request(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    for attempt in range(2):
        try:
            response = requests.post(url, headers=headers, json=data, timeout=60)
            if response.status_code == 200:
                return response.json()["candidates"][0]["content"]["parts"][0]["text"]
            logging.error(f"Gemini HTTP {response.status_code}: {response.text}")
        except Exception as e:
            logging.error(f"Gemini Error: {e}")
        time.sleep(2)
    raise Exception("Gemini request failed")

def generate_post(topic):
    prompt = f"""
မင်းက "မင်းမင်းဖုန်းဆိုင်" ရဲ့ professional content writer ဖြစ်တယ်။

စည်းကမ်းများ:
- BRAND NEW ဖုန်းအသစ်များသာ
- refurbished / second hand မပါစေနဲ့
- repair service မပြောရ
- emoji သုံး
- 3-5 bullet points
- plain text only
- markdown symbols မသုံးရ
- 800 characters အောက်

Topic:
{topic}

အဆုံးမှာ ဒီစာထည့်:
📱 မင်းမင်းဖုန်းဆိုင် - ဖုန်းအသစ်အစစ်များသာ
"""
    return gemini_text_request(prompt)

def generate_image(prompt):
    logging.info(f"Generating image for: {prompt}")
    safe_prompt = urllib.parse.quote(f"professional smartphone advertisement, {prompt}, white background, studio lighting")
    img_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1024&height=1024&model=flux"
    try:
        response = requests.get(img_url, timeout=60)
        if response.status_code == 200:
            return response.content
    except Exception as e:
        logging.error(f"Image generation error: {e}")
    return None

# ---------------- TELEGRAM ---------------- #
def send_telegram(text, chat_id=None):
    if chat_id is None:
        logging.error("send_telegram() called without chat_id - message not sent")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text[:4000],
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, json=data, timeout=30)
    except Exception as e:
        logging.error(f"Telegram send error: {e}")

def send_photo(image_bytes, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    files = {"photo": ("image.jpg", image_bytes, "image/jpeg")}
    data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption[:200]}
    try:
        response = requests.post(url, files=files, data=data, timeout=60)
        return response.status_code == 200
    except Exception as e:
        logging.error(f"Photo send error: {e}")
    return False

# ---------------- AUTO POST ---------------- #
def run_auto_post():
    if not is_auto_enabled():
        logging.info("Auto post is disabled")
        return
    
    logging.info("Running auto post")
    topics = load_topics()
    
    if not topics:
        logging.info("No topics found")
        return
    
    # ဒီနေ့ မပို့ရသေးတဲ့ topic ကိုရွေးမယ်
    available_topics = [t for t in topics if not already_posted_today(t)]
    
    if not available_topics:
        logging.info("All topics already posted today, using random topic")
        available_topics = topics
    
    topic = random.choice(available_topics)
    
    try:
        post = generate_post(topic)
        send_telegram(post, chat_id=TELEGRAM_CHAT_ID)
        
        image = generate_image(topic)
        if image:
            send_photo(image, topic)
        
        mark_posted(topic)
        logging.info(f"Auto post success: {topic}")
        
    except Exception as e:
        logging.error(f"Auto post failed: {e}")

# ---------------- SCHEDULER ---------------- #
scheduler = None

def start_scheduler():
    global scheduler
    if scheduler is not None:
        return
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=run_auto_post, trigger="cron", hour=9, minute=0, id="morning_post")
    scheduler.add_job(func=run_auto_post, trigger="cron", hour=17, minute=0, id="evening_post")
    scheduler.start()
    logging.info("Scheduler started - Auto posts at 9:00 and 17:00 daily")

# ---------------- WEBHOOK ---------------- #
@app.route(f"/webhook/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def webhook():
    update = request.get_json()
    
    if "message" in update:
        msg = update["message"]
        chat_id = str(msg["chat"]["id"])
        text = msg.get("text", "")
        
        # ADMIN PROTECTION
        if chat_id != str(ADMIN_ID):
            return "Unauthorized", 403
        
        logging.info(f"Command: {text}")
        
        # ---------------- START / HELP ---------------- #
        if text in ["/start", "/help"]:
            send_telegram(
                "🤖 Phone Shop AI Bot\n\n"
                "📋 Commands:\n"
                "/view_topics\n"
                "/add_topic [topic]\n"
                "/remove_topic [number]\n"
                "/write [topic]\n"
                "/write_topic [number]\n"
                "/random_post\n"
                "/status\n"
                "/cancel_auto\n"
                "/resume_auto",
                chat_id=chat_id
            )
        
        # ---------------- VIEW TOPICS ---------------- #
        elif text == "/view_topics":
            send_telegram(get_topics_list_text(), chat_id=chat_id)
        
        # ---------------- ADD TOPIC ---------------- #
        elif text.startswith("/add_topic"):
            topic = text.replace("/add_topic", "").strip()
            if not topic:
                send_telegram("❌ Topic ထည့်ပါ\n/add_topic iPhone 16 review", chat_id=chat_id)
            else:
                success, msg = add_topic(topic)
                send_telegram(msg, chat_id=chat_id)
        
        # ---------------- REMOVE TOPIC ---------------- #
        elif text.startswith("/remove_topic"):
            parts = text.split()
            if len(parts) != 2 or not parts[1].isdigit():
                send_telegram("❌ /remove_topic 2", chat_id=chat_id)
            else:
                success, msg = remove_topic(int(parts[1]))
                send_telegram(msg, chat_id=chat_id)
        
        # ---------------- WRITE TOPIC (by number) ---------------- #
        elif text.startswith("/write_topic"):
            parts = text.split()
            if len(parts) != 2 or not parts[1].isdigit():
                send_telegram("❌ /write_topic 1", chat_id=chat_id)
            else:
                index = int(parts[1])
                topics = load_topics()
                if 1 <= index <= len(topics):
                    topic = topics[index - 1]
                    send_telegram(f"⏳ Generating...\n\n📌 {topic}", chat_id=chat_id)
                    try:
                        post = generate_post(topic)
                        send_telegram(post, chat_id=chat_id)
                        image = generate_image(topic)
                        if image:
                            send_photo(image, topic)
                        send_telegram("✅ Done", chat_id=chat_id)
                    except Exception as e:
                        logging.error(e)
                        send_telegram(f"❌ Failed: {e}", chat_id=chat_id)
                else:
                    send_telegram("❌ Topic not found", chat_id=chat_id)
        
        # ---------------- WRITE CUSTOM TOPIC ---------------- #
        elif text.startswith("/write"):
            topic = text.replace("/write", "").strip()
            if not topic:
                send_telegram("❌ /write iPhone 16 review", chat_id=chat_id)
            else:
                send_telegram(f"⏳ Generating...\n\n📌 {topic}", chat_id=chat_id)
                try:
                    post = generate_post(topic)
                    send_telegram(post, chat_id=chat_id)
                    image = generate_image(topic)
                    if image:
                        send_photo(image, topic)
                    send_telegram("✅ Done", chat_id=chat_id)
                except Exception as e:
                    logging.error(e)
                    send_telegram(f"❌ Failed: {e}", chat_id=chat_id)
        
        # ---------------- RANDOM POST ---------------- #
        elif text == "/random_post":
            topics = load_topics()
            if not topics:
                send_telegram("❌ No topics found", chat_id=chat_id)
            else:
                topic = random.choice(topics)
                send_telegram(f"🎲 Random Topic\n\n📌 {topic}", chat_id=chat_id)
                try:
                    post = generate_post(topic)
                    send_telegram(post, chat_id=chat_id)
                    image = generate_image(topic)
                    if image:
                        send_photo(image, topic)
                    send_telegram("✅ Posted", chat_id=chat_id)
                except Exception as e:
                    logging.error(e)
                    send_telegram(f"❌ Failed: {e}", chat_id=chat_id)
        
        # ---------------- STATUS ---------------- #
        elif text == "/status":
            topics = load_topics()
            today_posts = get_today_post_count()
            auto_status = "✅ ON" if is_auto_enabled() else "❌ OFF"
            
            status_msg = f"""🤖 **Bot Status**

📚 Topics: {len(topics)}
📅 Today's posts: {today_posts}
🔄 Auto post: {auto_status}
⏰ Schedule: 9:00 AM & 5:00 PM

✅ Bot is running normally"""
            send_telegram(status_msg, chat_id=chat_id)
        
        # ---------------- CANCEL AUTO ---------------- #
        elif text == "/cancel_auto":
            set_auto_enabled(False)
            send_telegram("⏸️ Auto post turned OFF\n\nUse /resume_auto to start again", chat_id=chat_id)
        
        # ---------------- RESUME AUTO ---------------- #
        elif text == "/resume_auto":
            set_auto_enabled(True)
            send_telegram("▶️ Auto post turned ON\n\nNext post at 9:00 AM or 5:00 PM", chat_id=chat_id)
    
    return "OK", 200

# ---------------- MAIN ---------------- #
if __name__ == "__main__":
    init_db()
    start_scheduler()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
