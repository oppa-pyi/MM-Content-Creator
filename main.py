# main.py
import requests
import os
import random
import sys
from datetime import datetime

# ---------------- CONFIGURATION ---------------- #
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# ---------------- TOPICS LIST ---------------- #
PHONE_SHOP_TOPICS = [
    "ဖုန်းအသစ်ဝယ်မယ်ဆို သိထားသင့်တဲ့အချက် ၅ ချက်",
    "ဖုန်းအားသွင်းတဲ့အခါ သတိထားရမယ့်အချက်များ",
    "Redmi Note 14 Pro ရဲ့ အားသာချက်များ",
    "iPhone 16 vs Samsung S24 ဘယ်ဟာဝယ်သင့်လဲ",
    "ဖုန်းပူလာရင် ဘာလုပ်ရမလဲ",
    "Battery health ကောင်းအောင်ထိန်းသိမ်းနည်း",
    "ဖုန်းရေကျတဲ့အခါ ချက်ချင်းလုပ်ရမယ့်နည်းလမ်း",
    "သိန်း ၅၀ အတွင်း အကောင်းဆုံးဖုန်းများ ၂၀၂၄",
    "Gaming အတွက် အကောင်းဆုံးဖုန်းများ",
    "ဖုန်းလျှို့ဝှက်ကုဒ်များနှင့် အသုံးပြုနည်း"
]

# ---------------- GEMINI FUNCTION ---------------- #
def generate_gemini_text(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    
    response = requests.post(url, headers=headers, json=data, timeout=60)
    
    if response.status_code == 200:
        result = response.json()
        return result["candidates"][0]["content"]["parts"][0]["text"]
    else:
        raise Exception(f"Gemini API Error: {response.text}")

# ---------------- CONTENT GENERATOR ---------------- #
def generate_facebook_post(topic):
    prompt = f"""Write a Facebook post about "{topic}" in Myanmar language.

Write like a friendly phone shop owner talking to customers.

Structure:
1. HOOK - Eye-catching first line with emojis
2. CONTENT - 3-5 key points with ✅ emojis as bullet points
3. CTA - Call to action (ask a question to engage readers)
4. HASHTAGS - 3 hashtags like #PhoneTips #MyanmarTech

Keep under 1000 characters. Use natural, conversational Myanmar language.
Do NOT include any English intro like "Here is a post about...".
"""

    return generate_gemini_text(prompt)

# ---------------- TELEGRAM FUNCTIONS ---------------- #
def send_message_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text[:4000]
    }
    response = requests.post(url, json=payload, timeout=60)
    
    if response.status_code != 200:
        raise Exception(f"Telegram Error: {response.text}")
    
    print("✅ Telegram message sent!")
    return True

# ---------------- AUTO MODE ---------------- #
def run_auto_post():
    print("🚀 Auto Post Started at", datetime.now())
    
    topic = random.choice(PHONE_SHOP_TOPICS)
    print(f"📌 Selected Topic: {topic}")
    
    print("✍️ Generating content with Gemini...")
    content = generate_facebook_post(topic)
    
    print("📤 Sending to Telegram...")
    send_message_to_telegram(content)
    
    print("✅ All done!")

# ---------------- MAIN ---------------- #
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "auto":
        run_auto_post()
    else:
        print("Usage: python main.py auto")
