const fs = require('fs');
const path = require('path');

// --- 1. CONFIGURATION ---
const config = {
  baseUrl: "https://your-domain.com", // CHANGE THIS (no trailing slash)
  siteName: "Football & Music Hub",
  authorName: "Ifeanyi Clement Okoye", // Signals E-E-A-T to Google
  description: "Tactical football analysis and curated music reviews.",
  outputDir: path.join(__dirname, 'public')
};

// --- 2. YOUR DATA ---
// Keep this in a separate JSON file eventually, but here is the structure:
const articles = [
  {
    title: "The Osimhen Era: Why Galatasaray’s Leadership Crisis Ends Without an Armband",
    slug: "osimhen-galatasaray-leadership",
    date: "2026-05-07T10:00:00Z", // Use ISO format
    category: "Football",
    image: "https://your-domain.com/assets/osimhen-action.jpg", // Must be 1200px+ wide
    description: "In the high-pressure cauldron of RAMS Park, Osimhen proves leadership is a frequency, not a piece of fabric.",
    content: `
      <p>In the high-pressure cauldron of RAMS Park, the captain’s armband is usually a heavy burden.</p>
      <p>But for Victor Osimhen, leadership isn't a piece of fabric—it's a frequency he operates on...</p>
    `
  }
];

// --- 3. THE ENGINE ---
if (!fs.existsSync(config.outputDir)) fs.mkdirSync(config.outputDir);

function build() {
  let rssItems = "";
  let sitemapItems = "";
  const now = new Date();
  const twoDaysAgo = new Date(now.getTime() - (48 * 60 * 60 * 1000));

  articles.forEach(art => {
    const url = `${config.baseUrl}/${art.slug}.html`;
    const pubDate = new Date(art.date);

    // A. GENERATE HTML (With Discover & E-E-A-T Metadata)
    const html = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="max-image-preview:large">
    <meta name="description" content="${art.description}">
    <title>${art.title} | ${config.siteName}</title>
    
    <!-- Structured Data for Google News & E-E-A-T -->
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "NewsArticle",
      "headline": "${art.title}",
      "image": ["${art.image}"],
      "datePublished": "${art.date}",
      "author": [{
          "@type": "Person",
          "name": "${config.authorName}",
          "url": "${config.baseUrl}/about"
      }]
    }
    </script>
</head>
<body>
    <header><h1>${config.siteName}</h1></header>
    <main>
        <article>
            <h1>${art.title}</h1>
            <p><em>By ${config.authorName} | ${pubDate.toDateString()}</em></p>
            <img src="${art.image}" alt="${art.title}" style="max-width:100%">
            ${art.content}
        </article>
    </main>
</body>
</html>`;

    fs.writeFileSync(path.join(config.outputDir, `${art.slug}.html`), html);

    // B. PREPARE RSS ITEM
    rssItems += `
    <item>
        <title><![CDATA[${art.title}]]></title>
        <link>${url}</link>
        <guid isPermaLink="true">${url}</guid>
        <pubDate>${pubDate.toUTCString()}</pubDate>
        <description><![CDATA[${art.description}]]></description>
        <category>${art.category}</category>
    </item>`;

    // C. PREPARE NEWS SITEMAP (Only for articles < 48 hours old)
    if (pubDate > twoDaysAgo) {
      sitemapItems += `
    <url>
        <loc>${url}</loc>
        <news:news>
            <news:publication>
                <news:name>${config.siteName}</news:name>
                <news:language>en</news:language>
            </news:publication>
            <news:publication_date>${pubDate.toISOString()}</news:publication_date>
            <news:title>${art.title.replace(/&/g, '&amp;')}</news:title>
        </news:news>
    </url>`;
    }
  });

  // --- 4. WRITE XML FILES ---

  // RSS Feed
  const rssFeed = `<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
    <title>${config.siteName}</title>
    <link>${config.baseUrl}</link>
    <description>${config.description}</description>
    <language>en-us</language>
    <atom:link href="${config.baseUrl}/feed.xml" rel="self" type="application/rss+xml" />
    ${rssItems}
</channel>
</rss>`;
  fs.writeFileSync(path.join(config.outputDir, 'feed.xml'), rssFeed);

  // News Sitemap
  const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
    ${sitemapItems}
</urlset>`;
  fs.writeFileSync(path.join(config.outputDir, 'sitemap-news.xml'), sitemap);

  // Static Index
  fs.writeFileSync(path.join(config.outputDir, 'index.html'), `<h1>${config.siteName}</h1><p>Check the <a href="/feed.xml">RSS</a></p>`);

  console.log(`✅ Build Complete: ${articles.length} pages, RSS, and News Sitemap generated.`);
}

build();
