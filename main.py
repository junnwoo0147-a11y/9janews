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
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

LOCK_FILE = os.getenv("LOCK_FILE", "/tmp/9ja_news_bot.lock")
JSON_FILE_PATH = os.getenv("JSON_FILE_PATH", "data/articles.json")

# Retry configuration for API rate limiting
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
INITIAL_BACKOFF = int(os.getenv("INITIAL_BACKOFF", 2))

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

# --- STAGE 1: ENVIRONMENT CREDENTIAL LOADING ---
POLITICS_API_KEY = os.getenv("POLITICS_API_KEY")
POLITICS_AGENT_ID = os.getenv("POLITICS_AGENT_ID")

SPORTS_API_KEY = os.getenv("SPORTS_API_KEY")
SPORTS_AGENT_ID = os.getenv("SPORTS_AGENT_ID")

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
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
    """Extract image URL from feed entry with multiple fallback strategies"""
    
    # Strategy 1: Check media_content
    if 'media_content' in entry and len(entry.media_content) > 0:
        img_url = entry.media_content[0].get('url')
        if img_url:
            print(f"  ✓ Found image in media_content")
            return img_url
    
    # Strategy 2: Check links for image type
    if 'links' in entry:
        for link in entry.links:
            if 'image' in link.get('type', '').lower():
                img_url = link.get('href')
                if img_url:
                    print(f"  ✓ Found image in links")
                    return img_url
    
    # Strategy 3: Parse HTML content for img tags
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
                img_url = img["src"]
                print(f"  ✓ Found image in HTML content")
                return img_url
        except Exception as e:
            print(f"  ⚠️ HTML parsing failed: {e}")
    
    # Fallback: Use category-specific default
    if category.lower() == "sports":
        fallback_url = "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?q=80&w=1200&h=800&fit=crop"
        print(f"  ⚠️ No image found in entry, using sports default")
    else:
        fallback_url = "https://images.unsplash.com/photo-1541872703-74c5e44368f9?q=80&w=1200&h=800&fit=crop"
        print(f"  ⚠️ No image found in entry, using politics default")
    
    return fallback_url

def upload_to_cloudinary(url_source, title_seed, category):
    """
    Uploads remote image URL directly to Cloudinary, forcing WebP optimization 
    and a clean 1200x800 smart-gravity crop. No local temp files used.
    """
    try:
        url_source = url_source.strip().replace(" ", "%20")
        if url_source.startswith("//"):
            url_source = "https:" + url_source
        
        print(f"  📥 Passing URL source to Cloudinary server: {url_source[:65]}...")
        
        # Generate unique public ID
        clean_id = "".join(c for c in title_seed if c.isalnum() or c in (" ", "_", "-")).strip()[:40]
        public_id = f"discover_{int(datetime.now().timestamp())}_{clean_id.replace(' ', '_')}"
        
        # Upload remote URL directly with format conversion and dimensions modification
        upload_response = cloudinary.uploader.upload(
            url_source,
            public_id=public_id,
            folder=f"discover_images/{category.lower()}",
            format="webp",  # Converts to optimized WebP format automatically
            transformation=[
                {
                    "width": 1200, 
                    "height": 800, 
                    "crop": "fill",  
                    "gravity": "auto"  
                }
            ],
            overwrite=True,
            resource_type="auto"
        )
        
        cloudinary_url = upload_response.get("secure_url")
        print(f"  ✓ Cloudinary WebP URL: {cloudinary_url[:60]}...")
        return cloudinary_url
        
    except Exception as e:
        print(f"  ❌ Direct Cloudinary upload/transformation failed: {e}")
        return None

# --- STAGE 2: CATEGORY ROUTED MISTRAL API CALLS WITH RETRY ---
def generate_ai_article(category, old_title, old_summary):
    """
    Generate AI article with retry logic for rate limiting.
    Returns the AI-generated content or None if all retries fail.
    """
    article_data = f"TITLE: {old_title} | SUMMARY: {old_summary}"
    
    user_prompt = (
        f"Output your response inside standard HTML <p></p> paragraph blocks. "
        f"Do not include Markdown syntax or markdown code fences (like ```html). "
        f"The first paragraph block must contain the generated Title.\n\n"
        f"Category: {category}\nData: {article_data}"
    )
    
    for attempt in range(MAX_RETRIES):
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
            
            ai_content = response.choices[0].message.content
            print(f"  ✓ AI content generated successfully")
            return ai_content
            
        except Exception as e:
            error_str = str(e)
            
            # Check for rate limiting errors
            if "429" in error_str or "capacity exceeded" in error_str or "service_tier_capacity_exceeded" in error_str:
                if attempt < MAX_RETRIES - 1:
                    backoff_time = INITIAL_BACKOFF * (2 ** attempt)
                    print(f"  ⚠️ Rate limited (attempt {attempt + 1}/{MAX_RETRIES}). Waiting {backoff_time}s before retry...")
                    time.sleep(backoff_time)
                    continue
                else:
                    print(f"  ❌ Mistral API rate limit persists after {MAX_RETRIES} attempts")
                    return None
            else:
                # Other errors - don't retry
                print(f"  ❌ Mistral API error: {e}")
                return None
    
    return None

# --- STAGE 3: LIVE PREPENDING STORAGE ARCHITECTURE ---
def prepend_to_json_file(article_object):
    """Save article to JSON, prepending to the beginning of the list"""
    try:
        os.makedirs(os.path.dirname(JSON_FILE_PATH), exist_ok=True)
        
        if os.path.exists(JSON_FILE_PATH):
            with open(JSON_FILE_PATH, "r", encoding="utf-8") as f:
                try:
                    existing_data = json.load(f)
                except json.JSONDecodeError:
                    print(f"  ⚠️ Corrupted JSON file, starting fresh")
                    existing_data = []
        else:
            existing_data = []
            
        if not isinstance(existing_data, list):
            print(f"  ❌ JSON structure error: not a list. Aborting save.")
            return False
                    
        existing_data.insert(0, article_object)
        
        with open(JSON_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, indent=2, ensure_ascii=False)
            
        print(f"  ✓ Article saved: {article_object['slug']}")
        print(f"    - Category: {article_object['category']}")
        print(f"    - Image: {article_object['image'][:60]}...")
        return True
        
    except Exception as e:
        print(f"  ❌ JSON storage error: {e}")
        return False 

def process_and_save_item(item_data):
    """
    Process a single feed item: download image, generate AI content, and save to JSON
    """
    print(f"\n🔄 Processing: {item_data['old_title'][:60]}...")
    
    # Step 1: Upload image to Cloudinary
    print(f"  [1/3] Image Processing:")
    cloudinary_url = upload_to_cloudinary(
        item_data["raw_image_url"],
        item_data["old_title"],
        item_data["category"]
    )
    
    if not cloudinary_url:
        print(f"  ⚠️ Image upload failed, skipping article")
        return False
    
    item_data["cloudinary_url"] = cloudinary_url
    
    # Step 2: Generate AI content
    print(f"  [2/3] AI Content Generation:")
    ai_output = generate_ai_article(
        item_data["category"],
        item_data["old_title"],
        item_data["old_summary"]
    )
    
    if not ai_output:
        print(f"  ⚠️ AI generation failed, skipping article")
        return False
    
    # Step 3: Parse and structure AI output
    print(f"  [3/3] Structuring Article:")
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
    
    success = prepend_to_json_file(article_payload)
    return success

# --- STAGE 4: CRAWLER PIPELINE RUNNER ---
def execute_feed_crawl():
    """Main crawler pipeline that processes feed sources"""
    print(f"🕒 Pipeline Execution Initiated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    has_critical_error = False
    total_processed = 0
    
    sources = [
        {"url": "https://allnigeriasoccer.com/feed/", "category": "Sports"},
        {"url": "https://www.vanguardngr.com/category/politics/feed/", "category": "Politics"}
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    football_signals = [
        "football", "premier league", "laliga", "serie", "bundesliga", "champions league", 
        "transfers", "osimhen", "galatasaray", "arteta", "clash", "chelsea", "arsenal", 
        "manchester", "liverpool", "bale", "fifa", "uefa", "striker", "derby", "raya"
    ]

    for source in sources:
        # Rate Limiting Guard: Wait 2.5 minutes (150 seconds) before processing the next source
        if total_processed > 0:
            print(f"\n⏳ Delaying 2.5 minutes before hitting the next AI Engine to prevent rate limit errors...")
            time.sleep(150)

        print(f"\n{'='*60}")
        print(f"📰 Processing {source['category']} Feed")
        print(f"{'='*60}")
        
        try:
            req = urllib.request.Request(source["url"], headers=headers)
            with urllib.request.urlopen(req, timeout=15) as response:
                feed_data = feedparser.parse(response.read())
            
            if not feed_data.entries:
                print(f"⚠️ No entries found in {source['category']} feed")
                continue

            # Only look at the single most recent article entry
            latest_entry = feed_data.entries[0]
            print(f"📊 Evaluated the latest entry out of {len(feed_data.entries)} total items found.")
            
            title_clean = latest_entry.get('title', '')
            summary_clean = latest_entry.get('summary', '')
            
            # Sports category: filter by keywords
            if source["category"] == "Sports":
                search_space = (title_clean + " " + summary_clean).lower()
                if not any(keyword in search_space for keyword in football_signals):
                    print(f"  ⏭️ Skipped latest: Headline doesn't match current sports filtering signals.")
                    continue
            
            # Extract image URL
            raw_img_source = extract_image_url(latest_entry, source["category"])
            
            current_item = {
                "category": source["category"],
                "old_title": title_clean,
                "old_summary": summary_clean,
                "raw_image_url": raw_img_source,
                "cloudinary_url": None
            }
            
            # Process and save the item
            success = process_and_save_item(current_item)
            if success:
                total_processed += 1
                     
        except urllib.error.URLError as e:
            print(f"❌ Feed URL Error for {source['category']}: {e.reason}")
            has_critical_error = True
        except Exception as e:
            print(f"❌ Feed processing exception for {source['category']}: {e}")
            has_critical_error = True
    
    print(f"\n{'='*60}")
    print(f"✅ Pipeline Complete - Processed: {total_processed} articles")
    print(f"{'='*60}")
    
    return has_critical_error

if __name__ == "__main__":
    print("🚀 Waking up Automated News Pulse Scraper Machine...")
    pipeline_failed = execute_feed_crawl()
    
    if pipeline_failed:
        print("🏁 Sequence complete WITH ERRORS. Check logs above.")
        sys.exit(1)
    else:
        print("🏁 Sequence complete. Exiting clean.")
        sys.exit(0)
