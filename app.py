import requests
import os
import random
import urllib.parse
import base64
import time
import logging
from datetime import datetime
from flask import Flask, request

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

TOPICS_FILE = "topics.txt"

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
        return False, "❌ ဒီ Topic ရှိပြီးသားပါ။"

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

    headers = {
        "Content-Type": "application/json"
    }

    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ]
    }

    for attempt in range(2):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=data,
                timeout=60
            )

            if response.status_code == 200:
                return response.json()["candidates"][0]["content"]["parts"][0]["text"]

            logging.error(response.text)

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

# ---------------- IMAGE GENERATION ---------------- #
def generate_image(prompt):

    logging.info(f"Generating image for: {prompt}")

    # Pollinations fallback
    safe_prompt = urllib.parse.quote(
        f"professional smartphone advertisement, {prompt}, white background, studio lighting"
    )

    img_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1024&height=1024&model=flux"

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        response = requests.get(
            img_url,
            headers=headers,
            timeout=60
        )

        if response.status_code == 200:
            return response.content

    except Exception as e:
        logging.error(f"Image generation error: {e}")

    return None

# ---------------- TELEGRAM ---------------- #
def send_telegram(text, chat_id=None):

    if chat_id is None:
        chat_id = TELEGRAM_CHAT_ID

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

    files = {
        "photo": ("image.jpg", image_bytes, "image/jpeg")
    }

    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "caption": caption[:200]
    }

    try:
        response = requests.post(
            url,
            files=files,
            data=data,
            timeout=60
        )

        return response.status_code == 200

    except Exception as e:
        logging.error(f"Photo send error: {e}")

    return False

# ---------------- WEBHOOK ---------------- #
@app.route(f"/webhook/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def webhook():

    update = request.get_json()

    if "message" in update:

        msg = update["message"]
        chat_id = str(msg["chat"]["id"])
        text = msg.get("text", "")

        # ADMIN PROTECTION
        if chat_id != str(1917675707):
            return "Unauthorized", 403

        logging.info(f"Command: {text}")

        # ---------------- START ---------------- #
        if text in ["/start", "/help"]:

            send_telegram(
                "🤖 Phone Shop AI Bot\n\n"
                "📋 Commands:\n"
                "/view_topics\n"
                "/add_topic [topic]\n"
                "/remove_topic [number]\n"
                "/write [topic]\n"
                "/write_topic [number]\n"
                "/random_post"
            )

        # ---------------- VIEW TOPICS ---------------- #
        elif text == "/view_topics":

            send_telegram(get_topics_list_text())

        # ---------------- ADD TOPIC ---------------- #
        elif text.startswith("/add_topic"):

            topic = text.replace("/add_topic", "").strip()

            if not topic:
                send_telegram("❌ Topic ထည့်ပါ")
            else:
                success, msg = add_topic(topic)
                send_telegram(msg)

        # ---------------- REMOVE TOPIC ---------------- #
        elif text.startswith("/remove_topic"):

            parts = text.split()

            if len(parts) != 2 or not parts[1].isdigit():
                send_telegram("❌ Example: /remove_topic 2")
            else:
                success, msg = remove_topic(int(parts[1]))
                send_telegram(msg)

        # ---------------- WRITE_TOPIC FIRST ---------------- #
        elif text.startswith("/write_topic"):

            parts = text.split()

            if len(parts) != 2 or not parts[1].isdigit():
                send_telegram("❌ Example: /write_topic 1")

            else:
                index = int(parts[1])
                topics = load_topics()

                if 1 <= index <= len(topics):

                    topic = topics[index - 1]

                    send_telegram(f"⏳ Generating...\n\n📌 {topic}")

                    try:
                        post = generate_post(topic)

                        send_telegram(post)

                        image = generate_image(topic)

                        if image:
                            send_photo(image, topic)

                        send_telegram("✅ Done")

                    except Exception as e:
                        logging.error(e)
                        send_telegram("❌ Failed")

        # ---------------- WRITE ---------------- #
        elif text.startswith("/write"):

            topic = text.replace("/write", "").strip()

            if not topic:
                send_telegram("❌ Example: /write iPhone 16 review")

            else:
                send_telegram(f"⏳ Generating...\n\n📌 {topic}")

                try:
                    post = generate_post(topic)

                    send_telegram(post)

                    image = generate_image(topic)

                    if image:
                        send_photo(image, topic)

                    send_telegram("✅ Done")

                except Exception as e:
                    logging.error(e)
                    send_telegram("❌ Failed")

        # ---------------- RANDOM POST ---------------- #
        elif text == "/random_post":

            topics = load_topics()

            if not topics:
                send_telegram("❌ No topics found")

            else:
                topic = random.choice(topics)

                send_telegram(f"🎲 Random Topic\n\n📌 {topic}")

                try:
                    post = generate_post(topic)

                    send_telegram(post)

                    image = generate_image(topic)

                    if image:
                        send_photo(image, topic)

                    send_telegram("✅ Posted")

                except Exception as e:
                    logging.error(e)
                    send_telegram("❌ Failed")

    return "OK", 200

# ---------------- AUTO POST ---------------- #
def run_auto_post():

    logging.info("Running auto post")

    topics = load_topics()

    if topics:

        topic = random.choice(topics)

        try:
            post = generate_post(topic)

            send_telegram(post)

            image = generate_image(topic)

            if image:
                send_photo(image, topic)

            logging.info("Auto post success")

        except Exception as e:
            logging.error(e)

# ---------------- MAIN ---------------- #
if __name__ == "__main__":

    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "auto":
        run_auto_post()

    else:
        port = int(os.environ.get("PORT", 5000))

        app.run(
            host="0.0.0.0",
            port=port
        )
