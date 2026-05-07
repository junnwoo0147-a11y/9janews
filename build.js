const fs = require("fs");
const path = require("path");

const config = require("./site-config.js");
const articles = JSON.parse(
  fs.readFileSync("./data/articles.json", "utf-8")
);

const homeTemplate = fs.readFileSync(
  "./templates/index-template.html",
  "utf-8"
);

const articleTemplate = fs.readFileSync(
  "./templates/article-template.html",
  "utf-8"
);

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

  const daysOld =
    (Date.now() - new Date(article.datePublished)) /
    (1000 * 60 * 60 * 24);

  score += Math.max(0, 10 - daysOld);

  if (article.image) score += 3;

  if (article.description && article.description.length > 50) {
    score += 2;
  }

  if (article.content && article.content.length > 500) {
    score += 3;
  }

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
   RELATED ARTICLES
========================================================= */
function getRelated(article, all) {
  return all
    .filter(a => a.slug !== article.slug)
    .slice(0, 2);
}

/* =========================================================
   SMART RELATED ARTICLES (CATEGORY + TITLE BASED)
========================================================= */
function getRelated(article, all) {
  const normalize = str =>
    (str || "")
      .toLowerCase()
      .replace(/[^a-z0-9 ]/g, "")
      .split(" ")
      .filter(Boolean);

  const articleWords = new Set([
    ...normalize(article.title),
    ...(article.category ? normalize(article.category) : [])
  ]);

  return all
    .filter(a => a.slug !== article.slug)
    .map(a => {
      const words = [
        ...normalize(a.title),
        ...(a.category ? normalize(a.category) : [])
      ];

      let score = 0;

      words.forEach(w => {
        if (articleWords.has(w)) score++;
      });

      if (
        a.category &&
        article.category &&
        a.category === article.category
      ) {
        score += 5;
      }

      return { ...a, score };
    })
    .sort((a, b) => b.score - a.score);
}

/* =========================================================
   BUILD ARTICLE PAGES
========================================================= */
ranked.forEach(article => {
  const canonical =
    `${config.baseUrl}/articles/${article.slug}.html`;

  const related = getRelated(article, ranked);

  const relatedHTML = related
    .slice(0, 10) // show up to 10 related articles (adjust if you want more)
    .map(r => `
      <a class="related-item" href="articles/${r.slug}.html">
        <img src="${r.image || ""}" alt="${r.title}">
        <h4>${r.title}</h4>
      </a>
    `)
    .join("");

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

  fs.writeFileSync(
    path.join(articleOut, `${article.slug}.html`),
    html
  );
});;

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

/* =========================================================
   WRITE HOMEPAGE
========================================================= */
fs.writeFileSync(
  path.join(distDir, "index.html"),
  homepage
);

/* =========================================================
   STATIC PAGES → BUILD INTO /dist
========================================================= */

const staticPages = [
  {
    route: "about",
    file: "./about/about.html"
  },
  {
    route: "privacy-policy",
    file: "./privacy-policy/privacy.html"
  },
  {
    route: "authors",
    file: "./authors/ifeanyi-okoye.html"
  }
];

staticPages.forEach(page => {
  const content = fs.readFileSync(page.file, "utf-8");

  fs.writeFileSync(
    path.join(distDir, page.route + ".html"),
    content
  );
});

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

fs.writeFileSync(
  path.join(distDir, "feed.xml"),
  rssFeed
);

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

fs.writeFileSync(
  path.join(distDir, "sitemap.xml"),
  sitemap
);

/* =========================================================
   COPY ASSETS
========================================================= */
function copyFolder(src, dest) {
  if (!fs.existsSync(src)) return;

  fs.mkdirSync(dest, { recursive: true });

  fs.readdirSync(src, { withFileTypes: true }).forEach(entry => {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);

    if (entry.isDirectory()) {
      copyFolder(srcPath, destPath);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  });
}

copyFolder("./assets", path.join(distDir, "assets"));

/* =========================================================
   ROBOTS.TXT
========================================================= */
const robots = `
User-agent: *
Allow: /

Sitemap: ${config.baseUrl}/sitemap.xml
`;

fs.writeFileSync(
  path.join(distDir, "robots.txt"),
  robots
);

/* =========================================================
   DONE
========================================================= */
console.log("✅ BUILD COMPLETE — SITE GENERATED IN /dist");
console.log("✅ RSS FEED GENERATED");
console.log("✅ SITEMAP GENERATED");
console.log("✅ ROBOTS.TXT GENERATED");
