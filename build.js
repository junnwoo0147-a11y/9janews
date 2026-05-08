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
   STATIC PAGES & FEED
========================================================= */
// (Keep the rest of your existing logic for About, Privacy, RSS, and Assets here)

console.log("✅ BUILD COMPLETE — No duplicates in articles or homepage.");
