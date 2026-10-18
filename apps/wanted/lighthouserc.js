// Lighthouse CI (.github/workflows/lighthouse.yml): mobile, performance and accessibility at least 90.
module.exports = {
  "ci": {
    "collect": {
      "url": [
        "http://127.0.0.1:8080/",
        "http://127.0.0.1:8080/#projects",
        "http://127.0.0.1:8080/#teams",
        "http://127.0.0.1:8080/verify"
      ],
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
