import os
import re
from datetime import datetime

# --- CONFIGURATION ---
SITE_URL = "https://blog.pluse.name.ng"
# Pointing to your specific folder:
ARTICLES_DIR = "dist/articles"  
# These will be saved in the root so they are accessible at pluse.name.ng/sitemap.xml
OUTPUT_SITEMAP = "sitemap.xml"
OUTPUT_RSS = "feed.xml"

def extract_meta(file_path):
    """Extracts title and description from HTML file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
            # Find <title>
            title_search = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE)
            title = title_search.group(1).replace(" | 9ja News Pluse", "").strip() if title_search else "No Title"
            
            # Find <meta name="description">
            desc_search = re.search(r'<meta name="description" content="(.*?)">', content, re.IGNORECASE)
            description = desc_search.group(1).strip() if desc_search else "No description available."
            
            return title, description
    except Exception as e:
        print(f"⚠️ Error reading {file_path}: {e}")
        return None, None

def generate():
    # Ensure the directory exists
    if not os.path.exists(ARTICLES_DIR):
        print(f"❌ Error: The folder '{ARTICLES_DIR}' was not found!")
        return

    articles = []
    
    # 1. Scan dist/articles for HTML files
    for filename in os.listdir(ARTICLES_DIR):
        if filename.endswith(".html"):
            path = os.path.join(ARTICLES_DIR, filename)
            title, desc = extract_meta(path)
            
            if title:
                # Use file modification time for dates
                mod_time = os.path.getmtime(path)
                date_iso = datetime.fromtimestamp(mod_time).strftime('%Y-%m-%d')
                date_rss = datetime.fromtimestamp(mod_time).strftime('%a, %d %b %Y %H:%M:%S +0000')
                
                articles.append({
                    # This constructs the URL as https://blog.pluse.name.ng/articles/filename.html
                    'url': f"{SITE_URL}/articles/{filename}",
                    'title': title,
                    'desc': desc,
                    'date_iso': date_iso,
                    'date_rss': date_rss
                })

    # Sort articles by date (newest first)
    articles.sort(key=lambda x: x['date_iso'], reverse=True)

    # 2. Generate Sitemap
    with open(OUTPUT_SITEMAP, "w", encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for a in articles:
            f.write(f'  <url>\n    <loc>{a["url"]}</loc>\n    <lastmod>{a["date_iso"]}</lastmod>\n  </url>\n')
        f.write('</urlset>')

    # 3. Generate RSS Feed
    rss_header = f'''<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
  <title>9ja News Pluse</title>
  <link>{SITE_URL}</link>
  <description>Latest news updates from 9ja News Pluse</description>
  <language>en-ng</language>\n'''
    
    with open(OUTPUT_RSS, "w", encoding='utf-8') as f:
        f.write(rss_header)
        for a in articles:
            f.write(f'''  <item>
    <title>{a["title"]}</title>
    <link>{a["url"]}</link>
    <description>{a["desc"]}</description>
    <pubDate>{a["date_rss"]}</pubDate>
  </item>\n''')
        f.write('\n</channel>\n</rss>')

    print(f"✅ Done! Found {len(articles)} articles in {ARTICLES_DIR}.")
    print(f"📄 Generated {OUTPUT_SITEMAP} and {OUTPUT_RSS}")

if __name__ == "__main__":
    generate()
