import requests
import os
import json
from http.server import BaseHTTPRequestHandler

# ---------------- CONFIGURATION ---------------- #
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# topics (in-memory, for simplicity)
topics = [
    "ဖုန်းအသစ်ဝယ်မယ်ဆို သိထားသင့်တဲ့အချက် ၅ ချက်",
    "ဖုန်းအားသွင်းတဲ့အခါ သတိထားရမယ့်အချက်များ",
    "Redmi Note 14 Pro review in Myanmar"
]

# ---------------- HELPER FUNCTIONS ---------------- #
def send_telegram(text, chat_id=None):
    if chat_id is None:
        chat_id = TELEGRAM_CHAT_ID
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": text[:4000], "parse_mode": "Markdown"}, timeout=30)
    except Exception as e:
        print(f"Error: {e}")

def call_gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={GEMINI_API_KEY}"
    response = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
    if response.status_code == 200:
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    return "Error generating content"

def generate_post(topic):
    prompt = f"""Write a Facebook post about "{topic}" in Myanmar language for a phone shop.

Rules:
- BRAND NEW phones only. NO refurbished, NO trade-in, NO second hand.
- Use emojis, 3-5 key points with ✅
- End with "📱 မင်းမင်းဖုန်းဆိုင် - ဖုန်းအသစ်အစစ်များသာ"
- Keep under 800 characters

Start writing:"""
    return call_gemini(prompt)

def generate_image(topic):
    # Nano Banana for image generation
    url = f"https://generativelanguage.googleapis.com/v1beta/models/nanobanana-pro:generateContent?key={GEMINI_API_KEY}"
    prompt = f"Professional phone shop advertisement image for: {topic}. Clean product photography, white background, 4K quality."
    try:
        response = requests.post(url, json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE"]}
        }, timeout=120)
        if response.status_code == 200:
            data = response.json()
            for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []):
                if "inlineData" in part:
                    return part["inlineData"]["data"]
    except Exception as e:
        print(f"Image error: {e}")
    return None

def send_photo(image_base64, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    import base64
    binary_data = base64.b64decode(image_base64)
    files = {"photo": ("image.jpg", binary_data, "image/jpeg")}
    data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption[:200]}
    requests.post(url, files=files, data=data, timeout=60)

def get_topics_text():
    text = f"📚 Topic List ({len(topics)} ခု)\n\n"
    for i, t in enumerate(topics):
        text += f"{i+1}. {t}\n"
    return text

# ---------------- WEBHOOK HANDLER ---------------- #
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        update = json.loads(body)
        
        message = update.get("message")
        if message:
            chat_id = message["chat"]["id"]
            text = message.get("text", "")
            
            if text == "/start" or text == "/help":
                send_telegram(
                    "🤖 **Phone Shop Bot Commands**\n\n"
                    "• /view_topics - Topic စာရင်းကြည့်ရန်\n"
                    "• /add_topic [topic] - Topic အသစ်ထည့်ရန်\n"
                    "• /remove_topic [နံပါတ်] - Topic ဖျက်ရန်\n"
                    "• /random_post - Random Post + Image တင်မယ်",
                    chat_id
                )
            
            elif text == "/view_topics":
                send_telegram(get_topics_text(), chat_id)
            
            elif text.startswith("/add_topic"):
                topic = text.replace("/add_topic", "").strip()
                if topic and topic not in topics:
                    topics.append(topic)
                    send_telegram(f"✅ Topic ထည့်ပြီးပါပြီ။\n\n{topic}", chat_id)
                else:
                    send_telegram("❌ Topic မထည့်နိုင်ပါ။", chat_id)
            
            elif text.startswith("/remove_topic"):
                parts = text.split()
                if len(parts) == 2 and parts[1].isdigit():
                    idx = int(parts[1]) - 1
                    if 0 <= idx < len(topics):
                        removed = topics.pop(idx)
                        send_telegram(f"✅ ဖျက်ပြီးပါပြီ။\n\n{removed}", chat_id)
                    else:
                        send_telegram(f"❌ နံပါတ် {parts[1]} မရှိပါ။", chat_id)
                else:
                    send_telegram("❌ နံပါတ်ထည့်ပါ။ ဥပမာ: /remove_topic 3", chat_id)
            
            elif text == "/random_post":
                if not topics:
                    send_telegram("❌ Topic မရှိပါ။", chat_id)
                else:
                    import random
                    topic = random.choice(topics)
                    send_telegram(f"🎲 {topic}\n\n⏳ Post နဲ့ Image ထုတ်နေပါပြီ...", chat_id)
                    
                    post = generate_post(topic)
                    send_telegram(post)
                    
                    image = generate_image(topic)
                    if image:
                        send_photo(image, post[:200])
                        send_telegram("✅ Post + Image တင်ပြီးပါပြီ။", chat_id)
                    else:
                        send_telegram("✅ Post တင်ပြီးပါပြီ။", chat_id)
        
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")