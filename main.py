import requests
import os
import random
import sys
from datetime import datetime

# ---------------- CONFIGURATION ---------------- #
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# ---------------- TOPICS FILE FUNCTIONS ---------------- #
def load_topics():
    """topics.txt ဖိုင်ကနေ Topic စာရင်းကို ဖတ်မယ်"""
    if os.path.exists("topics.txt"):
        with open("topics.txt", "r", encoding="utf-8") as f:
            topics = [line.strip() for line in f if line.strip()]
            if topics:
                return topics
    # topics.txt မရှိရင် default topics သုံးမယ်
    return [
        "ဖုန်းအသစ်ဝယ်မယ်ဆို သိထားသင့်တဲ့အချက် ၅ ချက်",
        "ဖုန်းအားသွင်းတဲ့အခါ သတိထားရမယ့်အချက်များ",
        "Redmi Note 14 Pro ရဲ့ အားသာချက်များ",
    ]

def save_topics(topics):
    """Topic စာရင်းကို topics.txt မှာ သိမ်းမယ်"""
    with open("topics.txt", "w", encoding="utf-8") as f:
        for topic in topics:
            f.write(topic + "\n")

def add_topic(topic):
    """Topic အသစ်ထည့်မယ်"""
    topics = load_topics()
    if topic in topics:
        return False, "❌ ဒီ Topic ရှိပြီးသားပါ။"
    topics.append(topic)
    save_topics(topics)
    return True, f"✅ Topic အသစ်ထည့်ပြီးပါပြီ။\n\n📌 {topic}"

def remove_topic(index):
    """နံပါတ်အလိုက် Topic ဖျက်မယ်"""
    topics = load_topics()
    if 1 <= index <= len(topics):
        removed = topics.pop(index - 1)
        save_topics(topics)
        return True, f"✅ ဖျက်ပြီးပါပြီ။\n\n❌ {removed}"
    return False, f"❌ နံပါတ် {index} က မရှိပါ။ (၁ မှ {len(topics)} အတွင်းထည့်ပါ)"

def get_topics_list_text():
    """Topic စာရင်းကိ် လှလှပပ format လုပ်မယ်"""
    topics = load_topics()
    if not topics:
        return "📭 topics.txt ထဲမှာ Topic မရှိသေးပါ။"
    
    text = f"📚 **Topic List** (စုစုပေါင်း {len(topics)} ခု)\n\n"
    for i, topic in enumerate(topics):
        text += f"{i+1}. {topic}\n"
    return text

# ---------------- GEMINI FUNCTION ---------------- #
def generate_gemini_text(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={GEMINI_API_KEY}"
    
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
def send_message_to_telegram(text, chat_id=None):
    if chat_id is None:
        chat_id = TELEGRAM_CHAT_ID
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text[:4000],
        "parse_mode": "Markdown"
    }
    response = requests.post(url, json=payload, timeout=60)
    
    if response.status_code != 200:
        print(f"Telegram Error: {response.text}")
    return response.status_code == 200

def get_updates(offset=None):
    """Telegram ကနေ message အသစ်တွေ ယူမယ်"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    
    response = requests.get(url, params=params, timeout=35)
    if response.status_code == 200:
        return response.json().get("result", [])
    return []

# ---------------- COMMAND HANDLERS ---------------- #
def handle_command(chat_id, command, args):
    """Telegram command တွေကို ကိုင်တွယ်မယ်"""
    
    if command == "/view_topics":
        text = get_topics_list_text()
        send_message_to_telegram(text, chat_id)
    
    elif command == "/add_topic":
        if not args:
            send_message_to_telegram(
                "❌ Topic အမည်ထည့်ပေးပါ။\n\nဥပမာ: `/add_topic ဖုန်းအသစ်ဝယ်မယ်ဆို သိထားသင့်တဲ့အချက်`",
                chat_id
            )
            return
        success, message = add_topic(args)
        send_message_to_telegram(message, chat_id)
    
    elif command == "/remove_topic":
        if not args or not args.isdigit():
            send_message_to_telegram(
                f"❌ နံပါတ်ထည့်ပေးပါ။\n\n{get_topics_list_text()}\n\nဥပမာ: `/remove_topic 3`",
                chat_id
            )
            return
        success, message = remove_topic(int(args))
        send_message_to_telegram(message, chat_id)
    
    elif command == "/random_post":
        topics = load_topics()
        if not topics:
            send_message_to_telegram("❌ topics.txt ထဲမှာ Topic မရှိပါ။ `/add_topic` နဲ့ အရင်ထည့်ပါ။", chat_id)
            return
        
        topic = random.choice(topics)
        send_message_to_telegram(f"🎲 Random Topic ရွေးပေးလိုက်ပါပြီ!\n\n📌 {topic}\n\n⏳ Post တင်နေပါပြီ...", chat_id)
        
        try:
            content = generate_facebook_post(topic)
            send_message_to_telegram(content, TELEGRAM_CHAT_ID)
            send_message_to_telegram(f"✅ Post တင်ပြီးပါပြီ!\n\n📌 {topic}", chat_id)
        except Exception as e:
            send_message_to_telegram(f"❌ Post တင်ရာမှာ အဆင်မပြေပါ။\nError: {str(e)[:100]}", chat_id)
    
    elif command == "/start" or command == "/help":
        help_text = """
🤖 **Phone Shop Bot Commands**

📋 **Topic Management:**
• `/view_topics` - Topic စာရင်းကြည့်ရန်
• `/add_topic [topic]` - Topic အသစ်ထည့်ရန်
• `/remove_topic [နံပါတ်]` - Topic ဖျက်ရန်

📝 **Post:**
• `/random_post` - Random Topic ရွေးပြီး Post ချက်ချင်းတင်ရန်

⏰ **Auto Post:**
• မနက် ၈:၀၀ မှ ည ၈:၀၀ အထိ တစ်နာရီတစ်ခါ
"""
        send_message_to_telegram(help_text, chat_id)

# ---------------- BOT POLLING (Telegram Command တွေ နားထောင်မယ်) ---------------- #
def run_bot_polling():
    """Bot ကို အချိန်အကြာကြီး run ထားဖို့ - Local server အတွက်"""
    print("🤖 Bot is running... Waiting for commands...")
    last_update_id = 0
    
    while True:
        try:
            updates = get_updates(last_update_id + 1 if last_update_id else None)
            
            for update in updates:
                last_update_id = update.get("update_id")
                
                if "message" in update:
                    msg = update["message"]
                    chat_id = msg["chat"]["id"]
                    text = msg.get("text", "")
                    
                    if text.startswith("/"):
                        parts = text.split(" ", 1)
                        command = parts[0].lower()
                        args = parts[1] if len(parts) > 1 else ""
                        handle_command(chat_id, command, args)
            
            time.sleep(1)
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)

# ---------------- AUTO MODE (GitHub Actions ခေါ်မယ်) ---------------- #
def run_auto_post():
    """GitHub Actions က ဒီ function ကို နာရီတိုင်း ခေါ်မယ်"""
    print("🚀 Auto Post Started at", datetime.now())
    
    topics = load_topics()
    if not topics:
        print("❌ No topics found in topics.txt")
        return
    
    topic = random.choice(topics)
    print(f"📌 Selected Topic: {topic}")
    
    print("✍️ Generating content with Gemini...")
    content = generate_facebook_post(topic)
    
    print("📤 Sending to Telegram...")
    send_message_to_telegram(content)
    
    print("✅ All done!")

# ---------------- MAIN ---------------- #
if __name__ == "__main__":
    import time
    
    if len(sys.argv) > 1 and sys.argv[1] == "auto":
        # GitHub Actions mode
        run_auto_post()
    elif len(sys.argv) > 1 and sys.argv[1] == "bot":
        # Bot polling mode (ကိုယ်ပိုင် server မှာ run ဖို့)
        run_bot_polling()
    else:
        print("Usage:")
        print("  python main.py auto     # Run auto post once")
        print("  python main.py bot      # Run bot with commands")
