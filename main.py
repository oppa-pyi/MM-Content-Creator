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
