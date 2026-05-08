const fs = require("fs");
const path = require("path");

const config = require("./site-config.js");
const articles = JSON.parse(fs.readFileSync("./data/articles.json", "utf-8"));
const pagesData = JSON.parse(fs.readFileSync("./data/pages-data.json", "utf-8"));

const homeTemplate = fs.readFileSync("./templates/index-template.html", "utf-8");
const articleTemplate = fs.readFileSync("./templates/article-template.html", "utf-8");

const aboutTemplate = fs.readFileSync("./about/about.html", "utf-8");
const privacyTemplate = fs.readFileSync("./privacy-policy/privacy.html", "utf-8");
const authorTemplate = fs.readFileSync("./authors/ifeanyi-okoye.html", "utf-8");

const distDir = "./dist";
const articleOut = path.join(distDir, "articles");

if (!fs.existsSync(articleOut)) fs.mkdirSync(articleOut, { recursive: true });

/* =========================================================
   HELPERS
========================================================= */

const formatSections = (sections) => 
  (sections || []).map(s => `<h3>${s.heading || s.title}</h3><p>${s.text || s.body}</p>`).join("");

function scoreArticle(article) {
  let score = 0;
  const daysOld = (Date.now() - new Date(article.datePublished)) / (1000 * 60 * 60 * 24);
  score += Math.max(0, 10 - daysOld);
  if (article.image) score += 3;
  if (article.trendingBoost) score += article.trendingBoost;
  return score;
}

/**
 * FIXED: Related Articles by Category
 * 1. Filters out the current article (preventing self-duplication).
 * 2. Prioritizes articles in the same category.
 */
function getRelatedArticles(current, all) {
  return all
    .filter(a => a.slug !== current.slug) // REMOVE DUPLICATE: Don't show current article in related
    .map(a => {
      let relScore = 0;
      if (a.category === current.category) relScore += 10; // High priority for same category
      return { ...a, relScore };
    })
    .sort((a, b) => b.relScore - a.relScore || new Date(b.datePublished) - new Date(a.datePublished))
    .slice(0, 4) // Limit to 4 related items
    .map(r => `
      <div class="related-item">
        <a href="${r.slug}.html">
            <img src="${r.image || ""}" alt="${r.title}">
            <div>${r.title}</div>
        </a>
      </div>
    `).join("");
}

/* =========================================================
   PREPARE ARTICLES
========================================================= */
const ranked = articles
  .map(article => ({ ...article, score: scoreArticle(article) }))
  .sort((a, b) => b.score - a.score);

/* =========================================================
   BUILD ARTICLE PAGES
========================================================= */
ranked.forEach(article => {
  const canonical = `https://blog.pluse.name.ng/articles/${article.slug}.html`;
  const relatedHTML = getRelatedArticles(article, ranked);

  const html = articleTemplate
    .replace(/__TITLE__/g, article.title)
    .replace(/__DESCRIPTION__/g, article.description)
    .replace(/__IMAGE_URL__/g, article.image)
    .replace(/__CONTENT__/g, article.content)
    .replace(/__INTRO_PARAGRAPH__/g, article.intro)
    .replace(/__DATE_PUBLISHED__/g, article.datePublished)
    .replace(/__DATE_MODIFIED__/g, article.dateModified || article.datePublished)
    .replace(/__DISPLAY_DATE__/g, new Date(article.datePublished).toDateString())
    .replace(/__CANONICAL_URL__/g, canonical)
    .replace(/__RELATED_ARTICLES_DYNAMIC__/g, relatedHTML); // Matches your template placeholder

  fs.writeFileSync(path.join(articleOut, `${article.slug}.html`), html);
});

/* =========================================================
   BUILD HOMEPAGE (STOP DUPLICATES)
========================================================= */
const latest = ranked[0];
// REMOVE DUPLICATE: Grid starts from the second article (index 1)
const gridArticles = ranked.slice(1); 

const grid = gridArticles.map(article => `
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
  .replace(/__TITLE__/g, pagesData.pages.about.title)
  .replace(/__DESCRIPTION__/g, pagesData.pages.about.description)
  .replace(/__CANONICAL_URL__/g, pagesData.pages.about.canonical)
  .replace(/__CONTENT__/g, formatSections(pagesData.pages.about.content_sections));

fs.writeFileSync(path.join(distDir, "about.html"), finalAbout);

// 2. Build Privacy Page
const finalPrivacy = privacyTemplate
  .replace(/__TITLE__/g, pagesData.pages.privacy.title)
  .replace(/__DESCRIPTION__/g, pagesData.pages.privacy.description)
  .replace(/__CANONICAL_URL__/g, pagesData.pages.privacy.canonical)
  .replace(/__DATE_MODIFIED__/g, pagesData.pages.privacy.dateModified || new Date().toDateString())
  .replace(/__CONTENT__/g, formatSections(pagesData.pages.privacy.sections));

fs.writeFileSync(path.join(distDir, "privacy.html"), finalPrivacy);

// 3. Build Author Page
const authorData = pagesData.pages.authors.find(a => a.slug === "ifeanyi-okoye");

if (authorData) {
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
    .replace(/__AUTHOR_NAME__/g, authorData.name)
    .replace(/__AUTHOR_BIO__/g, authorData.bio)
    .replace(/__AUTHOR_IMAGE__/g, authorData.image)
    .replace(/___ORCID_URL__/g, authorData.social_url)
    .replace(/__ARTICLE_COUNT__/g, ranked.length)
    .replace(/__LATEST_POSTS_DYNAMIC__/g, authorArticles)
    .replace(/__CANONICAL_URL__/g, authorData.seo.canonical);

  fs.writeFileSync(path.join(distDir, "ifeanyi-okoye.html"), finalAuthor);
}

/* =========================================================
   FEED & SITEMAP GENERATION
========================================================= */
const rssItems = ranked.map(article => `
<item>
  <title><![CDATA[${article.title}]]></title>
  <link>${config.baseUrl}/articles/${article.slug}.html</link>
  <guid>${config.baseUrl}/articles/${article.slug}.html</guid>
  <pubDate>${new Date(article.datePublished).toUTCString()}</pubDate>
  <description><![CDATA[${article.description || article.title}]]></description>
</item>`).join("");

const rssFeed = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>${config.siteName}</title>
<link>${config.baseUrl}</link>
<description>Latest news from ${config.siteName}</description>
${rssItems}
</channel>
</rss>`;

fs.writeFileSync(path.join(distDir, "feed.xml"), rssFeed);

const sitemapUrls = ranked.map(article => `
<url>
  <loc>${config.baseUrl}/articles/${article.slug}.html</loc>
  <lastmod>${new Date(article.datePublished).toISOString()}</lastmod>
</url>`).join("");

const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>${config.baseUrl}</loc></url>
${sitemapUrls}
</urlset>`;

fs.writeFileSync(path.join(distDir, "sitemap.xml"), sitemap);

/* =========================================================
   COPY ASSETS & ROBOTS
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

const robots = `User-agent: *\nAllow: /\n\nSitemap: ${config.baseUrl}/sitemap.xml`;
fs.writeFileSync(path.join(distDir, "robots.txt"), robots);

console.log("✅ BUILD COMPLETE — SITE GENERATED IN /dist");
