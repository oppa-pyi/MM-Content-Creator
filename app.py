import requests
import os
import random
import urllib.parse
import time
import logging
import sqlite3
import base64
import re
from datetime import datetime, date
from flask import Flask, request

app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ---------- CONFIG ----------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
ADMIN_ID = 1917675707
MAX_TOPICS = 25  # အများဆုံး Topic အရေအတွက် (ကျော်ရင် အဟောင်းများကို အလိုအလျောက်ဖျက်)

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

# ---------- TOPIC FUNCTIONS (with auto FIFO removal) ----------
def load_topics():
    if os.path.exists(TOPICS_FILE):
        with open(TOPICS_FILE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    return ["📱 ဖုန်းအသစ်ဝယ်မယ်ဆို သိထားသင့်တဲ့အချက် ၅ ချက်"]

def save_topics(topics):
    with open(TOPICS_FILE, "w", encoding="utf-8") as f:
        for topic in topics:
            f.write(topic + "\n")

def add_topic(topic, auto_remove=True):
    """Topic အသစ်ထည့်ပြီး MAX_TOPICS ကျော်ရင် အဟောင်းဆုံးများကို ဖျက်ပေးတယ်"""
    topics = load_topics()
    if topic in topics:
        return False, "❌ Topic ရှိပြီးသားဖြစ်လို့ မထည့်ပါ။"
    
    topics.append(topic)
    
    # FIFO: အရေအတွက်ကျော်နေရင် အရင်ဆုံး topic များကို ဖျက်မယ်
    removed_count = 0
    if auto_remove and len(topics) > MAX_TOPICS:
        excess = len(topics) - MAX_TOPICS
        removed_topics = topics[:excess]
        topics = topics[excess:]
        removed_count = len(removed_topics)
    
    save_topics(topics)
    
    if removed_count > 0:
        return True, f"✅ Topic ထည့်းပြီး\n{topic}\n\n🗑️ အဟောင်း {removed_count} ခုကို အလိုအလျောက်ဖျက်ပြီးပါပြီ။"
    else:
        return True, f"✅ Topic ထည့်ပြီး\n{topic}"

def remove_oldest_topics(count):
    """အရင်ဆုံး topic count ခုကို ဖျက်ပါ (manual သုံးဖို့)"""
    topics = load_topics()
    if count >= len(topics):
        removed = topics.copy()
        save_topics([])
        return removed
    else:
        removed = topics[:count]
        save_topics(topics[count:])
        return removed

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

# ---------- GEMINI ----------
def gemini_request(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={GEMINI_API_KEY}"
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    for _ in range(2):
        try:
            r = requests.post(url, json=data, timeout=60)
            if r.status_code == 200:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            logging.error(f"Gemini request error: {e}")
        time.sleep(2)
    return "AI Error"

# ---------- SHOP INFO ----------
def load_shop_info():
    if os.path.exists("shop_info.txt"):
        with open("shop_info.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    return "ဆိုင်အချက်အလက် မရှိသေးပါ"

def generate_post(topic):
    shop_info = load_shop_info()
    prompt = f"""Facebook post ရေးပါ။ Topic: {topic}

အောက်ပါဆိုင်အချက်အလက်ကို post ရဲ့အဆုံးမှာ ထည့်ပေးပါ:
{shop_info}

စည်းကမ်း: 
- emoji သုံးပါ
- bullet points 3-5 ခု
- မြန်မာလို
- စာလုံးရေ 800 အောက်"""
    return gemini_request(prompt)

# ---------- IMAGE GENERATION FALLBACK ----------
def generate_gemini_image(prompt):
    if not GEMINI_API_KEY:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=60)
        if r.status_code == 200:
            data = r.json()
            for part in data["candidates"][0]["content"]["parts"]:
                if "inlineData" in part and part["inlineData"]["mimeType"].startswith("image/"):
                    return base64.b64decode(part["inlineData"]["data"])
    except Exception as e:
        logging.error(f"Gemini image error: {e}")
    return None

def generate_leonardo_image(prompt):
    LEONARDO_API_KEY = os.environ.get("LEONARDO_API_KEY")
    if not LEONARDO_API_KEY:
        return None
    url = "https://cloud.leonardo.ai/api/rest/v1/generations"
    headers = {"Authorization": f"Bearer {LEONARDO_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "prompt": prompt,
        "modelId": "b24e16ff-06e3-47eb-8b33-4ed6a5a6c5e9",
        "width": 1024,
        "height": 1024,
        "num_images": 1,
        "presetStyle": "DYNAMIC"
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=60)
        if r.status_code == 200:
            gen_id = r.json()["sdGenerationJob"]["generationId"]
            for _ in range(15):
                time.sleep(2)
                res = requests.get(f"https://cloud.leonardo.ai/api/rest/v1/generations/{gen_id}", headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    if data["generations_by_pk"]["status"] == "COMPLETE":
                        img_url = data["generations_by_pk"]["generated_images"][0]["url"]
                        return requests.get(img_url, timeout=30).content
                    elif data["generations_by_pk"]["status"] == "FAILED":
                        break
    except Exception as e:
        logging.error(f"Leonardo error: {e}")
    return None

def generate_pollinations_image(prompt):
    safe = urllib.parse.quote(f"smartphone advertisement, {prompt}")
    url = f"https://image.pollinations.ai/prompt/{safe}?width=1024&height=1024"
    try:
        r = requests.get(url, timeout=60)
        return r.content if r.status_code == 200 else None
    except Exception as e:
        logging.error(f"Pollinations error: {e}")
        return None

def generate_image_with_fallback(prompt):
    img = generate_gemini_image(prompt)
    if img:
        return img
    img = generate_leonardo_image(prompt)
    if img:
        return img
    img = generate_pollinations_image(prompt)
    if img:
        return img
    return None

def generate_image(prompt):
    return generate_image_with_fallback(prompt)

# ---------- BULK TOPIC GENERATOR (10 topics at once) & AUTO ADD ----------
def generate_topic_batch():
    prompt = """Generate a list of 10 detailed, specific smartphone-related topics for Facebook posts.
Requirements:
- Each topic should be around 80-120 characters
- Language: Myanmar (Burmese)
- Should be informative and practical, like a mini-guide or tip
- Start each topic with an emoji (📱, 🔋, 📸, 🖥️, ⚡, 🛡️, 💡, etc.)
- Format: just the list, numbered 1 to 10, each on a new line, nothing else.
- Example:
1. 📱 ဖုန်းအသစ်ဝယ်မယ်ဆို သိထားသင့်တဲ့အချက် ၅ ချက်
2. 🔋 Battery health ကောင်းအောင်ထိန်းသိမ်းနည်း
"""
    return gemini_request(prompt)

def parse_topic_list(raw_text):
    """AI ပေးလိုက်တဲ့ text ထဲက topic များကို extract လုပ်မယ်"""
    topics = []
    lines = raw_text.split('\n')
    for line in lines:
        line = line.strip()
        # Numbered list: "1. topic text" or "1- topic text"
        match = re.match(r'^\d+[\.\-]\s*(.+)$', line)
        if match:
            topic = match.group(1).strip()
            if topic:
                topics.append(topic)
        else:
            # Fallback: ignore lines without number
            pass
    return topics[:10]  # maximum 10

# ---------- TELEGRAM ----------
def send_telegram(text, chat_id):
    if not chat_id:
        return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
                      json={"chat_id": chat_id, "text": text[:4000]}, timeout=30)
    except Exception as e:
        logging.error(f"Telegram send error: {e}")

def send_photo(image_bytes, caption, chat_id):
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
                      files={"photo": ("img.jpg", image_bytes)},
                      data={"chat_id": chat_id, "caption": caption[:200]}, timeout=60)
    except Exception as e:
        logging.error(f"Photo send error: {e}")

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
        
        # ----- HELP -----
        if text in ["/start", "/help"]:
            send_telegram(f"""📱 **Commands**
/view_topics - Topic စာရင်း
/add_topic [topic] - Topic အသစ် (Auto FIFO: max {MAX_TOPICS})
/remove_topic [num] - Topic ဖျက်
/write [topic] - Post ရေး
/write_topic [num] - Topic ရွေးရေး
/random_post - ကျပန်း
/generate_topic - AI Topic (၁၀ ခု) အသစ် + Auto Save
/status - Bot အခြေအနေ""", chat_id)
        
        # ----- VIEW -----
        elif text == "/view_topics":
            send_telegram(get_topics_list(), chat_id)
        
        # ----- ADD -----
        elif text.startswith("/add_topic"):
            param = text.replace("/add_topic", "").strip()
            if not param:
                send_telegram("❌ /add_topic [topic]\n\nExample: /add_topic 📱 ဖုန်းဘက်ထရီ အကြောင်း", chat_id)
            else:
                ok, msg = add_topic(param)
                send_telegram(msg, chat_id)
        
        # ----- REMOVE -----
        elif text.startswith("/remove_topic"):
            parts = text.split()
            if len(parts) != 2 or not parts[1].isdigit():
                send_telegram("❌ /remove_topic 2", chat_id)
            else:
                ok, msg = remove_topic(int(parts[1]))
                send_telegram(msg, chat_id)
        
        # ----- WRITE TOPIC (by number) -----
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
                        logging.error(f"Write topic error: {e}")
                        send_telegram("❌ Fail", chat_id)
                else:
                    send_telegram("❌ မရှိဘူး", chat_id)
        
        # ----- WRITE CUSTOM -----
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
                    logging.error(f"Write custom error: {e}")
                    send_telegram("❌ Fail", chat_id)
        
        # ----- RANDOM -----
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
                    logging.error(f"Random post error: {e}")
                    send_telegram("❌ Fail", chat_id)
        
        # ----- GENERATE TOPIC (BATCH OF 10) + AUTO ADD -----
        elif text == "/generate_topic":
            send_telegram("⏳ AI က Topic စာရင်း (၁၀ ခု) ထုတ်နေပါတယ်...", chat_id)
            try:
                raw_batch = generate_topic_batch()
                topics_list = parse_topic_list(raw_batch)
                
                if not topics_list:
                    send_telegram("❌ AI မှ Topic စာရင်း ပြန်မပို့နိုင်ပါ။ နောက်တစ်ခါ ထပ်ကြိုးစားပါ။", chat_id)
                    return
                
                added = 0
                duplicates = 0
                added_topics = []
                for t in topics_list:
                    ok, msg = add_topic(t, auto_remove=True)
                    if ok:
                        added += 1
                        added_topics.append(t)
                    else:
                        duplicates += 1
                
                result_msg = f"🤖 **AI Topic Generator**\n\n"
                result_msg += f"✅ အသစ်ထည့်ပြီးသော Topic: {added} ခု\n"
                if duplicates > 0:
                    result_msg += f"⚠️ ထပ်နေသော Topic: {duplicates} ခု\n"
                result_msg += f"📚 လက်ရှိ စုစုပေါင်း: {len(load_topics())} / {MAX_TOPICS}\n\n"
                
                # Show first 5 added topics
                if added_topics:
                    result_msg += f"**အသစ်ထည့်ထားသော Topic များ (ပထမ ၅ ခု):**\n"
                    for i, t in enumerate(added_topics[:5], 1):
                        result_msg += f"{i}. {t}\n"
                    if len(added_topics) > 5:
                        result_msg += f"... နှင့် {len(added_topics)-5} ခု\n"
                
                send_telegram(result_msg, chat_id)
                
            except Exception as e:
                logging.error(f"Generate topic list error: {e}")
                send_telegram("❌ Topic စာရင်း ထုတ်လို့မရပါ။ နောက်တစ်ခါ ထပ်ကြိုးစားပါ။", chat_id)
        
        # ----- STATUS -----
        elif text == "/status":
            topics = load_topics()
            send_telegram(f"🤖 Status\nTopics: {len(topics)} / {MAX_TOPICS}\n✅ Running", chat_id)
    
    return "OK", 200

# ---------- MAIN ----------
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)