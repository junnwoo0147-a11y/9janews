import os
import sys
import json
import re
import urllib.request
from datetime import datetime
import threading
import time
import feedparser
from bs4 import BeautifulSoup
import telebot
import cloudinary
import cloudinary.uploader
import boto3
import signal
import atexit

LOCK_FILE = "/tmp/9ja_news_bot.lock"

def acquire_lock():
    if os.path.exists(LOCK_FILE):
        # Check if lock is stale (older than 5 minutes)
        if time.time() - os.path.getmtime(LOCK_FILE) < 300:
            print("❌ Another bot instance is running. Exiting...")
            sys.exit(1)
        os.remove(LOCK_FILE)
    
    # Create lock file
    with open(LOCK_FILE, 'w') as f:
        f.write(str(os.getpid()))

def release_lock():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)

acquire_lock()
atexit.register(release_lock)

# --- STAGE 0: CREDENTIAL HARDCODING ---
TELEGRAM_TOKEN = "8799270771:AAEUDhwhXaHq8cgfr1eIz9TdH9X3B0X604Y"
CHAT_ID = "6108841631"

# Hardcoded AWS Bedrock Token (As requested. Remember to revoke this later!)
os.environ["AWS_BEARER_TOKEN_BEDROCK"] = "ABSKQmVkcm9ja0FQSUtleS1qemdmLWF0LTQ0Mjg0NzMxODc2NjpobmV5N09sR29tdFliSXNnS1kxRHNUaDI3U2xRWDdmU2RRTm9kV3FzdTlNRzN6aC8zOFR2NXJZSGJydz0="

cloudinary.config(
    cloud_name="dttmavamx",
    api_key="336655594631775",
    api_secret="xydaLJiFP26S_BG_AgBbAmP7U00"
)

# Initialize Telegram SDK
bot = telebot.TeleBot(TELEGRAM_TOKEN)

def signal_handler(sig, frame):
    print("🛑 Shutting down bot gracefully...")
    # Stop any polling loops
    if bot:
        bot.stop_polling()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# --- STAGE 2: THE HUMAN-PULSE MASTER PROMPT (VERBATIM) ---
MASTER_PROMPT = """
ROLE:
You are a highly opinionated, passionate hobbyist and seasoned observer. You are NOT a content generator. You are a ghostwriter for a popular blog that people read specifically for its "real talk,[...]

TASK:
The category for this post is {category}.
Write a short, high-substance article based on the following data: {article_data}

RULE 1: NO HALLUCINATIONS (STRICT GROUNDING)
 * You must use the core facts provided in the input.
 * Do NOT invent names, dates, or events that are not present.
 * Atmospheric Exception: You may invent sensory "fluff" to ground the piece in reality (e.g., describing a crowded room, the weather, or a specific feeling), but the news core must remain 100% ac[...]

RULE 2: THE TITLE (SUMMARY + CURIOSITY)
 * Formula: [Detailed Action/Event] + [Unanswered Question or Opinionated Twist].
 * Forbidden: Clickbait tropes ("You won't believe," "X things about...", "This changes everything").
 * Example (Tech): "The new Apple update finally fixes the battery drain, but the privacy trade-off feels like a step backward."

RULE 3: THE "HUMAN DEFECT" STYLE (ANTI-DETECTION)
 * High Burstiness (RANDOMIZED LAYOUT): Vary sentence and paragraph lengths aggressively throughout the entire piece. 
 * Dynamic Execution: You can use the pattern of a long, rambling thought sentence followed by a 3-word punch, but ONLY use it once or twice in the entire article. Mix it up. Use a single-sentence[...]
 * Vocabulary Search & Destroy: Completely banish statistical AI markers. If you use them, the text fails. Never use: "delve", "testament", "tapestry", "landscape", "furthermore", "moreover", "in [...]

RULE 4: SENSORY "WITNESS" LAYER
To prove you "were there," include one hyper-specific sensory detail related to the news category:
 * Tech: The annoying fan noise of a laptop, a smudge on a glossy screen, or the tactical click of a worn-out mechanical keyboard.
 * General/Politics: The way people in the background were looking at their phones, a heavy silence in the room, or the dim buzz of fluorescent office lights.
 * Finance/Sports: The chaotic feeling of a green/red ticker, the coffee-fueled energy of the press box, or a sudden gasp from a specific corner of a crowded room.

INTERNAL MONOLOGUE:
Before you write, internally list the 3 most "robotic" ways to report this news and then deliberately choose a 4th, more conversational path. Ensure your rhythm doesn't follow a standard 5-sentenc[...]
"""

# Global processing queue for man-in-the-loop tracking
PENDING_QUEUE = []
CURRENT_PROCESSING_ITEM = None
JSON_FILE_PATH = "data/articles.json"
queue_lock = threading.Lock()


def generate_slug(title):
    slug = title.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_-]+', '-', slug)
    return slug


# Dynamic category-based fallback image
def extract_image_url(entry, category):
    if 'media_content' in entry and len(entry.media_content) > 0:
        return entry.media_content[0].get('url')
    if 'links' in entry:
        for link in entry.links:
            if 'image' in link.get('type', ''):
                return link.get('href')
    
    html_target = ""
    if 'summary' in entry:
        html_target += entry.summary
    if 'content' in entry:
        for c in entry.content:
            html_target += c.value
            
    if html_target:
        try:
            soup = BeautifulSoup(html_target, "html.parser")
            img = soup.find("img")
            if img and img.get("src"):
                return img["src"]
        except Exception:
            pass
            
    if category.lower() == "sports":
        return "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?q=80&w=1200&h=800&fit=crop"
    else:
        return "https://images.unsplash.com/photo-1541872703-74c5e44368f9?q=80&w=1200&h=800&fit=crop"


def upload_to_cloudinary(url_source, title_seed):
    try:
        clean_id = "".join(c for c in title_seed if c.isalnum() or c in (" ", "_", "-")).strip()[:40]
        public_id = f"discover_{int(datetime.now().timestamp())}_{clean_id.replace(' ', '_')}"
        
        response = cloudinary.uploader.upload(
            url_source,
            public_id=public_id,
            folder="discover_images",
            transformation=[
                {"width": 1200, "height": 800, "crop": "fill", "gravity": "auto"}
            ]
        )
        return response.get("secure_url")
    except Exception as e:
        print(f"⚠️ Cloudinary Error: {e}. Cascading to raw feed source.")
        return url_source


def generate_ai_article(category, old_title, old_summary):
    article_data = f"TITLE: {old_title} | SUMMARY: {old_summary}"
    
    system_instruction_wrapper = (
        "Output your entire response inside standard HTML <p></p> paragraph blocks. "
        "Do not include Markdown syntax, ```html containers, or outer page wrappers. "
        "The first line of text must contain the Title, also wrapped in its own single <p> block."
    )
    
    # Combine the creative prompt with the strict output format
    combined_system_prompt = f"{MASTER_PROMPT}\n\n{system_instruction_wrapper}"
    user_prompt = f"Category: {category}\nData: {article_data}"
    
    # Setup the Claude 3.5 Sonnet payload architecture for AWS Bedrock
    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4000,
        "temperature": 0.75,
        "system": combined_system_prompt,
        "messages": [
            {
                "role": "user",
                "content": user_prompt
            }
        ]
    }
    
    try:
        bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")
        model_id = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
        
        response = bedrock_runtime.invoke_model(
            modelId=model_id,
            body=json.dumps(payload)
        )
        response_body = json.loads(response.get("body").read())
        
        return response_body["content"][0]["text"]
        
    except Exception as e:
        return f"<p>Claude Bedrock Execution Error: {str(e)}</p>"


def prepend_to_json_file(article_object):
    try:
        os.makedirs(os.path.dirname(JSON_FILE_PATH), exist_ok=True)
        
        if os.path.exists(JSON_FILE_PATH):
            with open(JSON_FILE_PATH, "r", encoding="utf-8") as f:
                try:
                    existing_data = json.load(f)
                except json.JSONDecodeError:
                    existing_data = []
        else:
            existing_data = []
            
        if not isinstance(existing_data, list):
            print("❌ Error: Existing JSON structure is not a list. Aborting.")
            return False
                    
        existing_data.insert(0, article_object)
        
        with open(JSON_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, indent=2, ensure_ascii=False)
            
        print(f"💾 Successfully prepended article: {article_object['slug']}")
        return True
    except Exception as e:
        print(f"❌ Critical storage write error: {e}")
        return False 


def dispatch_next_queue_item():
    global CURRENT_PROCESSING_ITEM
    with queue_lock:
        if not PENDING_QUEUE:
            CURRENT_PROCESSING_ITEM = None
            return

        CURRENT_PROCESSING_ITEM = PENDING_QUEUE.pop(0)
    
    print(f"Processing candidate for Telegram validation: {CURRENT_PROCESSING_ITEM['old_title']}")
    
    ai_output = generate_ai_article(
        CURRENT_PROCESSING_ITEM["category"],
        CURRENT_PROCESSING_ITEM["old_title"],
        CURRENT_PROCESSING_ITEM["old_summary"]
    )
    
    CURRENT_PROCESSING_ITEM["ai_raw_output"] = ai_output
    
    paragraphs = re.findall(r'<p>(.*?)</p>', ai_output, re.DOTALL)
    ai_title = paragraphs[0] if paragraphs else CURRENT_PROCESSING_ITEM["old_title"]
    ai_content_only = "".join([f"<p>{p}</p>" for p in paragraphs[1:]]) if len(paragraphs) > 1 else ai_output

    CURRENT_PROCESSING_ITEM["extracted_title"] = ai_title
    CURRENT_PROCESSING_ITEM["extracted_content"] = ai_content_only

    part1 = (
        f"🔍 **OLD ARTICLE DATA CLASSIFIED AT:**\n"
        f"Category: {CURRENT_PROCESSING_ITEM['category']}\n"
        f"Title: {CURRENT_PROCESSING_ITEM['old_title']}\n"
        f"Summary: {CURRENT_PROCESSING_ITEM['old_summary']}\n\n"
        f"====================================\n\n"
        f"✨ **NEW AI RECORD ENTRY**\n"
        f"Title: {ai_title}"
    )
    bot.send_message(CHAT_ID, part1, parse_mode="Markdown")
    
    clean_content = re.sub(r'<[^>]*>', '', ai_content_only)
    max_length = 4000
    
    if len(clean_content) > max_length:
        chunks = [clean_content[i:i+max_length] for i in range(0, len(clean_content), max_length)]
        for idx, chunk in enumerate(chunks):
            header = f"📄 **Content (Part {idx+1}/{len(chunks)})**:\n" if idx > 0 else "📄 **Content**:\n"
            bot.send_message(CHAT_ID, header + chunk, parse_mode="Markdown")
    else:
        bot.send_message(CHAT_ID, f"📄 **Content**:\n{clean_content}", parse_mode="Markdown")
    
    part3 = (
        f"🕒 *Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n"
        f"👉 _Reply directly to this text to authorize or apply custom edits._"
    )
    bot.send_message(CHAT_ID, part3, parse_mode="Markdown")


@bot.message_handler(func=lambda msg: msg.text and msg.text.startswith("Category:") and str(msg.chat.id) == CHAT_ID)
def handle_manual_injection(message):
    bot.reply_to(message, "🚨 **Manual Breaking News Received! Injecting into pipeline...**")
    text = message.text
    
    try:
        category = re.search(r'Category:\s*(.+)', text, re.IGNORECASE).group(1).strip()
        title = re.search(r'Title:\s*(.+)', text, re.IGNORECASE).group(1).strip()
        summary = re.search(r'Summary:\s*(.+)', text, re.IGNORECASE | re.DOTALL).group(1).strip()
        
        raw_img_source = "https://images.unsplash.com/photo-1541872703-74c5e44368f9?q=80&w=1200&h=800&fit=crop"
        optimized_cloudinary_url = upload_to_cloudinary(raw_img_source, title)
        
        with queue_lock:
            PENDING_QUEUE.append({
                "category": category,
                "old_title": title,
                "old_summary": summary,
                "cloudinary_url": optimized_cloudinary_url
            })
            
        if CURRENT_PROCESSING_ITEM is None:
            dispatch_next_queue_item()
            
    except AttributeError:
        bot.send_message(CHAT_ID, "❌ **Error parsing manual injection.** Ensure it contains 'Category:', 'Title:', and 'Summary:' on separate lines.")


@bot.message_handler(func=lambda msg: not (msg.text and msg.text.startswith("Category:")))
def process_user_approval_response(message):
    global CURRENT_PROCESSING_ITEM
    if str(message.chat.id) != CHAT_ID or not CURRENT_PROCESSING_ITEM:
        return

    bot.reply_to(message, "⚙️ **Processing verification update... Updating target database...**")
    
    user_input = message.text.strip()
    
    final_title = CURRENT_PROCESSING_ITEM["extracted_title"]
    final_content = CURRENT_PROCESSING_ITEM["extracted_content"]
    
    if user_input.lower() not in ("yes", "approve", "ok", "go", "publish"):
        if "title:" in user_input.lower():
            lines = user_input.split('\n')
            t_line = [l for l in lines if l.lower().startswith("title:")]
            if t_line:
                final_title = t_line[0].replace("Title:", "").replace("title:", "").strip()
            c_lines = [l for l in lines if not l.lower().startswith("title:")]
            final_content = "\n".join(c_lines).strip()
        else:
            final_content = user_input

    execution_time_marker = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    
    clean_text_layer = re.sub(r'<[^>]*>', '', final_content)
    
    article_payload = {
        "slug": generate_slug(final_title),
        "title": final_title,
        "description": clean_text_layer[:147] + "...",
        "intro": clean_text_layer[:47] + "...",
        "content": final_content,
        "image": CURRENT_PROCESSING_ITEM["cloudinary_url"],
        "datePublished": execution_time_marker,
        "dateModified": execution_time_marker,
        "category": CURRENT_PROCESSING_ITEM["category"].lower(),
        "trendingBoost": 3
    }
    
    success = prepend_to_json_file(article_payload)
    
    if success:
        bot.send_message(
            CHAT_ID, 
            f"✅ **Successfully Saved!**\n"
            f"Slug: `{article_payload['slug']}`\n"
            f"Time Logged: `{execution_time_marker}`"
        )
    else:
        bot.send_message(CHAT_ID, "❌ **Error committing dynamic JSON record change to storage layer.**")

    # Forcefully shut down the script to signal GitHub Actions to save the JSON file
    print("✅ Work complete. Shutting down script so GitHub can commit changes.")
    bot.stop_polling()  
    sys.exit(0)


# --- STAGE 1: CRAWLER (MODIFIED FOR EXACTLY 1 EACH) ---
def execute_feed_crawl():
    global PENDING_QUEUE
    print(f"🕒 Scheduled Crawl Triggered at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # NEW RSS LINKS INJECTED HERE
    sources = [
        {"url": "https://allnigeriasoccer.com/feed/", "category": "Sports"},
        {"url": "https://www.vanguardngr.com/category/politics/", "category": "Politics"}
    ]
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    football_signals = [
        "football", "premier league", "laliga", "serie", "bundesliga", "champions league", 
        "transfers", "osimhen", "galatasaray", "arteta", "clash", "chelsea", "arsenal", 
        "manchester", "liverpool", "bale", "fifa", "uefa", "striker", "derby", "raya"
    ]

    new_items = []

    for source in sources:
        try:
            req = urllib.request.Request(source["url"], headers=headers)
            with urllib.request.urlopen(req, timeout=15) as response:
                feed_data = feedparser.parse(response.read())
            
            if not feed_data.entries:
                continue

            saved_count = 0
            for entry in feed_data.entries:
                if saved_count >= 1:
                    break
                
                title_clean = entry.get('title', '')
                summary_clean = entry.get('summary', '')
                
                if source["category"] == "Sports":
                    search_space = (title_clean + " " + summary_clean).lower()
                    if not any(keyword in search_space for keyword in football_signals):
                        continue
                
                raw_img_source = extract_image_url(entry, source["category"])
                optimized_cloudinary_url = upload_to_cloudinary(raw_img_source, title_clean)
                
                new_items.append({
                    "category": source["category"],
                    "old_title": title_clean,
                    "old_summary": summary_clean,
                    "cloudinary_url": optimized_cloudinary_url
                })
                saved_count += 1
                
        except Exception as e:
            print(f"❌ Feed processing exception: {e}")

    with queue_lock:
        PENDING_QUEUE.extend(new_items)
        
    if CURRENT_PROCESSING_ITEM is None:
        dispatch_next_queue_item()

# --- STAGE 4: MAIN EXECUTION TRIGGER ---
if __name__ == "__main__":
    print("🚀 Waking up News Pulse Bot...")
    
    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception as e:
        pass
        
    print("🔍 Crawling RSS feeds for fresh news...")
    execute_feed_crawl()
    
    print("📥 Waiting for your reply in Telegram to authorize publishing...")
    bot.polling(skip_pending=True, timeout=10, long_polling_timeout=10)
