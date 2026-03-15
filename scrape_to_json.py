#!/usr/bin/env python3
"""
scrape_to_json.py — Headless scraper that runs all 93 sources and exports
results to docs/data.json for static GitHub Pages deployment.

Usage:  python3 scrape_to_json.py
Output: docs/data.json (committed by GitHub Actions)
"""

import sys, os, json, time, threading, calendar
from datetime import datetime

# Force cloud mode so the server doesn't try to open browsers or use Desktop paths
os.environ['CLOUD'] = '1'
os.environ['DOWNLOAD_DIR'] = '/tmp/Repositories'

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

import server as srv

def main():
    now = datetime.now()
    y, m = now.year, now.month
    from_iso, to_iso, from_dd, to_dd = srv._month_range(y, m)

    print(f"Scraping {len(srv.SOURCES)} sources for {y}-{m:02d} ({from_iso} to {to_iso})")
    print("=" * 60)

    # Mark all as fetching
    for k in srv.SOURCES:
        srv.cache[k]["fetching"] = True

    # Run the watchdog
    threading.Thread(target=srv._watchdog, daemon=True).start()

    # Bump generation and run scrapers synchronously (blocking)
    srv._scrape_generation += 1
    gen = srv._scrape_generation
    srv._run_all_scrapers(from_iso, to_iso, from_dd, to_dd, gen)

    # Collect results
    sources = {}
    status = {}
    total_docs = 0
    ok_count = 0
    err_count = 0

    for dtype in srv.SOURCES:
        c = srv.cache[dtype]
        docs = list(c.get("data", []))
        # Filter to active month
        docs = [d for d in docs if d.get("date_iso") and from_iso <= d["date_iso"] <= to_iso]
        sources[dtype] = docs
        total_docs += len(docs)

        fetched = len(docs)
        error = c.get("error")
        status[dtype] = {
            "fetching": False,
            "total": c.get("total", 0),
            "fetched": fetched,
            "pages_done": c.get("pages_done", 0),
            "error": error,
            "fetch_started_at": c.get("fetch_started_at", 0),
        }
        if error:
            err_count += 1
        else:
            ok_count += 1

    # Build the output JSON
    output = {
        "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "active_month": {"year": y, "month": m},
        "date_range": {"from_iso": from_iso, "to_iso": to_iso},
        "total_sources": len(srv.SOURCES),
        "total_documents": total_docs,
        "sources_ok": ok_count,
        "sources_error": err_count,
        "sources": sources,
        "status": status,
    }

    # Write to docs/data.json
    out_dir = os.path.join(os.path.dirname(__file__), "docs")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "data.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = os.path.getsize(out_path) / 1024
    print(f"\n{'=' * 60}")
    print(f"Done! {total_docs} documents from {ok_count} sources ({err_count} errors)")
    print(f"Written to {out_path} ({size_kb:.1f} KB)")

if __name__ == "__main__":
    main()
