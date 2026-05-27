import requests
import os
import random
import time
import logging
import sqlite3
import re
import threading
from datetime import datetime, date
from flask import Flask, request
from apscheduler.schedulers.background import BackgroundScheduler

# Try to import openai, but don't fail if not available
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    openai = None

app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ---------- CONFIG ----------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
ADMIN_ID = 1917675707
MAX_TOPICS = 25

TOPICS_FILE = "topics.txt"
DB_FILE = "bot_data.db"

# ---------- DATABASE (Analytics) ----------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS analytics
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  topic TEXT,
                  generated_at TEXT,
                  source TEXT)''')
    conn.commit()
    conn.close()
    logging.info("Database ready")

def log_analytics(topic, source="gemini"):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        now = datetime.now()
        c.execute("INSERT INTO analytics (topic, generated_at, source) VALUES (?, ?, ?)",
                  (topic[:200], now.isoformat(), source))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Analytics error: {e}")

def get_analytics_summary():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT topic, COUNT(*) FROM analytics GROUP BY topic ORDER BY COUNT(*) DESC LIMIT 10")
        results = c.fetchall()
        conn.close()
        
        if not results:
            return "📊 အချက်အလက် မရှိသေးပါ။"
        
        msg = "📊 **အသုံးအများဆုံး Topics**\n\n"
        for i, (topic, count) in enumerate(results, 1):
            msg += f"{i}. {topic[:40]}... ({count} ကြိမ်)\n"
        return msg
    except Exception as e:
        logging.error(f"Analytics summary error: {e}")
        return "📊 Analytics error. Check logs."

# ---------- TOPIC FUNCTIONS ----------
def load_topics():
    try:
        if os.path.exists(TOPICS_FILE):
            with open(TOPICS_FILE, "r", encoding="utf-8") as f:
                return [line.strip() for line in f if line.strip()]
    except Exception as e:
        logging.error(f"Load topics error: {e}")
    return ["📱 ဖုန်းအသစ်ဝယ်မယ်ဆို သိထားသင့်တဲ့အချက် ၅ ချက်"]

def save_topics(topics):
    try:
        with open(TOPICS_FILE, "w", encoding="utf-8") as f:
            for topic in topics:
                f.write(topic + "\n")
        logging.info(f"Saved {len(topics)} topics to {TOPICS_FILE}")
        return True
    except Exception as e:
        logging.error(f"Save topics error: {e}")
        return False

def add_topic(topic, auto_remove=True):
    if not topic or len(topic) > 300:
        return False, "❌ Topic က အရမ်းရှည်နေပါတယ် (max 300 characters)"
    
    topics = load_topics()
    if topic in topics:
        return False, "❌ Topic ရှိပြီးသား"
    topics.append(topic)
    removed_count = 0
    if auto_remove and len(topics) > MAX_TOPICS:
        excess = len(topics) - MAX_TOPICS
        removed_count = excess
        topics = topics[excess:]
    save_topics(topics)
    if removed_count > 0:
        return True, f"✅ Topic ထည့်ပြီး\n{topic}\n\n🗑️ အဟောင်း {removed_count} ခု အလိုအလျောက်ဖျက်ပြီး"
    else:
        return True, f"✅ Topic ထည့်ပြီး\n{topic}"

def remove_topic(index):
    topics = load_topics()
    if 1 <= index <= len(topics):
        removed = topics.pop(index - 1)
        save_topics(topics)
        return True, f"✅ ဖျက်ပြီး\n{removed}"
    return False, "❌ မှားယွင်းသောနံပါတ်"

def get_topics_list():
    topics = load_topics()
    if not topics:
        return "📭 Topic မရှိသေးပါ။"
    text = f"📚 စုစုပေါင်း ({len(topics)} / {MAX_TOPICS}) ခု\n"
    for i, t in enumerate(topics[:50]):
        text += f"{i+1}. {t[:80]}\n"
    return text

# ---------- SHOP INFO ----------
def load_shop_info():
    try:
        if os.path.exists("shop_info.txt"):
            with open("shop_info.txt", "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception as e:
        logging.error(f"Load shop info error: {e}")
    return ""

# ---------- AI MODEL FUNCTIONS ----------
def gemini_request(prompt):
    if not GEMINI_API_KEY:
        logging.warning("Gemini: No API key")
        return None
    
    # Clean prompt - remove very long content
    if len(prompt) > 3000:
        prompt = prompt[:3000]
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={GEMINI_API_KEY}"
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    for attempt in range(3):
        try:
            r = requests.post(url, json=data, timeout=90)
            if r.status_code == 200:
                result = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                if result and len(result) > 10:
                    return result
                else:
                    logging.warning(f"Gemini returned short/empty response: {result}")
            else:
                logging.error(f"Gemini HTTP {r.status_code}: {r.text[:200]}")
        except requests.Timeout:
            logging.error(f"Gemini timeout (attempt {attempt+1})")
        except Exception as e:
            logging.error(f"Gemini error (attempt {attempt+1}): {e}")
        time.sleep(5)
    return None

def openai_request(prompt):
    if not OPENAI_API_KEY or not OPENAI_AVAILABLE:
        return None
    
    # Clean prompt
    if len(prompt) > 3000:
        prompt = prompt[:3000]
    
    openai.api_key = OPENAI_API_KEY
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1000,
            timeout=60
        )
        result = response.choices[0].message.content
        if result and len(result) > 10:
            return result
    except Exception as e:
        logging.error(f"OpenAI error: {e}")
    return None

def ai_request(prompt):
    """Try Gemini first, then OpenAI as fallback"""
    logging.info(f"AI Request - Prompt length: {len(prompt)}")
    
    try:
        result = gemini_request(prompt)
        if result and "Error" not in result and len(result) > 10:
            return result, "gemini"
    except Exception as e:
        logging.error(f"Gemini exception: {e}")
    
    try:
        result = openai_request(prompt)
        if result and "Error" not in result and len(result) > 10:
            return result, "openai"
    except Exception as e:
        logging.error(f"OpenAI exception: {e}")
    
    return "AI Error: Both models failed. Please try again with shorter topic.", None

# ---------- POST + PROMPT GENERATION ----------
def generate_post_and_prompt(topic):
    # Shorten topic if too long
    if len(topic) > 150:
        topic = topic[:147] + "..."
    
    shop_info = load_shop_info()
    if len(shop_info) > 500:
        shop_info = shop_info[:500]
    
    prompt = f"""You are a professional Facebook content writer for a phone shop in Myanmar.

Shop Information (use this naturally in your post):
{shop_info}

Task: Write TWO things about this topic: {topic}

PART 1 - POST CONTENT:
Write a Facebook post (Burmese/Myanmar language)
- Use emojis naturally
- Include 3-5 bullet points (• or -)
- Keep under 600 characters
- Sound friendly and engaging
- Weave the shop info naturally into the post
- Do NOT use markdown
- Do NOT include any title like "Post Content". Just the post itself.

PART 2 - IMAGE PROMPT:
Write a short, detailed English prompt (max 200 characters) for generating an image.
Include shop name naturally in the prompt.

FORMAT:
[POST]
... post content ...
[/POST]
[PROMPT]
... image prompt ...
[/PROMPT]

Return ONLY this format."""
    
    response, source = ai_request(prompt)
    
    if "AI Error" in response:
        return response, "", source
    
    # Parse response
    post_content = ""
    image_prompt = ""
    
    post_match = re.search(r'\[POST\](.*?)\[/POST\]', response, re.DOTALL)
    if post_match:
        post_content = post_match.group(1).strip()[:800]
    
    prompt_match = re.search(r'\[PROMPT\](.*?)\[/PROMPT\]', response, re.DOTALL)
    if prompt_match:
        image_prompt = prompt_match.group(1).strip()[:250]
    
    # Fallback
    if not post_content:
        post_content = f"📱 {topic}\n\nအသေးစိတ်အချက်အလက်များအတွက် ဆိုင်သို့ ဆက်သွယ်မေးမြန်းနိုင်ပါတယ်။\n\n{shop_info[:200]}"
    if not image_prompt:
        image_prompt = f"realistic smartphone product photo, {topic[:80]}, 4k, studio lighting"
    
    return post_content, image_prompt, source

# ---------- DALL-E IMAGE (Optional) ----------
def generate_dalle_image(prompt):
    if not OPENAI_API_KEY or not OPENAI_AVAILABLE:
        return None
    openai.api_key = OPENAI_API_KEY
    try:
        response = openai.Image.create(
            model="dall-e-3",
            prompt=prompt[:500],
            n=1,
            size="1024x1024",
            quality="standard"
        )
        img_data = requests.get(response.data[0].url, timeout=30).content
        logging.info("DALL-E: Image generated")
        return img_data
    except Exception as e:
        logging.error(f"DALL-E error: {e}")
        return None

# ---------- BULK TOPIC GENERATION ----------
def generate_topic_batch():
    prompt = """Generate a list of 10 detailed, specific smartphone-related topics for Facebook posts.
Each topic should be 50-80 characters, Myanmar language, start with an emoji.
Format: numbered list 1 to 10, nothing else.
Example:
1. 📱 ဖုန်းအသစ်ဝယ်မယ်ဆို သိထားသင့်တဲ့အချက် ၅ ချက်
2. 🔋 Battery health ကောင်းအောင်ထိန်းသိမ်းနည်း"""
    response, _ = ai_request(prompt)
    return response

def parse_topic_list(raw_text):
    topics = []
    for line in raw_text.split('\n'):
        line = line.strip()
        match = re.match(r'^\d+[\.\-]\s*(.+)$', line)
        if match:
            topic = match.group(1).strip()
            if topic and len(topic) < 150:
                topics.append(topic)
    return topics[:10]

# ---------- TELEGRAM HELPERS ----------
def send_telegram(text, chat_id):
    if not chat_id or not text:
        return
    try:
        # Split long messages
        if len(text) > 4000:
            for i in range(0, len(text), 4000):
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                              json={"chat_id": chat_id, "text": text[i:i+4000]}, timeout=30)
        else:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                          json={"chat_id": chat_id, "text": text}, timeout=30)
    except Exception as e:
        logging.error(f"Telegram send error: {e}")

def send_photo(image_bytes, caption, chat_id):
    if not image_bytes:
        return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
                      files={"photo": ("image.jpg", image_bytes)},
                      data={"chat_id": chat_id, "caption": (caption or "")[:200]}, timeout=60)
    except Exception as e:
        logging.error(f"Photo send error: {e}")

# ---------- BACKGROUND HANDLER ----------
def handle_post_generation(topic, chat_id, auto_image=False):
    def task():
        try:
            # Check topic length
            if len(topic) > 300:
                send_telegram(f"⚠️ Topic က {len(topic)} လုံးရှည်နေပါတယ်။ ကျေးဇူးပြု၍ အတိုချုံးပါ။", chat_id)
                return
            
            send_telegram(f"⏳ ထုတ်နေပါတယ်... {topic[:80]}...", chat_id)
            post_content, image_prompt, source = generate_post_and_prompt(topic)
            
            if "AI Error" in post_content:
                send_telegram(f"❌ {post_content}", chat_id)
                return
            
            log_analytics(topic, source)
            send_telegram(post_content, chat_id)
            send_telegram(f"🖼️ **Image Prompt** (AI: {source})\n\n`{image_prompt}`", chat_id)
            
            if auto_image and OPENAI_API_KEY:
                send_telegram("🎨 ပုံထုတ်နေပါတယ်...", chat_id)
                img = generate_dalle_image(image_prompt)
                if img:
                    send_photo(img, post_content[:200], chat_id)
        except Exception as e:
            logging.error(f"Generation error: {e}")
            send_telegram(f"❌ ထုတ်လို့မရပါ။ Error: {str(e)[:100]}", chat_id)
    threading.Thread(target=task, daemon=True).start()

# ---------- AUTO SCHEDULE (4 times per day) ----------
def auto_post_to_channel():
    logging.info("Running scheduled auto post...")
    topics = load_topics()
    if not topics:
        logging.warning("No topics for auto post")
        return
    
    # Try up to 3 times to find a working topic
    for _ in range(3):
        topic = random.choice(topics)
        if len(topic) < 150:
            break
    
    post_content, image_prompt, source = generate_post_and_prompt(topic)
    
    if "AI Error" not in post_content:
        log_analytics(topic, f"{source}_auto")
        now = datetime.now().strftime("%H:%M")
        send_telegram(f"⏰ **Auto Post - {now}**\n\n{post_content}", TELEGRAM_CHAT_ID)
        send_telegram(f"🖼️ **Image Prompt** (AI: {source})\n\n`{image_prompt}`", TELEGRAM_CHAT_ID)
        
        if OPENAI_API_KEY:
            img = generate_dalle_image(image_prompt)
            if img:
                send_photo(img, post_content[:200], TELEGRAM_CHAT_ID)

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
        
        logging.info(f"Command: {text[:100]}")
        
        if text in ["/start", "/help"]:
            send_telegram(f"""📱 **Commands**
/view_topics - Topic စာရင်း
/add_topic [topic] - Topic အသစ်
/remove_topic [num] - Topic ဖျက်
/write [topic] - Post + Prompt ထုတ်
/write_img [topic] - Post + Prompt + DALL-E ပုံ
/write_topic [num] - Topic ရွေးရေး
/random_post - ကျပန်း
/generate_topic - AI Topic (၁၀ ခု) အဟောင်းဖျက်
/analytics - အသုံးပြုမှုစာရင်း
/status - Bot အခြေအနေ""", chat_id)
        
        elif text == "/view_topics":
            send_telegram(get_topics_list(), chat_id)
        
        elif text == "/analytics":
            send_telegram(get_analytics_summary(), chat_id)
        
        elif text.startswith("/add_topic"):
            param = text.replace("/add_topic", "").strip()
            if not param:
                send_telegram("❌ /add_topic [topic]", chat_id)
            else:
                ok, msg = add_topic(param)
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
                    handle_post_generation(topics[idx - 1], chat_id, auto_image=False)
                else:
                    send_telegram("❌ Topic မရှိပါ", chat_id)
        
        elif text.startswith("/write_img"):
            topic = text.replace("/write_img", "").strip()
            if not topic:
                send_telegram("❌ /write_img iPhone 16", chat_id)
            else:
                handle_post_generation(topic, chat_id, auto_image=True)
        
        elif text.startswith("/write"):
            topic = text.replace("/write", "").strip()
            if not topic:
                send_telegram("❌ /write iPhone 16", chat_id)
            else:
                handle_post_generation(topic, chat_id, auto_image=False)
        
        elif text == "/random_post":
            topics = load_topics()
            if not topics:
                send_telegram("❌ Topic မရှိပါ", chat_id)
            else:
                topic = random.choice(topics)
                send_telegram(f"🎲 Random topic: {topic[:80]}", chat_id)
                handle_post_generation(topic, chat_id, auto_image=False)
        
        elif text == "/generate_topic":
            send_telegram("⏳ AI က Topic ၁၀ ခု ထုတ်နေပါတယ်... (အဟောင်းများ အကုန်ဖျက်ပါမည်)", chat_id)
            try:
                raw = generate_topic_batch()
                topics_list = parse_topic_list(raw)
                
                if not topics_list or len(topics_list) == 0:
                    send_telegram("❌ Topic ထုတ်လို့မရပါ။ နောက်တစ်ခါ ထပ်ကြိုးစားပါ။", chat_id)
                    return "OK", 200
                
                success = save_topics(topics_list)
                
                if success:
                    verify_topics = load_topics()
                    result_msg = f"🤖 **AI Topic Generator**\n\n✅ Topic အသစ် {len(verify_topics)} ခု အောင်မြင်စွာ သိမ်းဆည်းပြီးပါပြီ။\n\n**Topic အသစ်များ:**\n"
                    for i, t in enumerate(verify_topics[:10], 1):
                        result_msg += f"{i}. {t[:80]}\n"
                    send_telegram(result_msg, chat_id)
                else:
                    send_telegram("❌ Topic ထုတ်လို့ရပေမယ့် ဖိုင်သိမ်းရာမှာ အမှားရှိနေပါတယ်။", chat_id)
                
            except Exception as e:
                logging.error(f"Generate topic batch error: {e}")
                send_telegram(f"❌ Error: {str(e)[:100]}", chat_id)
        
        elif text == "/status":
            topics = load_topics()
            models = []
            if GEMINI_API_KEY:
                models.append("Gemini")
            if OPENAI_API_KEY:
                models.append("ChatGPT/DALL-E")
            send_telegram(f"🤖 Bot Status\nTopics: {len(topics)} / {MAX_TOPICS}\nAI Models: {', '.join(models) if models else 'None'}\n✅ အလုပ်လုပ်နေပါတယ်", chat_id)
    
    return "OK", 200

# ---------- MAIN ----------
if __name__ == "__main__":
    init_db()
    
    # Start scheduler for 4 times daily
    try:
        scheduler = BackgroundScheduler()
        scheduler.add_job(func=auto_post_to_channel, trigger="cron", hour=9, minute=0)
        scheduler.add_job(func=auto_post_to_channel, trigger="cron", hour=13, minute=0)
        scheduler.add_job(func=auto_post_to_channel, trigger="cron", hour=17, minute=0)
        scheduler.add_job(func=auto_post_to_channel, trigger="cron", hour=21, minute=0)
        scheduler.start()
        logging.info("Auto scheduler started - Daily posts at 9:00, 13:00, 17:00, 21:00")
    except Exception as e:
        logging.error(f"Scheduler error: {e}")
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)