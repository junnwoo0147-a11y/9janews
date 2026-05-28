import os
import sys
import json
import re
import urllib.request
import urllib.parse
import http.client
import ssl
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import time
import signal
import atexit
import cloudinary
import cloudinary.uploader
from mistralai import Mistral

LOCK_FILE = "/tmp/9ja_news_bot.lock"
JSON_FILE_PATH = "data/articles.json"

# --- STAGE 0: PROCESS MANAGEMENT ---
def acquire_lock():
    if os.path.exists(LOCK_FILE):
        if time.time() - os.path.getmtime(LOCK_FILE) < 300:
            raise RuntimeError("PROCESS CRASH: Another bot instance is actively running. Terminating execution to protect state.")
        os.remove(LOCK_FILE)
    
    with open(LOCK_FILE, 'w') as f:
        f.write(str(os.getpid()))

def release_lock():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)

acquire_lock()
atexit.register(release_lock)

def signal_handler(sig, frame):
    raise KeyboardInterrupt(f"PROCESS CRASH: Received termination signal {sig}. Pipeline broken instantly.")

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# --- STAGE 1: CREDENTIALS & CONFIGURATION ---
SPORTS_API_KEY = os.getenv("SPORTS_API_KEY")
SPORTS_AGENT_ID = os.getenv("SPORTS_AGENT_ID")
CRITIC_AGENT_ID = os.getenv("CRITIC_AGENT_ID")
VALIDATOR_AGENT_ID = os.getenv("VALIDATOR_AGENT_ID")

# --- KEY ROTATION POOL INITIALIZATION ---
ant_keys_pool = [
    os.getenv("SCRAPINGANT_KEY"),
    os.getenv("SCRAPINGANT_KEY1"),
    os.getenv("SCRAPINGANT_KEY2"),
    os.getenv("SCRAPINGANT_KEY3"),
    os.getenv("SCRAPINGANT_KEY4")
]
SCRAPINGANT_KEYS = [key for key in ant_keys_pool if key]
CURRENT_ANT_INDEX = 0

required_secrets = {
    "SPORTS_API_KEY": SPORTS_API_KEY,
    "SPORTS_AGENT_ID": SPORTS_AGENT_ID,
    "CRITIC_AGENT_ID": CRITIC_AGENT_ID,
    "VALIDATOR_AGENT_ID": VALIDATOR_AGENT_ID
}

missing_secrets = [key for key, value in required_secrets.items() if not value]
if not SCRAPINGANT_KEYS:
    missing_secrets.append("SCRAPINGANT_KEY (or at least one sequential backup key SCRAPINGANT_KEY1-4)")

if missing_secrets:
    raise ValueError(f"CONFIG CRASH: Missing required environment variables: {', '.join(missing_secrets)}")

cloudinary_config = {
    "cloud_name": os.getenv("CLOUDINARY_CLOUD_NAME"),
    "api_key": os.getenv("CLOUDINARY_API_KEY"),
    "api_secret": os.getenv("CLOUDINARY_API_SECRET")
}

cloudinary_missing = [key for key, value in cloudinary_config.items() if not value]
if cloudinary_missing:
    raise ValueError(f"CONFIG CRASH: Missing required Cloudinary configuration parameters: {', '.join(cloudinary_missing)}")

cloudinary.config(**cloudinary_config)


# --- HELPERS AND UTIL STAGES ---
def generate_slug(title):
    slug = re.sub(r'<[^>]+>', '', title).lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    return re.sub(r'[\s_-]+', '-', slug)


def get_full_article_via_ant(external_url):
    """ Passes an external link to ScrapingAnt to extract raw text markdown. Crashes if pool is exhausted. """
    global CURRENT_ANT_INDEX
    
    encoded_ext = urllib.parse.quote_plus(external_url)
    total_key_count = len(SCRAPINGANT_KEYS)
    
    for _ in range(total_key_count):
        current_key = SCRAPINGANT_KEYS[CURRENT_ANT_INDEX]
        print(f"   [⚡ ScrapingAnt Deep Fetch] Fetching text using key slot [{CURRENT_ANT_INDEX}/{total_key_count-1}] for: {external_url}")
        
        try:
            # Standard proxy configuration applied explicitly
            ant_endpoint = f"/v2/markdown?url={encoded_ext}&x-api-key={current_key}&proxy_type=standard&browser=true&wait_for_selector=article"
            conn = http.client.HTTPSConnection("api.scrapingant.com", context=ssl._create_unverified_context())
            conn.request("GET", ant_endpoint)
            res = conn.getresponse()
            
            if res.status == 200:
                payload = json.loads(res.read().decode("utf-8"))
                conn.close()
                markdown_output = payload.get("markdown", "")
                
                if "ONLY AVAILABLE IN PAID PLANS" in markdown_output or not markdown_output.strip():
                    print(f"   ⚠️ ScrapingAnt Key at index [{CURRENT_ANT_INDEX}] exhausted. Rotating...")
                    CURRENT_ANT_INDEX = (CURRENT_ANT_INDEX + 1) % total_key_count
                    continue
                    
                return markdown_output
            else:
                print(f"   ⚠️ ScrapingAnt API error response (Status {res.status}) on slot [{CURRENT_ANT_INDEX}]. Rotating...")
                conn.close()
                CURRENT_ANT_INDEX = (CURRENT_ANT_INDEX + 1) % total_key_count
                
        except Exception as deep_err:
            print(f"   ⚠️ Exception on ScrapingAnt key slot [{CURRENT_ANT_INDEX}]: {deep_err}. Rotating...")
            CURRENT_ANT_INDEX = (CURRENT_ANT_INDEX + 1) % total_key_count
            
    raise RuntimeError(f"SCRAPER CRASH: Every configured ScrapingAnt key slot has failed or exhausted quota metrics for URL: {external_url}")


def execute_google_search_via_ant(search_query):
    """ Executes a live raw Google Search using ScrapingAnt standard browser instances. Crashes if pool fails. """
    global CURRENT_ANT_INDEX

    google_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(search_query)}"
    encoded_google = urllib.parse.quote_plus(google_url)
    total_key_count = len(SCRAPINGANT_KEYS)
    
    for _ in range(total_key_count):
        current_key = SCRAPINGANT_KEYS[CURRENT_ANT_INDEX]
        print(f"   [🔍 ScrapingAnt Google SERP] Executing Search queries via key slot [{CURRENT_ANT_INDEX}]...")
        
        try:
            ant_endpoint = f"/v2/general?url={encoded_google}&x-api-key={current_key}&proxy_type=standard&browser=true"
            conn = http.client.HTTPSConnection("api.scrapingant.com", context=ssl._create_unverified_context())
            conn.request("GET", ant_endpoint)
            res = conn.getresponse()
            
            if res.status == 200:
                payload = json.loads(res.read().decode("utf-8"))
                conn.close()
                html_content = payload.get("html", "")
                
                raw_links = re.findall(r'href="(https?://[^"]+)"', html_content)
                cleaned_urls = []
                
                for url in raw_links:
                    url_clean = url.split('&')[0].split('?')[0]
                    if "google.com" in url_clean or "webcache" in url_clean:
                        continue
                    if url_clean not in cleaned_urls and len(url_clean) > 12:
                        cleaned_urls.append(url_clean)
                
                return cleaned_urls
            else:
                print(f"   ⚠️ SERP Error (Status {res.status}) on key index [{CURRENT_ANT_INDEX}]. Rotating...")
                conn.close()
                CURRENT_ANT_INDEX = (CURRENT_ANT_INDEX + 1) % total_key_count
                
        except Exception as search_err:
            print(f"   ⚠️ SERP Exceptions caught on slot [{CURRENT_ANT_INDEX}]: {search_err}. Rotating...")
            CURRENT_ANT_INDEX = (CURRENT_ANT_INDEX + 1) % total_key_count
            
    raise RuntimeError(f"SERP CRASH: Every configured ScrapingAnt key slot failed during Google Query execution: {search_query}")


def verify_topic_match(source_text, candidate_text):
    """Cross-checks alignment by calling the custom Mistral Validator Agent. Crashes if integration breaks."""
    if not source_text.strip() or not candidate_text.strip():
        raise ValueError("VALIDATOR CRASH: Received empty payload strings for semantic evaluation source/candidate matrix.")
        
    client = Mistral(api_key=SPORTS_API_KEY)
    formatted_prompt = f"### TARGET TOPIC REFERENCE:\n{source_text}\n\n### CANDIDATE ARTICLE BODY:\n{candidate_text}"
    
    for attempt in range(3):
        try:
            response = client.agents.complete(
                agent_id=VALIDATOR_AGENT_ID,
                messages=[{"role": "user", "content": formatted_prompt}]
            )
            raw_output = response.choices[0].message.content.strip()
            
            json_match = re.search(r'\{.*\}', raw_output, re.DOTALL)
            if json_match:
                payload = json.loads(json_match.group(0))
            else:
                payload = json.loads(raw_output)
                
            is_valid = bool(payload.get("is_valid_match", False))
            score = float(payload.get("match_score", 0.0))
            reasoning = payload.get("reasoning", "No explanation specified.")
            
            print(f"     🧐 [Mistral Validator Agent] Score: {score:.2%} | Match: {is_valid} | Reason: {reasoning}")
            return is_valid, score
            
        except Exception as e:
            if "429" in str(e):
                print("     ⚠️ Rate limited on validator agent. Cooling down 10s...")
                time.sleep(10)
            else:
                print(f"     ⚠️ Validator agent anomaly: {e}. Retrying execution context...")
                time.sleep(2)
                
    raise RuntimeError("VALIDATOR CRASH: Mistral Validation Agent failed to output structured, parsable data after maximum retries.")


# --- STAGE 2: DATA FETCHING WITH TIMEOUTS & STATE DEDUPLICATION ---
TIMEOUT_LIMIT = 180       
TARGET_ARTICLE_COUNT = 5  

def fetch_football_news():
    RSS_URL = "https://www.theguardian.com/football/rss"
    DORK_DOMAINS = [
        "skysports.com", "football.london", "theguardian.com", 
        "kwese.espn.com", "goal.com", "washingtonpost.com", 
        "espn.com", "sempremilan.com", "nytimes.com"
    ]
    
    historical_slugs = set()

    if os.path.exists(JSON_FILE_PATH):
        with open(JSON_FILE_PATH, "r", encoding="utf-8") as f:
            saved_articles = json.load(f)
            for article in saved_articles:
                if article.get("slug"):
                    historical_slugs.add(article["slug"])
                if article.get("source_slug"):
                    historical_slugs.add(article["source_slug"])
        print(f"📂 Loaded historical state cache. Found {len(historical_slugs)} checkpoint tags.")

    print(f"📡 [Step 1] Fetching Guardian Football RSS Feed directly...")
    req = urllib.request.Request(RSS_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15) as response:
        rss_payload = response.read()
        
    root = ET.fromstring(rss_payload)
    headline_pool = []
    rss_articles_registry = {}
    blacklist_terms = {"football", "live scores", "tables", "fixtures", "results", "world cup 2026", "competitions", "clubs", "news", "opinion"}
    
    for item in root.findall('.//item'):
        title_node = item.find('title')
        link_node = item.find('link')
        
        title = title_node.text if title_node is not None else ""
        link = link_node.text if link_node is not None else ""
        
        clean_title = title.strip().rstrip('.')
        clean_title = re.sub(r'(?:double|single)\s+quotation\s+mark', '', clean_title, flags=re.IGNORECASE).strip()
        word_count = len(clean_title.split())
        
        if word_count >= 5 and clean_title.lower() not in blacklist_terms:
            if not any(clean_title.lower().startswith(term) for term in blacklist_terms):
                if clean_title not in headline_pool:
                    headline_pool.append(clean_title)
                    rss_articles_registry[clean_title] = {"link": link}

    print(f"✓ Extracted {len(headline_pool)} total headline items from RSS feed.")
    
    for primary_trending_topic in headline_pool:
        predicted_slug = generate_slug(primary_trending_topic)
        
        if predicted_slug in historical_slugs:
            print(f"⏭️ Skipping already processed topic: '{primary_trending_topic}'")
            continue
            
        print(f"\n🎯 [Fresh Target Topic Locked] \"{primary_trending_topic}\"")
        
        # Ingest ground truth content
        guardian_source_url = rss_articles_registry[primary_trending_topic]["link"]
        print(f"📰 Ingesting ground-truth content from Guardian original node: {guardian_source_url}")
        guardian_full_content = get_full_article_via_ant(guardian_source_url)
        
        if not guardian_full_content.strip():
            raise RuntimeError(f"DATA INTEGRITY CRASH: Reference article content from original Guardian URL returned completely empty: {guardian_source_url}")
            
        target_reference_text = f"TITLE: {primary_trending_topic}\n\nCONTENT:\n{guardian_full_content}"
        
        context_matrix = []
        processed_api_urls = {guardian_source_url} 
        image_source = None
        topic_start_time = time.time()

        clean_query = re.sub(r'[^\w\s-]', '', primary_trending_topic)
        query_tokens = clean_query.split()
        filtering_stopwords = {'a', 'an', 'the', 'and', 'or', 'but', 'is', 'in', 'on', 'at', 'by', 'to', 'for', 'of', 'football', 'guardian', 'live', 'blog', 'news', 'vs', 'report'}
        active_search_terms = [t for t in query_tokens if t.lower() not in filtering_stopwords and len(t) > 3]
        final_query_string = " ".join(active_search_terms[:3])
        
        if not final_query_string:
            final_query_string = "Super Eagles"

        # --- PHASE 1: TRUE GOOGLE DORK VIA SCRAPINGANT ---
        print(f"🔍 [Phase 1: Whitelist Dorking] Directing programmatic site constraints to Google Search...")
        domain_or_chain = " OR ".join([f"site:{d}" for d in DORK_DOMAINS])
        dork_query = f"({domain_or_chain}) \"{final_query_string}\""
        
        phase1_urls = execute_google_search_via_ant(dork_query)
        print(f"     ✓ Google isolated {len(phase1_urls)} matching domain links to evaluate.")

        for record_url in phase1_urls:
            if time.time() - topic_start_time > TIMEOUT_LIMIT or len(context_matrix) >= TARGET_ARTICLE_COUNT:
                break
                
            if record_url in processed_api_urls:
                continue
                
            processed_api_urls.add(record_url)
            full_markdown_content = get_full_article_via_ant(record_url)
            
            if not full_markdown_content.strip():
                continue

            if not image_source:
                img_match = re.search(r'!\[.*?\]\((https?://[^\)]+\.(?:jpg|jpeg|png|webp)[^\)]*)\)', full_markdown_content, re.IGNORECASE)
                if img_match:
                    image_source = img_match.group(1)
                    print(f"     🖼️ Scraped context image asset: {image_source}")
            
            candidate_packet = f"TITLE: {primary_trending_topic}\n\nCONTENT:\n{full_markdown_content}"
            is_valid_match, match_score = verify_topic_match(target_reference_text, candidate_packet)
            
            if not is_valid_match:
                continue
            
            source_domain = urllib.parse.urlparse(record_url).netloc.replace("www.", "")
            context_matrix.append({
                "source": source_domain,
                "title": primary_trending_topic,
                "description": full_markdown_content[:140].strip() + "...",
                "content": full_markdown_content
            })
            print(f"     ✓ Pool Progress: {len(context_matrix)}/{TARGET_ARTICLE_COUNT} Verified.")
            time.sleep(1.0)

        # --- PHASE 2: NORMAL OPEN GOOGLE SEARCH FALLBACK ---
        elapsed_time = time.time() - topic_start_time
        if len(context_matrix) < TARGET_ARTICLE_COUNT and elapsed_time <= TIMEOUT_LIMIT:
            print(f"\n⚠️ Target unfulfilled. Engaging broad open web crawl fallback via Google...")
            
            for fallback_term in active_search_terms[:2]:
                if len(context_matrix) >= TARGET_ARTICLE_COUNT or (time.time() - topic_start_time) > TIMEOUT_LIMIT:
                    break
                    
                print(f"🔍 [Phase 2: Fallback] Querying: {fallback_term}")
                phase2_urls = execute_google_search_via_ant(fallback_term)
                
                for record_url in phase2_urls:
                    if time.time() - topic_start_time > TIMEOUT_LIMIT or len(context_matrix) >= TARGET_ARTICLE_COUNT:
                        break
                        
                    if record_url in processed_api_urls:
                        continue
                        
                    processed_api_urls.add(record_url)
                    full_markdown_content = get_full_article_via_ant(record_url)
                    
                    if not full_markdown_content.strip():
                        continue

                    if not image_source:
                        img_match = re.search(r'!\[.*?\]\((https?://[^\)]+\.(?:jpg|jpeg|png|webp)[^\)]*)\)', full_markdown_content, re.IGNORECASE)
                        if img_match:
                            image_source = img_match.group(1)
                    
                    candidate_packet = f"TITLE: {primary_trending_topic}\n\nCONTENT:\n{full_markdown_content}"
                    is_valid_match, match_score = verify_topic_match(target_reference_text, candidate_packet)
                    
                    if not is_valid_match:
                        continue
                    
                    source_domain = urllib.parse.urlparse(record_url).netloc.replace("www.", "")
                    context_matrix.append({
                        "source": source_domain,
                        "title": primary_trending_topic,
                        "description": full_markdown_content[:140].strip() + "...",
                        "content": full_markdown_content
                    })
                    print(f"     ✓ Pool Progress: {len(context_matrix)}/{TARGET_ARTICLE_COUNT} Verified.")
                    time.sleep(1.0)

        # Enforce rule: Less than 4 semantic matches means drop topic, move to next headline
        if len(context_matrix) < 4:
            print(f"❌ THROW AWAY: Topic secured only {len(context_matrix)} valid semantic matches. Abandoning topic loop to cycle back...")
            continue  
            
        print(f"🎉 SUCCESS: Topic cleared agent audits with {len(context_matrix)} aligned articles.")
        if not image_source:
            image_source = "https://images.unsplash.com/photo-1508098682722-e99c43a406b2"
            
        return {
            "category": "Sports",
            "image_source": image_source, 
            "match_meta": {
                "teams": primary_trending_topic, 
                "score": "N/A",
                "league": "Trending International Football",
                "elapsed_time": "Real-Time Processing Engine"
            },
            "raw_team_statistics": context_matrix
        }

    raise RuntimeError("PIPELINE CRASH: Entire headline RSS pool exhausted without tracking down a topic clearing the minimum semantic match constraint (4+ articles).")


# --- STAGE 3: CLOUDINARY UPLOAD ---
def upload_to_cloudinary(url_source, seed_name):
    if not url_source:
        raise ValueError("CLOUDINARY CRASH: Source asset image URL parameter is empty.")

    url_source = url_source.strip().replace(" ", "%20")
    if url_source.startswith("//"):
        url_source = "https:" + url_source
        
    clean_id = "".join(c for c in seed_name if c.isalnum() or c in (" ", "_", "-")).strip()[:40]
    public_id = f"api_data_{int(datetime.now().timestamp())}_{clean_id.replace(' ', '_')}"
    temp_image_path = f"/tmp/{public_id}.jpg"
    
    req = urllib.request.Request(url_source, headers={'User-Agent': 'Mozilla/5.0'})
    
    with urllib.request.urlopen(req, timeout=15) as response, open(temp_image_path, 'wb') as out_file:
        out_file.write(response.read())
    
    upload_response = cloudinary.uploader.upload(
        temp_image_path,
        public_id=public_id,
        folder="discover_images",
        transformation=[{"width": 1200, "crop": "fill", "gravity": "auto", "fetch_format": "auto", "quality": "auto"}]
    )
    
    if os.path.exists(temp_image_path):
        os.remove(temp_image_path)
        
    secure_url = upload_response.get("secure_url")
    if not secure_url:
        raise RuntimeError("CLOUDINARY CRASH: Cloudinary API upload succeeded but returned an invalid secure asset URL payload.")
        
    print(f"🖼️ Cloudinary Upload Success: {secure_url}")
    return secure_url


# --- STAGE 4: AI GENERATION & DUAL-AGENT LOOP ---
def generate_ai_article(data_package):
    print(f"⚽ Initializing Dual-Agent Orchestration Engine...")
    client = Mistral(api_key=SPORTS_API_KEY)
    meta = data_package["match_meta"]
    stats_string = json.dumps(data_package["raw_team_statistics"], indent=2)
    
    prompt_content = f"""Review the multi-source context below and synthesize an original, authoritative sports report.\n[NEWS CONTEXT]\nSubject: {meta['teams']}\nArticles Data: {stats_string}"""
    current_messages = [{"role": "user", "content": prompt_content}]
    
    max_loops = 3
    target_score = 97
    attempt = 0
    best_draft = None
    highest_score = -1

    while attempt < max_loops:
        attempt += 1
        print(f"✍️ Generation Turn {attempt}/{max_loops} via Writer Agent ({SPORTS_AGENT_ID})...")
        
        while True:
            try:
                gen_response = client.agents.complete(agent_id=SPORTS_AGENT_ID, messages=current_messages)
                generated_content = gen_response.choices[0].message.content
                break
            except Exception as e:
                if "429" in str(e) or "capacity" in str(e).lower():
                    print("⚠️ Rate Limit hit on Writer. Waiting 20s...")
                    time.sleep(20)
                else:
                    raise RuntimeError(f"AGENTS CRASH: Fatal connection breakdown on Writer Agent endpoint: {e}")
                    
        if best_draft is None:
            best_draft = generated_content

        print(f"🧐 Transferring payload to Critic Agent ({CRITIC_AGENT_ID}) for evaluation...")
        
        critic_success = False
        for critic_attempt in range(5):
            try:
                critic_response = client.agents.complete(
                    agent_id=CRITIC_AGENT_ID,
                    messages=[{"role": "user", "content": f"Evaluate this draft:\n\n{generated_content}"}]
                )
                
                raw_critic_text = critic_response.choices[0].message.content
                json_match = re.search(r'\{.*\}', raw_critic_text, re.DOTALL)
                if json_match:
                    critic_json = json.loads(json_match.group(0))
                else:
                    critic_json = json.loads(raw_critic_text.strip())
                    
                critic_success = True
                break
            except Exception as e:
                if "429" in str(e) or "capacity" in str(e).lower():
                    cooldown = 25 + (critic_attempt * 10)
                    print(f"⚠️ Rate Limit hit on Critic. Waiting {cooldown}s...")
                    time.sleep(cooldown)
                else:
                    print(f"⚠️ Critic layout anomaly: {e}. Retrying execution...")
                    time.sleep(5)

        if not critic_success:
            raise RuntimeError("AGENTS CRASH: Critic Agent structural execution failed or sustained systemic API timeouts occurred.")

        score = int(critic_json.get("score", 70))
        instructions = critic_json.get("improvement_instructions", "")
        
        print(f"📊 Audit Complete | Current Quality Metric: {score}/100")
        
        if score > highest_score:
            highest_score = score
            best_draft = generated_content

        if score >= target_score:
            print("🎉 Success! Quality threshold cleared. Initializing publishing sequence.")
            return generated_content
            
        if attempt < max_loops:
            print(f"⚠️ Score {score} below target. Routing remediation array back to Writer...")
            current_messages.extend([
                {"role": "assistant", "content": generated_content},
                {"role": "user", "content": f"Your last draft scored {score}/100. Rewrite it immediately to fulfill these commands from the Critic Agent: {instructions}."}
            ])
            time.sleep(10)

    # If loops exhaust without hit score target, we check if it is acceptable or completely failure
    if highest_score < 85:
        raise RuntimeError(f"AGENTS CRASH: Quality loop exhausted. Maximum audit score obtained was only {highest_score}/100, missing target benchmark safety threshold.")
        
    print(f"⚠️ Target target_score not reached, but acceptable threshold cleared ({highest_score}/100). Releasing article payload.")
    return best_draft


# --- STAGE 5: DATA FORMATTING & STORAGE ---
def process_and_save_item(data_package, cloudinary_url):
    ai_output = generate_ai_article(data_package)
    
    paragraphs = re.findall(r'<p>(.*?)</p>', ai_output, re.DOTALL)
    if not paragraphs:
        print("🚨 [Parser Guard] Missing HTML structure. Processing raw token auto-wrap...")
        raw_blocks = [block.strip() for block in ai_output.split("\n\n") if block.strip()]
        if raw_blocks:
            ai_title = raw_blocks[0]
            paragraphs = [f"<p>{b}</p>" for b in raw_blocks]
        else:
            ai_title = data_package["match_meta"]["teams"]
            paragraphs = [f"<p>{ai_output}</p>"]
    else:
        ai_title = re.sub(r'<[^>]+>', '', paragraphs[0]).strip()
        paragraphs = [f"<p>{p.strip()}</p>" for p in paragraphs]

    ai_content_only = "".join(paragraphs[1:]) if len(paragraphs) > 1 else "".join(paragraphs)
    clean_text = re.sub(r'<[^>]*>', '', ai_content_only)
    
    article_payload = {
        "slug": generate_slug(ai_title),
        "source_slug": generate_slug(data_package["match_meta"]["teams"]),  
        "title": ai_title,
        "description": clean_text[:147] + "...",
        "intro": clean_text[:47] + "...",
        "content": ai_content_only,
        "image": cloudinary_url,
        "datePublished": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "category": data_package["category"].lower(),
        "trendingBoost": 3
    }
    
    os.makedirs(os.path.dirname(JSON_FILE_PATH), exist_ok=True)
    existing_data = []
    if os.path.exists(JSON_FILE_PATH):
        with open(JSON_FILE_PATH, "r", encoding="utf-8") as f:
            existing_data = json.load(f)
            
    existing_data.insert(0, article_payload)
    
    with open(JSON_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, indent=2, ensure_ascii=False)
        
    print(f"💾 Successfully saved and prepended article: {article_payload['slug']}")


# --- STAGE 6: MAIN PIPELINE RUNNER ---
def execute_api_crawl():
    print(f"🕒 Pipeline Execution Initiated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    news_data = fetch_football_news()
    if not news_data or not news_data.get("raw_team_statistics"):
        raise ValueError("RUNNER CRASH: Target data matrix returned structure missing raw statistics fields completely.")
        
    cloudinary_url = upload_to_cloudinary(news_data["image_source"], news_data["match_meta"]["teams"])
    process_and_save_item(news_data, cloudinary_url)

if __name__ == "__main__":
    execute_api_crawl()
