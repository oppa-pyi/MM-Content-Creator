import requests
import os
import random
import json
from datetime import datetime
from flask import Flask, request

app = Flask(__name__)

# ---------------- CONFIGURATION ---------------- #
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# ---------------- TOPICS FILE FUNCTIONS ---------------- #
TOPICS_FILE = "topics.txt"

def load_topics():
    if os.path.exists(TOPICS_FILE):
        with open(TOPICS_FILE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    return [
        "ဖုန်းအသစ်ဝယ်မယ်ဆို သိထားသင့်တဲ့အချက် ၅ ချက်",
        "ဖုန်းအားသွင်းတဲ့အခါ သတိထားရမယ့်အချက်များ",
        "Redmi Note 14 Pro review in Myanmar",
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

# ---------------- GEMINI FUNCTIONS ---------------- #
def gemini_request(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    response = requests.post(url, headers=headers, json=data, timeout=60)
    if response.status_code == 200:
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    raise Exception(f"Gemini Error: {response.text}")

def generate_post(topic):
    prompt = f"""Write a Facebook post about "{topic}" in Myanmar language for a phone shop.

Be friendly, use emojis, 3-5 key points with ✅, end with a question.
Keep under 1000 characters. No English intro."""
    return gemini_request(prompt)

def generate_new_topics():
    prompt = """Generate 20 phone shop related topics in Myanmar language.
One per line, no numbering, no extra text.
Categories: buying tips, new phones, battery care, comparisons, how-to."""
    response = gemini_request(prompt)
    topics = [line.strip() for line in response.split('\n') if line.strip() and not line.startswith('#')]
    return topics[:20]

# ---------------- TELEGRAM SEND ---------------- #
def send_telegram(text, chat_id=None):
    if chat_id is None:
        chat_id = TELEGRAM_CHAT_ID
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": text[:4000], "parse_mode": "Markdown"}, timeout=30)
    except Exception as e:
        print(f"Send error: {e}")

# ---------------- WEBHOOK (Command Handler) ---------------- #
@app.route(f"/webhook/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def webhook():
    update = request.get_json()
    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")
        
        if text.startswith("/start") or text.startswith("/help"):
            send_telegram("""🤖 **Phone Shop Bot Commands**

📋 **Topic Management:**
• `/view_topics` - Topic စာရင်းကြည့်ရန်
• `/add_topic [topic]` - Topic အသစ်ထည့်ရန်
• `/remove_topic [နံပါတ်]` - Topic ဖျက်ရန်
• `/refresh_topics` - Gemini နဲ့ Topic အသစ်ထုတ်ရန်

📝 **Post:**
• `/write [topic]` - Topic ပေးရုံနဲ့ Post ရေးပေးမယ်
• `/random_post` - Random Topic နဲ့ Post တင်မယ်""", chat_id)
        
        elif text.startswith("/view_topics"):
            topics = load_topics()
            if not topics:
                send_telegram("📭 Topic မရှိသေးပါ။ `/refresh_topics` နဲ့ အသစ်ထုတ်ပါ။", chat_id)
            else:
                msg = f"📚 **Topic List** ({len(topics)} ခု)\n\n"
                for i, t in enumerate(topics[:30]):
                    msg += f"{i+1}. {t}\n"
                send_telegram(msg, chat_id)
        
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
                send_telegram("❌ နံပါတ်ထည့်ပေးပါ။\nဥပမာ: `/remove_topic 3`\n\n`/view_topics` နဲ့ နံပါတ်ကြည့်ပါ။", chat_id)
            else:
                success, msg = remove_topic(int(parts[1]))
                send_telegram(msg, chat_id)
        
        elif text.startswith("/refresh_topics"):
            send_telegram("🔄 Gemini က Topic အသစ်တွေ ထုတ်နေပါပြီ... ခဏစောင့်ပါ။", chat_id)
            try:
                new_topics = generate_new_topics()
                if new_topics:
                    save_topics(new_topics)
                    send_telegram(f"✅ Topic အသစ် {len(new_topics)} ခု ထုတ်ပြီးပါပြီ။\n\n`/view_topics` နဲ့ ကြည့်ပါ။", chat_id)
                else:
                    send_telegram("❌ Topic ထုတ်ရာမှာ အဆင်မပြေပါ။ နောက်မှထပ်စမ်းပါ။", chat_id)
            except Exception as e:
                send_telegram(f"❌ Error: {str(e)[:100]}", chat_id)
        
        elif text.startswith("/random_post"):
            topics = load_topics()
            if not topics:
                send_telegram("❌ Topic မရှိပါ။ `/refresh_topics` နဲ့ အရင်ထုတ်ပါ။", chat_id)
            else:
                topic = random.choice(topics)
                send_telegram(f"🎲 **Topic:** {topic}\n\n⏳ Post ရေးနေပါပြီ...", chat_id)
                try:
                    post = generate_post(topic)
                    send_telegram(post, TELEGRAM_CHAT_ID)
                    send_telegram("✅ Post တင်ပြီးပါပြီ။", chat_id)
                except Exception as e:
                    send_telegram(f"❌ Error: {str(e)[:100]}", chat_id)
        
        elif text.startswith("/write"):
            topic = text.replace("/write", "").strip()
            if not topic:
                send_telegram("❌ Topic ထည့်ပေးပါ။\nဥပမာ: `/write ဖုန်းဝယ်မယ်ဆို သတိထားရမယ့်အချက်`", chat_id)
            else:
                send_telegram(f"✍️ **Topic:** {topic}\n\n⏳ Post ရေးနေပါပြီ... ခဏစောင့်ပါ။", chat_id)
                try:
                    post = generate_post(topic)
                    send_telegram(post, TELEGRAM_CHAT_ID)
                    send_telegram(f"✅ Post တင်ပြီးပါပြီ။\n\n📌 {topic}", chat_id)
                except Exception as e:
                    send_telegram(f"❌ Error: {str(e)[:100]}", chat_id)
    
    return "OK", 200

# ---------------- AUTO POST (GitHub Actions) ---------------- #
def run_auto_post():
    print("🚀 Auto Post at", datetime.now())
    topics = load_topics()
    if topics:
        topic = random.choice(topics)
        post = generate_post(topic)
        send_telegram(post)
        print("✅ Done")

# ---------------- MAIN ---------------- #
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "auto":
        run_auto_post()
    else:
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port)
