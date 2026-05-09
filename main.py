import subprocess
import sys
import os
import urllib.request

# --- STAGE 0: AUTOMATIC INSTALLATION ---
def ensure_dependencies():
    libs = ['feedparser', 'tqdm', 'groq', 'pyTelegramBotAPI', 'PyGithub', 'cloudinary']
    for lib in libs:
        try:
            import_name = 'telebot' if lib == 'pyTelegramBotAPI' else ('github' if lib == 'PyGithub' else lib)
            __import__(import_name)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", lib])

ensure_dependencies()

import telebot
import feedparser
from groq import Groq
from github import Github, Auth
from tqdm import tqdm
import cloudinary
import cloudinary.uploader

# --- STAGE 1: CREDENTIALS ---
TELEGRAM_TOKEN = "8799270771:AAEUDhwhXaHq8cgfr1eIz9TdH9X3B0X604Y"
CHAT_ID = "6108841631"
GROQ_API_KEY = "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"

# Provided by GitHub Action Environment when running in the cloud
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = os.getenv("REPO_NAME")

cloudinary.config(
  cloud_name = "dttmavamx",
  api_key = "336655594631775",
  api_secret = "xydaLJiFP26S_BG_AgBbAmP7U00"
)

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

# Modern GitHub Auth to avoid deprecation warnings in logs
auth = Auth.Token(GITHUB_TOKEN) if GITHUB_TOKEN else None
gh = Github(auth=auth)

# --- STAGE 2: THE HUMAN-PULSE MASTER PROMPT ---
MASTER_PROMPT = """
ROLE:
You are a highly opinionated, passionate hobbyist and seasoned observer. You are NOT a content generator. You are a ghostwriter for a popular blog that people read specifically for its "real talk" and unique perspective. You are writing to a friend who is already interested in the topic but wants the "honest take."

TASK:
The category for this post is {category}.
Write a short, high-substance article based on the following data: {article_data}

RULE 1: NO HALLUCINATIONS (STRICT GROUNDING)
 * You must use the core facts provided in the input.
 * Do NOT invent names, dates, or events that are not present.
 * Atmospheric Exception: You may invent sensory "fluff" to ground the piece in reality (e.g., describing a crowded room, the weather, or a specific feeling), but the news must remain 100% accurate.

RULE 2: THE TITLE (SUMMARY + CURIOSITY)
 * Formula: [Detailed Action/Event] + [Unanswered Question or Opinionated Twist].
 * Forbidden: Clickbait tropes ("You won't believe," "X things about...").
 * Example (Tech): "The new Apple update finally fixes the battery drain, but the privacy trade-off feels like a step backward."

RULE 3: THE "HUMAN DEFECT" STYLE (ANTI-DETECTION)
 * High Perplexity: Do not use predictable word pairings.
 * High Burstiness: Vary sentence length aggressively.
    * Pattern: One long, rambling, parenthetical thought sentence followed by a short, 3-word punch. Like this.
 * Intentional "Flow" Breaks: Start sentences with "And," "But," or "So." Use contractions (don't, it's, shouldn't) every single time.
 * Forbidden Transitions: Never use "In conclusion," "Moreover," "Additionally," "Furthermore," or "Essentially."
 * Forbidden "AI" Vocabulary: Absolutely no use of: Testament, landscape, pivotal, underscores, delves, tapestry, comprehensive, multifaceted, or 'in today's world'.

RULE 4: SENSORY "WITNESS" LAYER
To prove you "were there," include one hyper-specific sensory detail related to the news category:
 * Tech: The annoying fan noise of a laptop or the smudge on a screen.
 * General News: The way people in the background were looking at their phones or the "heavy silence" in the room.
 * Finance/Sports: The chaotic feeling of a green/red ticker or the "coffee-fueled" energy of the report.

INTERNAL MONOLOGUE (Claude 4.7 Extended Thinking):
Before you write, internally list the 3 most "robotic" ways to report this news and then deliberately choose a 4th, more conversational path. Ensure your rhythm doesn't follow a standard 5-sentence paragraph structure.
"""

def originate_content(category, title, summary):
    article_data = f"TITLE: {title} | SUMMARY: {summary}"
    try:
        completion = client.chat.completions.create(
            model="openai/gpt-oss-120b", 
            messages=[{"role": "system", "content": MASTER_PROMPT.format(category=category, article_data=article_data)}],
            temperature=0.85
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"Groq Error: {e}"

def push_to_github(content):
    if not GITHUB_TOKEN or not REPO_NAME:
        raise ValueError("GitHub credentials (GITHUB_TOKEN or REPO_NAME) are missing.")
        
    repo = gh.get_repo(REPO_NAME)
    
    # Extract title for filename and clean it
    first_line = content.split('\n')[0].replace("Title: ", "").replace("#", "").strip()
    filename = "".join(x for x in first_line[:30] if x.isalnum() or x == " ").replace(" ", "-").lower() + ".md"
    path = f"content/posts/{filename}" # Assuming this is your Cloudflare Pages content path
    
    repo.create_file(path, f"Automated Publish: {filename}", content, branch="main")

# --- THE LISTENER ---
@bot.message_handler(func=lambda message: True)
def handle_approval(message):
    """Listens for your replies in Telegram and pushes them to GitHub/Cloudflare."""
    if str(message.chat.id) == CHAT_ID:
        bot.reply_to(message, "🚀 **Ghostwriter output received! Pushing to Cloudflare Pages via GitHub...**")
        try:
            push_to_github(message.text)
            bot.send_message(CHAT_ID, "✅ **Published! Cloudflare is now rebuilding your site.**")
        except Exception as e:
            bot.send_message(CHAT_ID, f"❌ **GitHub Error:** {e}")

def run_crawl():
    """Fetches exactly 2 Sports and 2 Politics articles."""
    print("🚀 Starting News Crawl...")
    
    # Updated to the specific Sky Sports Football feed to match your screenshot
    sources = [
        {"url": "https://www.skysports.com/rss/12040", "cat": "Sports"},
        {"url": "https://rss.punchng.com/feed/", "cat": "Politics"}
    ]
    
    # User-Agent header bypasses anti-bot systems (fixes the 0it issue)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'}

    for source in sources:
        try:
            req = urllib.request.Request(source["url"], headers=headers)
            with urllib.request.urlopen(req) as response:
                content = response.read()
                feed = feedparser.parse(content)
            
            if not feed.entries:
                print(f"⚠️ No entries found for {source['cat']}. Feed might be temporarily down or blocking.")
                continue

            for entry in tqdm(feed.entries[:2], desc=f"Drafting {source['cat']}"):
                rebranded = originate_content(source["cat"], entry.title, entry.summary)
                bot.send_message(CHAT_ID, f"📝 **{source['cat'].upper()} DRAFT**\n\n{rebranded}")
                
        except Exception as e:
            print(f"❌ Failed to fetch {source['cat']}: {e}")
            
    print("✅ Crawl finished. Drafts sent to Telegram.")

if __name__ == "__main__":
    # Always run the crawl on startup (This triggers immediately when GitHub Action runs)
    run_crawl()
    
    # If this is running inside GitHub Actions, it will exit after sending drafts.
    # If you run this locally on your PC or a VPS, it will stay alive to listen for replies.
    if os.getenv("GITHUB_ACTIONS") != "true":
        print("Bot is now entering LISTENER mode. Awaiting your replies in Telegram...")
        bot.infinity_polling()
