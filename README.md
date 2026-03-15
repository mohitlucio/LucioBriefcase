# Lucio AI Briefcase — Regulatory Document Automation Machine

A zero-dependency Python automation tool that scrapes **93 regulatory document sources** across **15+ Indian and international regulators** in real time, and displays them in a live web dashboard.

> **[Live Demo →](https://mohitlucio.github.io/LucioBriefcase/)**

![Python](https://img.shields.io/badge/python-3.8%2B-blue?logo=python&logoColor=white)
![Sources](https://img.shields.io/badge/sources-93-green)
![Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)
![License](https://img.shields.io/badge/license-MIT-blue)

---

## What It Does

On startup, the system simultaneously scrapes dozens of regulatory bodies for new filings and documents. The dashboard lets you:

- **Browse** all documents by regulator category (SEBI, BSE, CCI, RBI, IRDAI, RERA, TRAI, EU, UK, UAE…)
- **Filter** by date range, search by title or company
- **Download** PDFs directly to organized local folders
- **Audit** — run a full accuracy check that HEAD-verifies every cached PDF URL
- **Export** audit reports as CSV or JSON

## Covered Regulators (93 Sources)

| Category | Regulators / Sources |
|---|---|
| **SEBI** | RHP, DRHP, Rights LoF, InvIT (6 types), REIT, Informal Guidance, Consultation Papers, Circulars, Final Offer, LODR, ICDR, Takeover, AIF |
| **BSE** | QIP Placement Documents, Draft/Preliminary Placement |
| **CCI** | Form I/II/III, Gun Jumping, Approved-with-Mod, Antitrust (S26.1/.2/.6/.7, S27, S33, Other), Green Channel |
| **RBI** | Master Directions, Master Circulars, 9 Entity Types (Commercial Banks, SFBs, Payment Banks, etc.), FEMA Directions/Circulars/Notifications |
| **IRDAI** | Circulars, Gazette Notified Regulations |
| **India INX** | Circulars & Notices, Issuer Documents |
| **RERA** | Telangana (4 types), Tamil Nadu, Maharashtra, Karnataka (REAT + RERA), Haryana REAT, Delhi REAT, DTCP Karnataka |
| **TRAI** | Directions, Regulations, Recommendations, Consultation Papers |
| **GST** | CGST Circulars |
| **IBBI/NCLT** | Resolution & Admission Orders |
| **EU Competition** | Mergers (Reg.139/2004), Antitrust & Cartels, DMA, Foreign Subsidies |
| **EPO** | Board of Appeal Decisions |
| **GDPR (EDPB)** | Guidelines, Binding Decisions, Opinions |
| **UAE** | ADGM Court Judgments, DIFC Court of Appeal, MOHRE Laws & Resolutions |
| **UK Tribunals** | Employment (England & Scotland), Admin Appeals, CAT, CMA (Mergers & Non-merger), EAT, UTIAC, Land Chamber, Tax Chancery, Tax FTT |

## Architecture

```
LucioBriefcase/
├── run.py                  ← One-click launcher
├── Launch_Briefcase.command ← macOS double-click launcher
├── backend/
│   └── server.py           ← Full backend (5400+ lines, stdlib only)
├── frontend/
│   └── index.html          ← Single-file SPA dashboard
├── tests/
│   ├── test_all_sources.py ← Tests all 93 sources
│   └── test_new_sources.py ← Tests recently added sources
└── docs/
    └── index.html          ← GitHub Pages demo
```

### Backend

- **Server:** `ThreadingHTTPServer` on `localhost:8765`
- **Concurrency:** SEBI sources run sequentially (WAF avoidance with 20s gaps); all non-SEBI sources run in parallel via `ThreadPoolExecutor`
- **Watchdog:** Resets scrapers stuck >600s
- **Downloads:** `Semaphore(40)` global cap; `curl` fallback for HTTP/2 domains
- **Storage:** All PDFs saved to `~/Desktop/Repositories/<SourceType>/`

### Frontend

- Self-contained single-file SPA (HTML + CSS + JS)
- Clean flat design with Inter font
- Global progress bar + per-source status dots
- Category tabs with real-time document counts
- Full-screen Downloads modal (in-progress / completed / failed)
- Accuracy Audit modal with CSV/JSON export

## Quick Start

### Requirements

- **Python 3.8+** (no pip packages needed — 100% stdlib)

### Run

```bash
# Option 1: Command line
python3 run.py

# Option 2: macOS double-click
open Launch_Briefcase.command
```

The dashboard opens automatically at **http://localhost:8765**

### Run Tests

```bash
python3 run_tests.py
```

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Serves the dashboard |
| `/api/status` | GET | Per-source cache state |
| `/api/active_month` | GET | Current active month + date range |
| `/api/documents?type=RHP` | GET | Filtered docs for one source |
| `/api/unified?from=&to=&search=` | GET | All sources merged, date-filtered |
| `/api/audit` | GET | Parallel HEAD-check of all cached PDF URLs |
| `/api/set_month` | POST | Change active scraping month |
| `/api/download` | POST | Trigger PDF download |

## Built By

**Mohit Sharma**

## License

MIT
