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

app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ---------- CONFIG ----------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
ADMIN_ID = 1917675707
MAX_TOPICS = 25

TOPICS_FILE = "topics.txt"
DB_FILE = "bot_data.db"

# ---------- DATABASE ----------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT, date TEXT)''')
    conn.commit()
    conn.close()
    logging.info("Database ready")

# ---------- TOPIC FUNCTIONS ----------
def load_topics():
    if os.path.exists(TOPICS_FILE):
        with open(TOPICS_FILE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    return ["📱 ဖုန်းအသစ်ဝယ်မယ်ဆို သိထားသင့်တဲ့အချက် ၅ ချက်"]

def save_topics(topics):
    """လုံးဝအစားထိုးသိမ်းမယ်"""
    with open(TOPICS_FILE, "w", encoding="utf-8") as f:
        for topic in topics:
            f.write(topic + "\n")

def add_topic(topic, auto_remove=True):
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
        text += f"{i+1}. {t}\n"
    return text

# ---------- SHOP INFO ----------
def load_shop_info():
    if os.path.exists("shop_info.txt"):
        with open("shop_info.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""

# ---------- GEMINI REQUEST (Text Generation) ----------
def gemini_request(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={GEMINI_API_KEY}"
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    for _ in range(3):
        try:
            r = requests.post(url, json=data, timeout=60)
            if r.status_code == 200:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            logging.error(f"Gemini error: {e}")
        time.sleep(3)
    return "AI Error"

# ---------- POST + PROMPT GENERATION (တစ်ခါခိုင်း နှစ်ခုထွက်) ----------
def generate_post_and_prompt(topic):
    shop_info = load_shop_info()
    
    prompt = f"""You are a professional Facebook content writer for a phone shop in Myanmar.

Shop Information (use this naturally in your post):
{shop_info}

Task: Write TWO things about: {topic}

PART 1 - POST CONTENT:
Write a Facebook post (Burmese/Myanmar language)
- Use emojis naturally
- Include 3-5 bullet points
- Keep under 800 characters
- Sound friendly and engaging
- Weave the shop info naturally into the post (NOT just copied at the end)
- Do NOT use markdown

PART 2 - IMAGE PROMPT:
Write a short, detailed English prompt (max 200 characters) for generating an image.
This will be used by an AI image generator (DALL-E, Imagen, or Stable Diffusion).
The prompt should describe a realistic smartphone product photo based on the topic.

FORMAT:
[POST]
... your post content here ...
[/POST]
[PROMPT]
... your image prompt here ...
[/PROMPT]

Return ONLY this format, nothing else."""
    
    response = gemini_request(prompt)
    
    # Parse the response
    post_content = ""
    image_prompt = ""
    
    post_match = re.search(r'\[POST\](.*?)\[/POST\]', response, re.DOTALL)
    if post_match:
        post_content = post_match.group(1).strip()
    
    prompt_match = re.search(r'\[PROMPT\](.*?)\[/PROMPT\]', response, re.DOTALL)
    if prompt_match:
        image_prompt = prompt_match.group(1).strip()
    
    # Fallback if parsing fails
    if not post_content:
        post_content = response[:800]
    if not image_prompt:
        image_prompt = f"realistic smartphone product photo, {topic}, 4k, studio lighting"
    
    return post_content, image_prompt

# ---------- BULK TOPIC GENERATION (REPLACE ALL) ----------
def generate_topic_batch():
    prompt = """Generate a list of 10 detailed, specific smartphone-related topics for Facebook posts.
Each topic should be 80-120 characters, Myanmar language, start with an emoji.
Format: numbered list 1 to 10, nothing else.
Example:
1. 📱 ဖုန်းအသစ်ဝယ်မယ်ဆို သိထားသင့်တဲ့အချက် ၅ ချက်
2. 🔋 Battery health ကောင်းအောင်ထိန်းသိမ်းနည်း"""
    return gemini_request(prompt)

def parse_topic_list(raw_text):
    topics = []
    for line in raw_text.split('\n'):
        line = line.strip()
        match = re.match(r'^\d+[\.\-]\s*(.+)$', line)
        if match:
            topic = match.group(1).strip()
            if topic:
                topics.append(topic)
    return topics[:10]

# ---------- TELEGRAM HELPERS ----------
def send_telegram(text, chat_id):
    if not chat_id:
        return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                      json={"chat_id": chat_id, "text": text[:4000]}, timeout=30)
    except Exception as e:
        logging.error(f"Telegram send error: {e}")

# ---------- BACKGROUND POST HANDLER (ဆက်တိုက်မပို့ရန်) ----------
def handle_post_generation(topic, chat_id):
    def task():
        try:
            send_telegram(f"⏳ ထုတ်နေပါတယ်... {topic}", chat_id)
            post_content, image_prompt = generate_post_and_prompt(topic)
            
            send_telegram(f"📝 **Post Content**\n\n{post_content}", chat_id)
            send_telegram(f"🖼️ **Image Prompt**\n\n`{image_prompt}`", chat_id)
            
        except Exception as e:
            logging.error(f"Generation error: {e}")
            send_telegram("❌ ထုတ်လို့မရပါ။", chat_id)
    threading.Thread(target=task, daemon=True).start()

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
        
        if text in ["/start", "/help"]:
            send_telegram(f"""📱 **Commands**
/view_topics - Topic စာရင်း
/add_topic [topic] - Topic အသစ် (Auto FIFO max {MAX_TOPICS})
/remove_topic [num] - Topic ဖျက်
/write [topic] - Post + Prompt ထုတ်
/write_topic [num] - Topic ရွေးရေး
/random_post - ကျပန်း
/generate_topic - AI Topic (၁၀ ခု) **အဟောင်းအကုန်ဖျက်**
/status - Bot အခြေအနေ""", chat_id)
        
        elif text == "/view_topics":
            send_telegram(get_topics_list(), chat_id)
        
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
                    handle_post_generation(topics[idx - 1], chat_id)
                else:
                    send_telegram("❌ Topic မရှိပါ", chat_id)
        
        elif text.startswith("/write"):
            topic = text.replace("/write", "").strip()
            if not topic:
                send_telegram("❌ /write iPhone 16", chat_id)
            else:
                handle_post_generation(topic, chat_id)
        
        elif text == "/random_post":
            topics = load_topics()
            if not topics:
                send_telegram("❌ Topic မရှိပါ", chat_id)
            else:
                topic = random.choice(topics)
                send_telegram(f"🎲 Random topic: {topic}", chat_id)
                handle_post_generation(topic, chat_id)
        
        # 🔥 GENERATE TOPIC - REPLACE ALL (အဟောင်းအကုန်ဖျက်)
        elif text == "/generate_topic":
            send_telegram("⏳ AI က Topic ၁၀ ခု ထုတ်နေပါတယ်... (အဟောင်းများ အကုန်ဖျက်ပါမည်)", chat_id)
            try:
                raw = generate_topic_batch()
                topics_list = parse_topic_list(raw)
                
                if not topics_list:
                    send_telegram("❌ Topic ထုတ်လို့မရပါ။ နောက်တစ်ခါ ထပ်ကြိုးစားပါ။", chat_id)
                    return "OK", 200
                
                # 🔥 အဟောင်းအကုန်ဖျက်၊ အသစ် ၁၀ ခုပဲထည့်
                save_topics(topics_list)
                
                result_msg = f"🤖 **AI Topic Generator**\n\n✅ အဟောင်း အားလုံးဖျက်ပြီး Topic အသစ် {len(topics_list)} ခု ထည့်ပြီးပါပြီ။\n\n**Topic အသစ်များ:**\n"
                for i, t in enumerate(topics_list, 1):
                    result_msg += f"{i}. {t}\n"
                
                send_telegram(result_msg, chat_id)
                
            except Exception as e:
                logging.error(f"Generate topic batch error: {e}")
                send_telegram("❌ Topic ထုတ်လို့မရပါ။ နောက်တစ်ခါ ထပ်ကြိုးစားပါ။", chat_id)
        
        elif text == "/status":
            topics = load_topics()
            send_telegram(f"🤖 Bot Status\nTopics: {len(topics)} / {MAX_TOPICS}\n✅ အလုပ်လုပ်နေပါတယ်", chat_id)
    
    return "OK", 200

# ---------- MAIN ----------
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
