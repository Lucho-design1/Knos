"""The money page (TASK-CHAMPION T4): each number with its primary source, re-checked on the date it carries.
Served at GET /api/money, with the share Knos needs computed at the live fee."""
MONEY = {
 "checked": "2026-10-22",
 "pools": [
  {
   "id": "global500",
   "label": "Global 500 revenue",
   "usd": 43100000000000.0,
   "shown": "$43.1T",
   "year": "2025",
   "source": "Fortune Global 500, 2026 list",
   "url": "https://fortune.com/global500/2026/"
  },
  {
   "id": "world_rd",
   "label": "World R&D",
   "usd": 2870000000000.0,
   "shown": "$2.87T",
   "year": "2024",
   "source": "WIPO, Global Innovation Index, Dec 2025",
   "url": "https://www.wipo.int/en/web/global-innovation-index/w/blogs/2025/end-of-year-edition"
  },
  {
   "id": "top2000_rd",
   "label": "Top 2,000 R&D",
   "eur": 1446000000000.0,
   "shown": "EUR 1,446B",
   "year": "2024",
   "source": "EU Industrial R&D Investment Scoreboard 2025 (JRC144638)",
   "url": "https://publications.jrc.ec.europa.eu/repository/handle/JRC144638"
  },
  {
   "id": "vc",
   "label": "Venture funding",
   "usd": 425000000000.0,
   "shown": "$425B",
   "year": "2025",
   "source": "Crunchbase",
   "url": "https://news.crunchbase.com/venture/funding-data-third-largest-year-2025/"
  }
 ],
 "barriers": [
  {
   "shown": "83% vs 3%",
   "label": "innovation top-3, ready",
   "year": "2024",
   "source": "BCG, Innovation Systems Need a Reboot",
   "url": "https://www.bcg.com/publications/2024/innovation-systems-need-a-reboot"
  },
  {
   "shown": "90%",
   "label": "of drug candidates fail",
   "year": "2022",
   "source": "Sun et al., Acta Pharm Sin B",
   "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC9293739/"
  },
  {
   "shown": "$43-79K",
   "label": "per demand study",
   "year": "2026",
   "source": "MX8 Labs, budgeting examples",
   "url": "https://mx8labs.com/2026/05/07/what-market-research-actually-costs/"
  },
  {
   "shown": "18%",
   "label": "seed dilution",
   "year": "",
   "source": "Carta data",
   "url": "https://carta.com/data/linkedin-archive/"
  }
 ],
 "not_shown": [
  {
   "claim": "failed validation adds 12-24 months (BOM)",
   "why": "no primary source found on 22 Oct 2026"
  }
 ]
}
