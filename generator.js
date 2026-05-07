const fs = require('fs');
const path = require('path');

/**
 * SEO & Aggregator Generator
 * Generates: feed.xml, sitemap.xml, sitemap-news.xml
 */
function generateSEOFiles(articles, config) {
    const { baseUrl, siteName, outputDir, description } = config;
    
    let rssItems = "";
    let sitemapItems = "";
    let newsSitemapItems = "";

    const now = new Date();
    const twoDaysAgo = new Date(now.getTime() - (48 * 60 * 60 * 1000));

    // Ensure output directory exists
    if (!fs.existsSync(outputDir)) fs.mkdirSync(outputDir, { recursive: true });

    articles.forEach(art => {
        const fullUrl = `${baseUrl}/${art.slug}.html`;
        const pubDate = new Date(art.date);
        const isoDate = pubDate.toISOString();

        // 1. Build RSS Item (with CDATA for safety)
        rssItems += `
        <item>
            <title><![CDATA[${art.title}]]></title>
            <link>${fullUrl}</link>
            <guid isPermaLink="true">${fullUrl}</guid>
            <pubDate>${pubDate.toUTCString()}</pubDate>
            <category>${art.category}</category>
            <description><![CDATA[${art.description}]]></description>
        </item>`;

        // 2. Build Standard Sitemap Item
        sitemapItems += `
    <url>
        <loc>${fullUrl}</loc>
        <lastmod>${isoDate.split('T')[0]}</lastmod>
    </url>`;

        // 3. Build News Sitemap Item (Strict 48-hour window)
        if (pubDate > twoDaysAgo) {
            newsSitemapItems += `
    <url>
        <loc>${fullUrl}</loc>
        <news:news>
            <news:publication>
                <news:name>${siteName}</news:name>
                <news:language>en</news:language>
            </news:publication>
            <news:publication_date>${isoDate}</news:publication_date>
            <news:title><![CDATA[${art.title}]]></news:title>
        </news:news>
    </url>`;
        }
    });

    // --- XML TEMPLATES ---

    const rssFeed = `<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
    <title>${siteName}</title>
    <link>${baseUrl}</link>
    <description>${description}</description>
    <language>en-us</language>
    <atom:link href="${baseUrl}/feed.xml" rel="self" type="application/rss+xml" />
    ${rssItems}
</channel>
</rss>`;

    const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url><loc>${baseUrl}/</loc><lastmod>${now.toISOString().split('T')[0]}</lastmod></url>
    ${sitemapItems}
</urlset>`;

    const newsSitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
    ${newsSitemapItems}
</urlset>`;

    // Write Files
    try {
        fs.writeFileSync(path.join(outputDir, 'feed.xml'), rssFeed);
        fs.writeFileSync(path.join(outputDir, 'sitemap.xml'), sitemap);
        fs.writeFileSync(path.join(outputDir, 'sitemap-news.xml'), newsSitemap);
        console.log(`✅ SEO Files Generated: feed.xml, sitemap.xml, sitemap-news.xml`);
    } catch (err) {
        console.error(`❌ Error writing SEO files: ${err.message}`);
    }
}

module.exports = generateSEOFiles;
