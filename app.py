import requests
import os
import random
import json
import urllib.parse
import base64
import time
from datetime import datetime
from flask import Flask, request

app = Flask(__name__)

# ---------------- CONFIGURATION ---------------- #
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

TOPICS_FILE = "topics.txt"

# ---------------- TOPICS FILE FUNCTIONS ---------------- #
def load_topics():
    if os.path.exists(TOPICS_FILE):
        with open(TOPICS_FILE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    return [
        "ဖုန်းအသစ်ဝယ်မယ်ဆို သိထားသင့်တဲ့အချက် ၅ ချက်",
        "ဖုန်းအားသွင်းတဲ့အခါ သတိထားရမယ့်အချက်များ",
        "Redmi Note 14 Pro review in Myanmar",
        "iPhone 16 vs Samsung S24 ဘယ်ဟာဝယ်သင့်လဲ",
        "ဖုန်းပူလာရင် ဘာလုပ်ရမလဲ",
        "Battery health ကောင်းအောင်ထိန်းသိမ်းနည်း",
    ]

def save_topics(topics):
    with open(TOPICS_FILE, "w", encoding="utf-8") as f:
        for topic in topics:
            f.write(topic + "\n")

def add_topic(topic):
    topics = load_topics()
    if topic in topics:
        return False, "❌ ဒီ Topic ရှိပြီးသားပါ။"
    topics.append(topic)
    save_topics(topics)
    return True, f"✅ Topic အသစ်ထည့်ပြီးပါပြီ။\n\n📌 {topic}"

def remove_topic(index):
    topics = load_topics()
    if 1 <= index <= len(topics):
        removed = topics.pop(index - 1)
        save_topics(topics)
        return True, f"✅ Topic ဖျက်ပြီးပါပြီ။\n\n❌ {removed}"
    return False, f"❌ နံပါတ် {index} က မရှိပါ။ (၁ မှ {len(topics)} အတွင်း)"

def get_topics_list_text():
    topics = load_topics()
    if not topics:
        return "📭 Topic မရှိသေးပါ။ `/add_topic` နဲ့ ထည့်ပါ။"
    text = f"📚 *Topic List* ({len(topics)} ခု)\n\n"
    for i, t in enumerate(topics[:50]):
        text += f"{i+1}. {t}\n"
    return text

# ---------------- GEMINI TEXT GENERATION ---------------- #
def gemini_text_request(prompt):
    """Gemini 2.0 Flash Lite နဲ့ Text ထုတ်မယ်"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    response = requests.post(url, headers=headers, json=data, timeout=60)
    if response.status_code == 200:
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    raise Exception(f"Gemini Error: {response.text}")

def generate_post(topic):
    """ဆိုင်စည်းကမ်းအတိုင်း Post ရေးမယ်"""
    
    SYSTEM_INSTRUCTION = """မင်းက "မင်းမင်းဖုန်းဆိုင်" ရဲ့ Content Creator Bot ဖြစ်တယ်။

အရေးကြီးတဲ့ စည်းကမ်းများ (လုံးဝမချိုးဖောက်ရ):
- BRAND NEW ဖုန်းအသစ်များသာ ရောင်းချသည်။
- Refurbished, Second hand, Trade-in (ဖုန်းအဟောင်းနဲ့လဲခြင်း) လုံးဝမပါစေနဲ့။
- ဖုန်းပြင်ဆင်ခြင်း (Repair) ဝန်ဆောင်မှု မရှိပါ။

Post ရေးပုံစံ:
- စာဖတ်သူကို ဆွဲဆောင်မယ့် စာကြောင်း (Emoji သုံးပါ)
- 3-5 key points (✅ as bullet points)
- အောက်ဆုံးမှာ "📱 မင်းမင်းဖုန်းဆိုင် - ဖုန်းအသစ်အစစ်များသာ" ထည့်ပါ
- စာလုံးရေ 800 အောက်သာထားပါ

Topic: {topic}

စလိုက်ပါ:"""
    
    return gemini_text_request(SYSTEM_INSTRUCTION)

def generate_new_topics():
    """Gemini နဲ့ Topic အသစ်တွေ ထုတ်မယ်"""
    prompt = """Generate 20 phone shop related topics in Myanmar language.
One per line, no numbering, no extra text.
Categories: buying tips, new phones, battery care, comparisons, how-to.
Start each topic with an emoji."""
    response = gemini_text_request(prompt)
    topics = [line.strip() for line in response.split('\n') if line.strip()]
    return topics[:25]

# ---------------- IMAGE GENERATION (Multi-Layer Fallback) ---------------- #

# Layer 1: Nano Banana Pro (Preview - အကောင်းဆုံး quality)
def generate_image_nanobanana(prompt):
    """Nano Banana Pro နဲ့ ပုံထုတ်မယ်"""
    model = "nanobanana-pro"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
    
    image_prompt = f"""Professional phone shop advertisement image for: {prompt}.
Style: Clean product photography, white background, high quality 4K resolution.
Professional lighting, phone shop branding friendly.
No text overlay, no watermark.
Product should be centered."""
    
    data = {
        "contents": [{"parts": [{"text": image_prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"], "temperature": 0.3}
    }
    
    try:
        response = requests.post(url, json=data, timeout=90)
        if response.status_code == 200:
            result = response.json()
            for part in result.get("candidates", [{}])[0].get("content", {}).get("parts", []):
                if "inlineData" in part:
                    print("✅ Nano Banana Pro image generated")
                    return base64.b64decode(part["inlineData"]["data"])
    except Exception as e:
        print(f"Nano Banana failed: {e}")
    return None

# Layer 2: Imagen 4 (Stable - Google official)
def generate_image_imagen4(prompt):
    """Imagen 4 နဲ့ ပုံထုတ်မယ် (Stable)"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-4.0-generate-001:generateImages?key={GEMINI_API_KEY}"
    
    data = {
        "instances": [{"prompt": f"Phone shop product photo, {prompt}, clean white background, professional, high quality"}],
        "parameters": {"sampleCount": 1, "aspectRatio": "1:1"}
    }
    
    try:
        response = requests.post(url, json=data, timeout=90)
        if response.status_code == 200:
            result = response.json()
            if "predictions" in result and result["predictions"]:
                print("✅ Imagen 4 image generated")
                return base64.b64decode(result["predictions"][0]["bytesBase64Encoded"])
    except Exception as e:
        print(f"Imagen 4 failed: {e}")
    return None

# Layer 3: Pollinations AI (Free, always works)
def generate_image_pollinations(prompt):
    """Pollinations AI နဲ့ ပုံထုတ်မယ် (Free Fallback)"""
    safe_prompt = urllib.parse.quote(f"professional phone product photography, {prompt}, clean white background, studio lighting")
    img_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1024&height=1024&model=flux"
    
    headers = {"User-Agent": "Mozilla/5.0"}
    
    for attempt in range(2):
        try:
            response = requests.get(img_url, headers=headers, timeout=60)
            if response.status_code == 200 and "image" in response.headers.get("content-type", ""):
                print("✅ Pollinations image generated")
                return response.content
        except Exception as e:
            print(f"Pollinations attempt {attempt+1} failed: {e}")
        time.sleep(2)
    return None

# Main image function with fallback chain
def generate_image(prompt):
    """အလုပ်အဖြစ်ဆုံး Image Generation - Fallback Chain"""
    
    print(f"🎨 Generating image for: {prompt[:50]}...")
    
    # Try Nano Banana Pro first (best quality)
    image = generate_image_nanobanana(prompt)
    if image:
        return image
    
    # Fallback to Imagen 4 (stable)
    image = generate_image_imagen4(prompt)
    if image:
        return image
    
    # Final fallback to Pollinations (always works)
    image = generate_image_pollinations(prompt)
    if image:
        return image
    
    print("❌ All image generation methods failed")
    return None

# ---------------- TELEGRAM FUNCTIONS ---------------- #
def send_telegram(text, chat_id=None):
    if chat_id is None:
        chat_id = TELEGRAM_CHAT_ID
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": text[:4000], "parse_mode": "Markdown"}, timeout=30)
    except Exception as e:
        print(f"Send error: {e}")

def send_photo(image_bytes, caption=""):
    """Telegram ကို ပုံပို့မယ်"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    files = {"photo": ("image.jpg", image_bytes, "image/jpeg")}
    data = {"chat_id": TELEGRAM_CHAT_ID}
    if caption:
        data["caption"] = caption[:200]
    try:
        response = requests.post(url, files=files, data=data, timeout=60)
        return response.status_code == 200
    except Exception as e:
        print(f"Send photo error: {e}")
        return False

# ---------------- WEBHOOK (Command Handler) ---------------- #
@app.route(f"/webhook/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def webhook():
    update = request.get_json()
    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")
        
        # /start /help
        if text == "/start" or text == "/help":
            send_telegram(
                "🤖 *Phone Shop Bot v3.0*\n\n"
                "📋 *Topic Management:*\n"
                "• /view_topics - Topic စာရင်းကြည့်ရန်\n"
                "• /add_topic [topic] - Topic အသစ်ထည့်ရန်\n"
                "• /remove_topic [နံပါတ်] - Topic ဖျက်ရန်\n"
                "• /refresh_topics - Topic အသစ်များထုတ်ယူရန်\n\n"
                "📝 *Post:*\n"
                "• /write [topic] - Topic ပေးရုံနဲ့ Post + Image တင်မယ်\n"
                "• /write_topic [နံပါတ်] - Topic List ထဲက နံပါတ်ရွေးပြီး Post + Image တင်မယ်\n"
                "• /random_post - Random Topic နဲ့ Post + Image တင်မယ်\n\n"
                "⚡ Image Generation: Nano Banana Pro → Imagen 4 → Pollinations",
                chat_id
            )
        
        elif text == "/view_topics":
            send_telegram(get_topics_list_text(), chat_id)
        
        elif text.startswith("/add_topic"):
            topic = text.replace("/add_topic", "").strip()
            if not topic:
                send_telegram("❌ Topic အမည်ထည့်ပေးပါ။\nဥပမာ: `/add_topic ဖုန်းအသစ်ဝယ်မယ်ဆို သိထားသင့်တဲ့အချက်`", chat_id)
            else:
                success, msg = add_topic(topic)
                send_telegram(msg, chat_id)
        
        elif text.startswith("/remove_topic"):
            parts = text.split()
            if len(parts) != 2 or not parts[1].isdigit():
                send_telegram("❌ နံပါတ်ထည့်ပေးပါ။\nဥပမာ: `/remove_topic 3`", chat_id)
            else:
                success, msg = remove_topic(int(parts[1]))
                send_telegram(msg, chat_id)
        
        elif text == "/refresh_topics":
            send_telegram("🔄 Topic အသစ်တွေ ထုတ်နေပါပြီ... 15-20 စက္ကန့်စောင့်ပါ။", chat_id)
            try:
                new_topics = generate_new_topics()
                if new_topics:
                    save_topics(new_topics)
                    send_telegram(f"✅ Topic အသစ် {len(new_topics)} ခု ထုတ်ပြီးပါပြီ။\n\n`/view_topics` နဲ့ ကြည့်ပါ။", chat_id)
                else:
                    send_telegram("❌ Topic ထုတ်ရာမှာ အဆင်မပြေပါ။", chat_id)
            except Exception as e:
                send_telegram(f"❌ Error: {str(e)[:100]}", chat_id)
        
        # /write [topic]
        elif text.startswith("/write"):
            topic = text.replace("/write", "").strip()
            if not topic:
                send_telegram("❌ Topic ထည့်ပေးပါ။\nဥပမာ: `/write ဖုန်းအသစ်ဝယ်မယ်ဆို သိထားသင့်တဲ့အချက်`", chat_id)
            else:
                send_telegram(f"✍️ *Topic:* {topic}\n\n⏳ Post နဲ့ Image ထုတ်နေပါပြီ... (10-20 စက္ကန့်)", chat_id)
                try:
                    post = generate_post(topic)
                    send_telegram(post)
                    
                    image = generate_image(topic)
                    if image:
                        send_photo(image, post[:200])
                        send_telegram(f"✅ Post + Image တင်ပြီးပါပြီ။\n\n📌 {topic}", chat_id)
                    else:
                        send_telegram(f"✅ Post တင်ပြီးပါပြီ။ (Image မထွက်ပါ)\n\n📌 {topic}", chat_id)
                except Exception as e:
                    send_telegram(f"❌ Error: {str(e)[:100]}", chat_id)
        
        # /write_topic [number]
        elif text.startswith("/write_topic"):
            parts = text.split()
            if len(parts) != 2 or not parts[1].isdigit():
                send_telegram("❌ နံပါတ်ထည့်ပေးပါ။\nဥပမာ: `/write_topic 3`", chat_id)
            else:
                index = int(parts[1])
                topics = load_topics()
                if 1 <= index <= len(topics):
                    topic = topics[index - 1]
                    send_telegram(f"✍️ *Topic #{index}:* {topic}\n\n⏳ Post နဲ့ Image ထုတ်နေပါပြီ...", chat_id)
                    try:
                        post = generate_post(topic)
                        send_telegram(post)
                        
                        image = generate_image(topic)
                        if image:
                            send_photo(image, post[:200])
                            send_telegram(f"✅ Post + Image တင်ပြီးပါပြီ။\n\n📌 {topic}", chat_id)
                        else:
                            send_telegram(f"✅ Post တင်ပြီးပါပြီ။\n\n📌 {topic}", chat_id)
                    except Exception as e:
                        send_telegram(f"❌ Error: {str(e)[:100]}", chat_id)
                else:
                    send_telegram(f"❌ နံပါတ် {index} က မရှိပါ။ (၁ မှ {len(topics)} အတွင်း)", chat_id)
        
        # /random_post
        elif text == "/random_post":
            topics = load_topics()
            if not topics:
                send_telegram("❌ Topic မရှိပါ။ `/add_topic` နဲ့ အရင်ထည့်ပါ။", chat_id)
            else:
                topic = random.choice(topics)
                send_telegram(f"🎲 *Topic:* {topic}\n\n⏳ Post နဲ့ Image ထုတ်နေပါပြီ...", chat_id)
                try:
                    post = generate_post(topic)
                    send_telegram(post)
                    
                    image = generate_image(topic)
                    if image:
                        send_photo(image, post[:200])
                        send_telegram(f"✅ Post + Image တင်ပြီးပါပြီ။\n\n📌 {topic}", chat_id)
                    else:
                        send_telegram(f"✅ Post တင်ပြီးပါပြီ။\n\n📌 {topic}", chat_id)
                except Exception as e:
                    send_telegram(f"❌ Error: {str(e)[:100]}", chat_id)
    
    return "OK", 200

# ---------------- AUTO POST ---------------- #
def run_auto_post():
    """GitHub Actions / Render Cron အတွက်"""
    print("🚀 Auto Post at", datetime.now())
    topics = load_topics()
    if topics:
        topic = random.choice(topics)
        try:
            post = generate_post(topic)
            send_telegram(post)
            print(f"✅ Posted: {topic[:50]}...")
        except Exception as e:
            print(f"Error: {e}")
    else:
        print("❌ No topics found")

# ---------------- MAIN ---------------- #
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "auto":
        run_auto_post()
    else:
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port)
