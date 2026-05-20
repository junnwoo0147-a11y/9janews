import os
import json
from datetime import datetime, timezone

# --- CONFIGURATION ---
SITE_URL = "https://blog.pluse.name.ng"
ARTICLES_JSON = "data/articles.json"
OUTPUT_SITEMAP = "sitemap.xml"
OUTPUT_RSS = "feed.xml"

def generate():
    # Check if JSON file exists
    if not os.path.exists(ARTICLES_JSON):
        print(f"❌ Error: The file '{ARTICLES_JSON}' was not found!")
        return

    try:
        with open(ARTICLES_JSON, 'r', encoding='utf-8') as f:
            articles = json.load(f)
    except Exception as e:
        print(f"❌ Error reading {ARTICLES_JSON}: {e}")
        return

    if not articles:
        print(f"⚠️ Warning: No articles found in {ARTICLES_JSON}")
        return

    # Sort by date (newest first)
    articles.sort(
        key=lambda x: datetime.fromisoformat(x.get('datePublished', '2000-01-01')).replace(tzinfo=None), 
        reverse=True
    )

    # 2. Generate Sitemap
    with open(OUTPUT_SITEMAP, "w", encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for article in articles:
            slug = article.get('slug', '').strip()
            if slug:
                url = f"{SITE_URL}/articles/{slug}"
                date_published = article.get('datePublished', '').split('T')[0]
                f.write(f'  <url>\n    <loc>{url}</loc>\n    <lastmod>{date_published}</lastmod>\n  </url>\n')
        f.write('</urlset>')

    # 3. Generate RSS Feed
    rss_header = f'''<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
  <title>9ja News Pluse</title>
  <link>{SITE_URL}</link>
  <description>Latest news updates from 9ja News Pluse</description>
  <language>en-ng</language>
'''
    
    with open(OUTPUT_RSS, "w", encoding='utf-8') as f:
        f.write(rss_header)
        for article in articles:
            slug = article.get('slug', '').strip()
            title = article.get('title', 'No Title')
            description = article.get('description', article.get('intro', 'No description available.'))
            date_published = article.get('datePublished', '')
            
            if slug:
                url = f"{SITE_URL}/articles/{slug}"
                # Convert ISO date to RFC 2822 format for RSS
                try:
                    dt = datetime.fromisoformat(date_published).replace(tzinfo=None)
                    date_rss = dt.strftime('%a, %d %b %Y %H:%M:%S +0000')
                except:
                    date_rss = datetime.now(timezone.utc).replace(tzinfo=None).strftime('%a, %d %b %Y %H:%M:%S +0000')
                
                f.write(f'''  <item>
    <title>{title}</title>
    <link>{url}</link>
    <description>{description}</description>
    <pubDate>{date_rss}</pubDate>
  </item>
''')
        f.write('\n</channel>\n</rss>')

    print(f"✅ Done! Found {len(articles)} articles in {ARTICLES_JSON}.")
    print(f"📄 Generated {OUTPUT_SITEMAP} and {OUTPUT_RSS}")

if __name__ == "__main__":
    generate()
