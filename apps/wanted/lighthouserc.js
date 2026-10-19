// Lighthouse CI (.github/workflows/lighthouse.yml): mobile, performance and accessibility at least 90 on EVERY page:
// every page of the front door (the Pages build of web/, served on :8081: the bare address with the research products,
// How we verify, each view, each page a module fills, each page added by name, and the site's other HTML files) and
// every view of the app (apps/wanted, served on :8080). tests/test_lighthouse_pages.py holds this list to the site's
// own lists (web/views.js, web/front.js MOUNTS) and the app's views (static/app.js VIEWS), so a new page is measured.
const SITE = "http://127.0.0.1:8081/";
const APP = "http://127.0.0.1:8080/";
const site = ["", "#verify", "#check", "#protect", "#fund", "#claim", "#pricing", "#records", "#network", "#build",
  "#buy", "#install", "#capabilities", "#status", "#index", "#pilot", "#reproduce", "#shadow", "#verifier", "#playground", "#terms",
  "#supplier", "#invoice-statement", "#story", "#keyholder", "#record",
  "#approve", "#rails", "#enforcement", "#judges", "#finance", "#payee", "#vendor", "#apps",
  "faq.html", "check/", "privacy.html", "wanted.html"];
const app = ["", "#buy", "#fund", "#contribute", "#make", "#research", "#projects", "#teams", "#agents", "verify"];
module.exports = {
  "ci": {
    "collect": {
      "url": [...site.map((p) => SITE + p), ...app.map((p) => APP + p)],
      "numberOfRuns": 1,
      "settings": {
        "formFactor": "mobile",
        "screenEmulation": {
          "mobile": true,
          "width": 412,
          "height": 823,
          "deviceScaleFactor": 1.75
        },
        "chromeFlags": "--no-sandbox --headless=new",
        "onlyCategories": [
          "performance",
          "accessibility",
          "best-practices"
        ]
      }
    },
    "assert": {
      "assertions": {
        "categories:performance": [
          "error",
          {
            "minScore": 0.9
          }
        ],
        "categories:accessibility": [
          "error",
          {
            "minScore": 0.9
          }
        ]
      }
    },
    "upload": {
      "target": "filesystem",
      "outputDir": ".lighthouseci"
    }
  }
};
