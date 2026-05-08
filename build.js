const fs = require("fs");
const path = require("path");

const config = require("./site-config.js");
const articles = JSON.parse(
  fs.readFileSync("./data/articles.json", "utf-8")
);

// NEW: Load the pages data
const pagesData = JSON.parse(
  fs.readFileSync("./data/pages.json", "utf-8")
);

const homeTemplate = fs.readFileSync(
  "./templates/index-template.html",
  "utf-8"
);

const articleTemplate = fs.readFileSync(
  "./templates/article-template.html",
  "utf-8"
);

// NEW: Load the specific templates you requested
const aboutTemplate = fs.readFileSync("./about/about.html", "utf-8");
const privacyTemplate = fs.readFileSync("./privacy-policy/privacy.html", "utf-8");
const authorTemplate = fs.readFileSync("./authors/ifeanyi-okoye.html", "utf-8");

const distDir = "./dist";
const articleOut = path.join(distDir, "articles");

/* =========================================================
   PREPARE DIRECTORIES
========================================================= */
fs.mkdirSync(articleOut, { recursive: true });

/* =========================================================
   DISCOVER-LIKE SCORING SYSTEM
========================================================= */
function scoreArticle(article) {
  let score = 0;
  const daysOld = (Date.now() - new Date(article.datePublished)) / (1000 * 60 * 60 * 24);
  score += Math.max(0, 10 - daysOld);
  if (article.image) score += 3;
  if (article.description && article.description.length > 50) score += 2;
  if (article.content && article.content.length > 500) score += 3;
  return score;
}

/* =========================================================
   PREPARE ARTICLES
========================================================= */
const ranked = articles
  .map(article => ({
    ...article,
    score: scoreArticle(article)
  }))
  .sort((a, b) => b.score - a.score);

/* =========================================================
   SMART RELATED ARTICLES
========================================================= */
function getRelated(article, all) {
  const normalize = str => (str || "").toLowerCase().replace(/[^a-z0-9 ]/g, "").split(" ").filter(Boolean);
  const articleWords = new Set([...normalize(article.title), ...(article.category ? normalize(article.category) : [])]);

  return all
    .filter(a => a.slug !== article.slug)
    .map(a => {
      const words = [...normalize(a.title), ...(a.category ? normalize(a.category) : [])];
      let score = 0;
      words.forEach(w => { if (articleWords.has(w)) score++; });
      if (a.category && article.category && a.category === article.category) score += 5;
      return { ...a, score };
    })
    .sort((a, b) => b.score - a.score);
}

/* =========================================================
   BUILD ARTICLE PAGES
========================================================= */
ranked.forEach(article => {
  const canonical = `${config.baseUrl}/articles/${article.slug}.html`;
  const related = getRelated(article, ranked);
  const relatedHTML = related.slice(0, 10).map(r => `
      <a class="related-item" href="articles/${r.slug}.html">
        <img src="${r.image || ""}" alt="${r.title}">
        <h4>${r.title}</h4>
      </a>
    `).join("");

  const html = articleTemplate
    .replace(/__TITLE__/g, article.title || "")
    .replace(/__DESCRIPTION__/g, article.description || "")
    .replace(/__IMAGE_URL__/g, article.image || "/assets/default.jpg")
    .replace(/__CONTENT__/g, article.content || "")
    .replace(/__INTRO_PARAGRAPH__/g, article.intro || "")
    .replace(/__DATE_PUBLISHED__/g, article.datePublished || "")
    .replace(/__DATE_MODIFIED__/g, article.dateModified || article.datePublished || "")
    .replace(/__DISPLAY_DATE__/g, new Date(article.datePublished).toDateString())
    .replace(/__CANONICAL_URL__/g, canonical)
    .replace(/__RELATED_ARTICLES__/g, relatedHTML);

  fs.writeFileSync(path.join(articleOut, `${article.slug}.html`), html);
});

/* =========================================================
   BUILD HOMEPAGE
========================================================= */
const latest = ranked[0];
const rest = ranked.slice(1);
const grid = rest.map(article => `
<div class="grid-item">
  <a href="articles/${article.slug}.html">
    <img src="${article.image}" alt="${article.title}" loading="lazy">
    <h3>${article.title}</h3>
    <p>${article.description}</p>
  </a>
</div>
`).join("");

const homepage = homeTemplate
  .replace(/{{LATEST_URL}}/g, `articles/${latest.slug}.html`)
  .replace(/{{LATEST_IMAGE}}/g, latest.image)
  .replace(/{{LATEST_TITLE}}/g, latest.title)
  .replace(/{{LATEST_DESCRIPTION}}/g, latest.description)
  .replace(/{{ALL_ARTICLES_GRID}}/g, grid);

fs.writeFileSync(path.join(distDir, "index.html"), homepage);

/* =========================================================
   STATIC PAGES → INJECT DATA & BUILD
========================================================= */

// 1. Build About Page
const finalAbout = aboutTemplate
  .replace(/__TITLE__/g, pagesData.about.title)
  .replace(/__DESCRIPTION__/g, pagesData.about.description)
  .replace(/__CANONICAL_URL__/g, `${config.baseUrl}/about.html`)
  .replace(/__CONTENT__/g, pagesData.about.content);

fs.writeFileSync(path.join(distDir, "about.html"), finalAbout);

// 2. Build Privacy Page
const finalPrivacy = privacyTemplate
  .replace(/__TITLE__/g, pagesData.privacy.title)
  .replace(/__DESCRIPTION__/g, pagesData.privacy.description)
  .replace(/__CANONICAL_URL__/g, `${config.baseUrl}/privacy-policy.html`)
  .replace(/__DATE_MODIFIED__/g, pagesData.privacy.dateModified)
  .replace(/__CONTENT__/g, pagesData.privacy.content);

fs.writeFileSync(path.join(distDir, "privacy-policy.html"), finalPrivacy);

// 3. Build Author Page (Dynamic Feed for Ifeanyi)
const authorArticles = ranked.map(post => `
    <a href="articles/${post.slug}.html" class="post-card">
        <img src="${post.image}" class="post-thumb" alt="${post.title}">
        <div class="post-info">
            <h2>${post.title}</h2>
            <span class="post-meta">${new Date(post.datePublished).toDateString()}</span>
        </div>
    </a>
`).join("");

const finalAuthor = authorTemplate
  .replace(/__AUTHOR_NAME__/g, pagesData.author.name)
  .replace(/__AUTHOR_BIO__/g, pagesData.author.bio)
  .replace(/__AUTHOR_IMAGE__/g, pagesData.author.image)
  .replace(/__TWITTER_URL__/g, pagesData.author.twitter)
  .replace(/__INSTAGRAM_URL__/g, pagesData.author.instagram)
  .replace(/__ARTICLE_COUNT__/g, ranked.length) // Uses total ranked count
  .replace(/__LATEST_POSTS_DYNAMIC__/g, authorArticles)
  .replace(/__CANONICAL_URL__/g, `${config.baseUrl}/authors/ifeanyi-okoye.html`);

fs.writeFileSync(path.join(distDir, "author-ifeanyi.html"), finalAuthor);


/* =========================================================
   GENERATE RSS FEED
========================================================= */
const rssItems = ranked.map(article => `
<item>
  <title><![CDATA[${article.title}]]></title>
  <link>${config.baseUrl}/articles/${article.slug}.html</link>
  <guid>${config.baseUrl}/articles/${article.slug}.html</guid>
  <pubDate>${new Date(article.datePublished).toUTCString()}</pubDate>
  <description><![CDATA[${article.description || article.title}]]></description>
</item>
`).join("");

const rssFeed = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>${config.siteName}</title>
<link>${config.baseUrl}</link>
<description>Latest news from ${config.siteName}</description>
<language>en-us</language>
${rssItems}
</channel>
</rss>`;

fs.writeFileSync(path.join(distDir, "feed.xml"), rssFeed);

/* =========================================================
   GENERATE SITEMAP
========================================================= */
const sitemapUrls = ranked.map(article => `
<url>
  <loc>${config.baseUrl}/articles/${article.slug}.html</loc>
  <lastmod>${new Date(article.datePublished).toISOString()}</lastmod>
</url>
`).join("");

const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url>
  <loc>${config.baseUrl}</loc>
</url>
${sitemapUrls}
</urlset>`;

fs.writeFileSync(path.join(distDir, "sitemap.xml"), sitemap);

/* =========================================================
   COPY ASSETS
========================================================= */
function copyFolder(src, dest) {
  if (!fs.existsSync(src)) return;
  fs.mkdirSync(dest, { recursive: true });
  fs.readdirSync(src, { withFileTypes: true }).forEach(entry => {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    if (entry.isDirectory()) { copyFolder(srcPath, destPath); } 
    else { fs.copyFileSync(srcPath, destPath); }
  });
}
copyFolder("./assets", path.join(distDir, "assets"));

/* =========================================================
   ROBOTS.TXT
========================================================= */
const robots = `User-agent: *\nAllow: /\n\nSitemap: ${config.baseUrl}/sitemap.xml`;
fs.writeFileSync(path.join(distDir, "robots.txt"), robots);

console.log("✅ BUILD COMPLETE — SITE GENERATED IN /dist");
