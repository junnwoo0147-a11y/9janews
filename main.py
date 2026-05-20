import os
import sys
import json
import re
import urllib.request
from datetime import datetime
import time
import feedparser
from bs4 import BeautifulSoup
import cloudinary
import cloudinary.uploader
import signal
import atexit
from mistralai import Mistral

LOCK_FILE = "/tmp/9ja_news_bot.lock"
JSON_FILE_PATH = "data/articles.json"

def acquire_lock():
    if os.path.exists(LOCK_FILE):
        if time.time() - os.path.getmtime(LOCK_FILE) < 300:
            print("❌ Another bot instance is running. Exiting...")
            sys.exit(1)
        os.remove(LOCK_FILE)
    
    with open(LOCK_FILE, 'w') as f:
        f.write(str(os.getpid()))

def release_lock():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)

acquire_lock()
atexit.register(release_lock)

# --- STAGE 1: DUAL MISTRAL & CLOUDINARY CREDENTIALS ---
POLITICS_API_KEY = "zt7EHZL5BI5jIP4KqhqG5Riea9T7aJcL"
POLITICS_AGENT_ID = "ag_019e4724fb8c725db14acb1aaa4cb658"

SPORTS_API_KEY = "zt7EHZL5BI5jIP4KqhqG5Riea9T7aJcL"
SPORTS_AGENT_ID = "ag_019e47c1582372a2a31331f84c76ed54"

cloudinary.config(
    cloud_name="dttmavamx",
    api_key="336655594631775",
    api_secret="xydaLJiFP26S_BG_AgBbAmP7U00"
)

def signal_handler(sig, frame):
    print("🛑 Shutting down pipeline gracefully...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def generate_slug(title):
    slug = title.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_-]+', '-', slug)
    return slug

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
        url_source = url_source.strip().replace(" ", "%20")
        if url_source.startswith("//"):
            url_source = "https:" + url_source
            
        clean_id = "".join(c for c in title_seed if c.isalnum() or c in (" ", "_", "-")).strip()[:40]
        public_id = f"discover_{int(datetime.now().timestamp())}_{clean_id.replace(' ', '_')}"
        temp_image_path = f"/tmp/{public_id}.jpg"
        
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        req = urllib.request.Request(url_source, headers=headers)
        
        with urllib.request.urlopen(req, timeout=15) as response, open(temp_image_path, 'wb') as out_file:
            out_file.write(response.read())
        
        upload_response = cloudinary.uploader.upload(
            temp_image_path,
            public_id=public_id,
            folder="discover_images",
            transformation=[
                {"width": 1200, "height": 800, "crop": "fill", "gravity": "auto"}
            ]
        )
        
        if os.path.exists(temp_image_path):
            os.remove(temp_image_path)
            
        return upload_response.get("secure_url")
    except Exception as e:
        print(f"⚠️ Cloudinary/Download Error for {url_source}: {e}. Cascading to raw feed source.")
        return url_source

# --- STAGE 2: CATEGORY ROUTED MISTRAL API CALLS ---
def generate_ai_article(category, old_title, old_summary):
    article_data = f"TITLE: {old_title} | SUMMARY: {old_summary}"
    
    user_prompt = (
        f"Output your response inside standard HTML <p></p> paragraph blocks. "
        f"Do not include Markdown syntax or markdown code fences (like ```html). "
        f"The first paragraph block must contain the generated Title.\n\n"
        f"Category: {category}\nData: {article_data}"
    )
    
    try:
        if category.lower() == "sports":
            print(f"⚽ Dispatching to Mistral Sports Project Engine ({SPORTS_AGENT_ID})...")
            client = Mistral(api_key=SPORTS_API_KEY)
            response = client.agents.complete(
                agent_id=SPORTS_AGENT_ID,
                messages=[{"role": "user", "content": user_prompt}]
            )
        else:
            print(f"🤖 Dispatching to Mistral Politics Project Engine ({POLITICS_AGENT_ID})...")
            client = Mistral(api_key=POLITICS_API_KEY)
            response = client.agents.complete(
                agent_id=POLITICS_AGENT_ID,
                messages=[{"role": "user", "content": user_prompt}]
            )
            
        return response.choices[0].message.content
        
    except Exception as e:
        print(f"❌ Mistral API Execution Failure: {e}")
        # Fix: Return None instead of returning the error string so it doesn't get saved
        return None

# --- STAGE 3: LIVE PREPENDING STORAGE ARCHITECTURE ---
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
            print("❌ Error: Existing JSON structure is corrupted or not a list. Aborting.")
            return False
                    
        existing_data.insert(0, article_object)
        
        with open(JSON_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, indent=2, ensure_ascii=False)
            
        print(f"💾 Successfully saved and prepended article: {article_object['slug']}")
        return True
    except Exception as e:
        print(f"❌ Critical JSON storage write error: {e}")
        return False 

def process_and_save_item(item_data):
    print(f"Refining news item: {item_data['old_title']}")
    
    ai_output = generate_ai_article(
        item_data["category"],
        item_data["old_title"],
        item_data["old_summary"]
    )
    
    # Fix: If ai_output is None (due to Mistral API error), abort saving
    if not ai_output:
        print("⚠️ Aborting save: AI failed to generate article content.")
        return False
    
    paragraphs = re.findall(r'<p>(.*?)</p>', ai_output, re.DOTALL)
    ai_title = paragraphs[0].strip() if paragraphs else item_data["old_title"]
    ai_content_only = "".join([f"<p>{p.strip()}</p>" for p in paragraphs[1:]]) if len(paragraphs) > 1 else ai_output

    execution_time_marker = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    clean_text_layer = re.sub(r'<[^>]*>', '', ai_content_only)
    
    article_payload = {
        "slug": generate_slug(ai_title),
        "title": ai_title,
        "description": clean_text_layer[:147] + "...",
        "intro": clean_text_layer[:47] + "...",
        "content": ai_content_only,
        "image": item_data["cloudinary_url"],
        "datePublished": execution_time_marker,
        "dateModified": execution_time_marker,
        "category": item_data["category"].lower(),
        "trendingBoost": 3
    }
    
    prepend_to_json_file(article_payload)
    return True

# --- STAGE 4: CRAWLER PIPELINE RUNNER ---
def execute_feed_crawl():
    print(f"🕒 Pipeline Execution Initiated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    has_error = False
    
    sources = [
        {"url": "https://allnigeriasoccer.com/feed/", "category": "Sports"},
        {"url": "https://www.vanguardngr.com/category/politics/feed/", "category": "Politics"}
    ]
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    football_signals = [
        "football", "premier league", "laliga", "serie", "bundesliga", "champions league", 
        "transfers", "osimhen", "galatasaray", "arteta", "clash", "chelsea", "arsenal", 
        "manchester", "liverpool", "bale", "fifa", "uefa", "striker", "derby", "raya"
    ]

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
                
                current_item = {
                    "category": source["category"],
                    "old_title": title_clean,
                    "old_summary": summary_clean,
                    "cloudinary_url": optimized_cloudinary_url
                }
                
                # Fix: Check if it saved successfully. If false, flag the error.
                success = process_and_save_item(current_item)
                if success:
                    saved_count += 1
                else:
                    has_error = True
                
        except Exception as e:
            print(f"❌ Feed processing exception on {source['category']}: {e}")
            has_error = True
            
    return has_error

if __name__ == "__main__":
    print("🚀 Waking up Automated News Pulse Scraper Machine...")
    pipeline_failed = execute_feed_crawl()
    
    if pipeline_failed:
        print("🏁 Sequence complete with errors. Crashing Action.")
        sys.exit(1)
    else:
        print("🏁 Sequence complete. Exiting clean.")
