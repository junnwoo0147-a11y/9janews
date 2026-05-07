const fs = require('fs');
const path = require('path');

// --- 1. LIVE CONFIGURATION ---
const config = {
  baseUrl: "https://your-domain.com", // ⚠️ REPLACE WITH YOUR ACTUAL URL (No trailing slash)
  siteName: "Taste & Teach: Tactical Analysis",
  authorName: "Ifeanyi Clement Okoye",
  description: "Deep-dive tactical analysis of European football and curated music culture.",
  outputDir: path.join(__dirname, 'public')
};

// --- 2. THE CONTENT DATA ---
// When you add new posts, just add a new object to this array.
const articles = [
  {
    title: "The Osimhen Era: Why Galatasaray’s Leadership Crisis Ends Without a Captain’s Armband",
    slug: "osimhen-galatasaray-leadership",
    date: "2026-05-07T10:00:00Z", 
    category: "Football",
    image: "https://your-domain.com/assets/victor-osimhen-galatasaray.jpg", // Ensure this image is 1200px wide
    description: "Victor Osimhen has introduced a 'Defensive Front-Line' culture at RAMS Park, proving leadership is a frequency, not fabric.",
    content: `
      <p>In the high-pressure cauldron of RAMS Park, the captain’s armband is usually a heavy burden.</p>
      <p>But for Victor Osimhen, leadership isn't a piece of fabric—it's a frequency he operates on every time he steps onto the pitch.</p>
      <p>Osimhen has introduced a 'Defensive Front-Line' culture that didn't exist before. His 94% successful pressing rate is a signal that if the star is running, everyone must run.</p>
      <p>As Galatasaray approaches a historic fourth consecutive Süper Lig title, the narrative has shifted from scoring to psychological leadership.</p>
    `
  }
];

// --- 3. THE ENGINE ---
if (!fs.existsSync(config.outputDir)) fs.mkdirSync(config.outputDir, { recursive: true });

function build() {
  let rssItems = "";
  let sitemapItems = "";
  
  const now = new Date();
  const twoDaysAgo = new Date(now.getTime() - (48 * 60 * 60 * 1000));

  articles.forEach(art => {
    const url = `${config.baseUrl}/${art.slug}.html`;
    const pubDate = new Date(art.date);

    // A. GENERATE THE HTML PAGE
    const html = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="index, follow, max-image-preview:large">
    <meta name="description" content="${art.description}">
    <title>${art.title} | ${config.siteName}</title>
    
    <!-- E-E-A-T Structured Data -->
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "NewsArticle",
      "headline": "${art.title}",
      "image": ["${art.image}"],
      "datePublished": "${art.date}",
      "dateModified": "${art.date}",
      "author": [{
          "@type": "Person",
          "name": "${config.authorName}",
          "url": "${config.baseUrl}"
      }],
      "publisher": {
        "@type": "Organization",
        "name": "${config.siteName}",
        "logo": {
          "@type": "ImageObject",
          "url": "${config.baseUrl}/assets/logo.png"
        }
      }
    }
    </script>
    <style>
        body { font-family: sans-serif; line-height: 1.6; max-width: 800px; margin: 40px auto; padding: 0 20px; color: #333; }
        img { max-width: 100%; height: auto; border-radius: 8px; }
        h1 { line-height: 1.2; }
    </style>
</head>
<body>
    <header>
        <a href="/"><strong>${config.siteName}</strong></a>
    </header>
    <hr>
    <main>
        <article>
            <h1>${art.title}</h1>
            <p><em>By ${config.authorName} • ${pubDate.toDateString()}</em></p>
            <img src="${art.image}" alt="${art.title}">
            <div style="margin-top: 20px;">${art.content}</div>
        </article>
    </main>
    <footer style="margin-top: 50px; font-size: 0.8em; color: #666;">
        <p>© 2026 ${config.siteName}. All tactical rights reserved.</p>
    </footer>
</body>
</html>`;

    fs.writeFileSync(path.join(config.outputDir, `${art.slug}.html`), html);

    // B. ADD TO RSS FEED
    rssItems += `
    <item>
        <title><![CDATA[${art.title}]]></title>
        <link>${url}</link>
        <guid isPermaLink="true">${url}</guid>
        <pubDate>${pubDate.toUTCString()}</pubDate>
        <category>${art.category}</category>
        <description><![CDATA[${art.description}]]></description>
    </item>`;

    // C. ADD TO NEWS SITEMAP (Google News 48h Rule)
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

  // D. WRITE RSS FILE
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

  // E. WRITE NEWS SITEMAP
  const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
    ${sitemapItems}
</urlset>`;
  fs.writeFileSync(path.join(config.outputDir, 'sitemap-news.xml'), sitemap);

  // F. GENERATE HOMEPAGE
  const homepageHtml = `<h1>${config.siteName}</h1><ul>${articles.map(a => `<li><a href="${a.slug}.html">${a.title}</a></li>`).join('')}</ul>`;
  fs.writeFileSync(path.join(config.outputDir, 'index.html'), homepageHtml);

  console.log(`✅ SUCCESS: Generated ${articles.length} pages + RSS + News Sitemap.`);
}

build();
