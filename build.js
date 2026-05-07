const fs = require('fs');
const path = require('path');

// --- CONFIGURATION ---
const SITE_URL = "https://your-domain.com"; // CHANGE THIS to your real URL
const SITE_NAME = "Football & Music Hub";
const OUTPUT_DIR = path.join(__dirname, 'public');

// --- YOUR DATA ---
// Add your articles here. Every time you add one and push, traffic flows.
const articles = [
    {
        title: "Tactical Analysis: The Future of the Number 10",
        slug: "football-tactics-future",
        date: new Date().toISOString(),
        category: "Football",
        description: "A deep dive into how modern tactics are evolving.",
        content: "<h1>Tactics</h1><p>Modern football is changing fast...</p>"
    }
];

// --- THE ENGINE ---
if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR);

function build() {
    let rssItems = "";
    let sitemapItems = "";
    let newsSitemapItems = "";

    articles.forEach(art => {
        const fullUrl = `${SITE_URL}/${art.slug}.html`;
        const isoDate = new Date(art.date).toISOString();

        // Create HTML Page (Kept exactly as yours)
        const html = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${art.title} | ${SITE_NAME}</title>
    <link rel="alternate" type="application/rss+xml" title="RSS" href="/feed.xml" />
</head>
<body>
    <nav><a href="/">Home</a></nav>
    <article>
        <h1>${art.title}</h1>
        <p><em>Category: ${art.category} | Published: ${new Date(art.date).toDateString()}</em></p>
        ${art.content}
    </article>
    <footer>
        <p>© 2026 ${SITE_NAME}</p>
        <p><a href="https://www.newsnow.co.uk/" target="_blank">Featured on NewsNow</a></p>
    </footer>
</body>
</html>`;

        fs.writeFileSync(path.join(OUTPUT_DIR, `${art.slug}.html`), html);

        // Create RSS Entry (Kept exactly as yours)
        rssItems += `
        <item>
            <title>${art.title}</title>
            <link>${fullUrl}</link>
            <guid isPermaLink="true">${fullUrl}</guid>
            <pubDate>${new Date(art.date).toUTCString()}</pubDate>
            <category>${art.category}</category>
            <description>${art.description}</description>
        </item>`;

        // Create Standard Sitemap Entry
        sitemapItems += `
    <url>
        <loc>${fullUrl}</loc>
        <lastmod>${isoDate.split('T')[0]}</lastmod>
    </url>`;

        // Create Google News Sitemap Entry
        newsSitemapItems += `
    <url>
        <loc>${fullUrl}</loc>
        <news:news>
            <news:publication>
                <news:name>${SITE_NAME}</news:name>
                <news:language>en</news:language>
            </news:publication>
            <news:publication_date>${isoDate}</news:publication_date>
            <news:title>${art.title}</news:title>
        </news:news>
    </url>`;
    });

    // Create Final RSS File
    const rssFeed = `<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
    <title>${SITE_NAME}</title>
    <link>${SITE_URL}</link>
    <description>Expert football analysis and music reviews.</description>
    <language>en-us</language>
    <atom:link href="${SITE_URL}/feed.xml" rel="self" type="application/rss+xml" />
    ${rssItems}
</channel>
</rss>`;

    // Create Final Standard Sitemap File
    const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>${SITE_URL}/</loc>
        <lastmod>${new Date().toISOString().split('T')[0]}</lastmod>
    </url>
    ${sitemapItems}
</urlset>`;

    // Create Final News Sitemap File (Crucial for Google Discover)
    const newsSitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
    ${newsSitemapItems}
</urlset>`;

    fs.writeFileSync(path.join(OUTPUT_DIR, 'feed.xml'), rssFeed);
    fs.writeFileSync(path.join(OUTPUT_DIR, 'sitemap.xml'), sitemap);
    fs.writeFileSync(path.join(OUTPUT_DIR, 'sitemap-news.xml'), newsSitemap);
    
    // Create a simple homepage so the site isn't empty
    fs.writeFileSync(path.join(OUTPUT_DIR, 'index.html'), `<h1>${SITE_NAME}</h1><p>Check our <a href="/feed.xml">RSS Feed</a></p>`);

    console.log("🚀 Build complete: HTML, RSS, Standard Sitemap, and News Sitemap generated.");
}

build();
