#!/usr/bin/env python3
"""
scrape_to_json.py — Headless scraper that runs sources and exports
results to docs/data.json for static GitHub Pages deployment.

Usage:
  python3 scrape_to_json.py                         # scrape all 93 sources
  python3 scrape_to_json.py --sources RHP,DRHP      # scrape specific sources only
  python3 scrape_to_json.py --month 2026-02          # scrape a specific month
"""

import sys, os, json, time, threading, calendar, argparse
from datetime import datetime

# Force cloud mode so the server doesn't try to open browsers or use Desktop paths
os.environ['CLOUD'] = '1'
os.environ['DOWNLOAD_DIR'] = '/tmp/Repositories'

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

import server as srv

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sources', type=str, default='',
                        help='Comma-separated source keys to scrape (default: all)')
    parser.add_argument('--month', type=str, default='',
                        help='Month to scrape as YYYY-MM (default: current)')
    args = parser.parse_args()

    # Determine month
    if args.month:
        parts = args.month.split('-')
        y, m = int(parts[0]), int(parts[1])
    else:
        now = datetime.now()
        y, m = now.year, now.month
    from_iso, to_iso, from_dd, to_dd = srv._month_range(y, m)

    # Determine which sources to scrape
    if args.sources:
        target_keys = [k.strip() for k in args.sources.split(',') if k.strip() in srv.SOURCES]
        if not target_keys:
            print(f"ERROR: No valid source keys found in: {args.sources}")
            print(f"Valid keys: {', '.join(sorted(srv.SOURCES.keys()))}")
            sys.exit(1)
        partial = True
    else:
        target_keys = list(srv.SOURCES.keys())
        partial = False

    print(f"Scraping {len(target_keys)}/{len(srv.SOURCES)} sources for {y}-{m:02d} ({from_iso} to {to_iso})")
    if partial:
        print(f"Target sources: {', '.join(target_keys)}")
    print("=" * 60)

    # For partial scrapes, load existing data.json first so we merge
    out_dir = os.path.join(os.path.dirname(__file__), "docs")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "data.json")
    existing = None
    if partial and os.path.exists(out_path):
        try:
            with open(out_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            print(f"Loaded existing data.json ({existing.get('total_documents', 0)} docs)")
        except Exception:
            existing = None

    print(f"Scraping {len(srv.SOURCES)} sources for {y}-{m:02d} ({from_iso} to {to_iso})")
    print("=" * 60)

    # Mark target sources as fetching
    for k in target_keys:
        srv.cache[k]["fetching"] = True

    # Run the watchdog
    threading.Thread(target=srv._watchdog, daemon=True).start()

    # Bump generation and run scrapers
    srv._scrape_generation += 1
    gen = srv._scrape_generation
    if partial:
        # Run only targeted sources using thread pool
        from concurrent.futures import ThreadPoolExecutor
        def _scrape_one(dtype):
            cfg = srv.SOURCES[dtype]
            kind = cfg.get('kind', '')
            try:
                rec = srv.SCRAPER_DISPATCH.get(kind)
                if rec:
                    fn, _ = rec
                    fn(dtype, from_iso, to_iso)
                else:
                    srv.cache[dtype].update({"fetching": False})
            except Exception as e:
                print(f"[RUNNER] {dtype} raised {e}")
                srv.cache[dtype].update({"error": str(e), "fetching": False})
        with ThreadPoolExecutor(max_workers=6) as pool:
            pool.map(_scrape_one, target_keys)
    else:
        srv._run_all_scrapers(from_iso, to_iso, from_dd, to_dd, gen)

    # Collect results
    sources = {}
    status = {}
    total_docs = 0
    ok_count = 0
    err_count = 0

    # For partial scrapes, start with existing data
    if partial and existing:
        sources = dict(existing.get("sources", {}))
        status = dict(existing.get("status", {}))

    for dtype in (target_keys if partial else srv.SOURCES):
        c = srv.cache[dtype]
        docs = list(c.get("data", []))
        # Filter to active month
        docs = [d for d in docs if d.get("date_iso") and from_iso <= d["date_iso"] <= to_iso]
        sources[dtype] = docs

        error = c.get("error")
        status[dtype] = {
            "fetching": False,
            "total": c.get("total", 0),
            "fetched": len(docs),
            "pages_done": c.get("pages_done", 0),
            "error": error,
            "fetch_started_at": c.get("fetch_started_at", 0),
        }

    # Recount totals from all sources
    for dtype in srv.SOURCES:
        docs = sources.get(dtype, [])
        total_docs += len(docs) if isinstance(docs, list) else 0
        s = status.get(dtype, {})
        if s.get("error"):
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

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = os.path.getsize(out_path) / 1024
    print(f"\n{'=' * 60}")
    action = f"partial ({len(target_keys)} sources)" if partial else "full"
    print(f"Done [{action}]! {total_docs} documents from {ok_count} sources ({err_count} errors)")
    print(f"Written to {out_path} ({size_kb:.1f} KB)")

if __name__ == "__main__":
    main()
