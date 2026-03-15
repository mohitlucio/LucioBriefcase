#!/usr/bin/env python3
"""
download_all.py — Scrape documents and download PDFs to your laptop.

Usage:
  python3 download_all.py                                        # Current month
  python3 download_all.py --from 2026-02-16 --to 2026-03-15     # Custom date range
  python3 download_all.py --from 2026-02-16 --to 2026-03-15 --sources RHP,DRHP

Downloads go to: ~/Desktop/Repositories/<SourceType>/
Evidence report: ~/Desktop/Repositories/download_report.json + .txt
"""

import sys, os, json, time, threading, argparse, re, ssl, urllib.request, calendar
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Setup paths — download to Desktop, never /tmp
os.environ['CLOUD'] = '0'
os.environ.pop('DOWNLOAD_DIR', None)  # Ensure server uses Desktop path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

import server as srv

# ─── CONFIG ──────────────────────────────────────────────────────────────────
DL_DIR = os.path.expanduser('~/Desktop/Repositories')
MAX_WORKERS = 6
PDF_TIMEOUT = 180


def scrape_all_sources(from_iso, to_iso, target_keys=None):
    """Run all scrapers for the given date range."""
    keys = target_keys or list(srv.SOURCES.keys())

    # Compute dd/mm/yyyy for SEBI scrapers
    try:
        fd = datetime.strptime(from_iso, "%Y-%m-%d")
        td = datetime.strptime(to_iso, "%Y-%m-%d")
        from_dd = fd.strftime("%d/%m/%Y")
        to_dd = td.strftime("%d/%m/%Y")
    except Exception:
        from_dd = to_dd = None

    print(f"\n{'='*70}")
    print(f"  SCRAPING {len(keys)} sources  |  {from_iso} → {to_iso}")
    print(f"{'='*70}\n")

    for k in keys:
        srv.cache[k]["fetching"] = True

    threading.Thread(target=srv._watchdog, daemon=True).start()
    srv._scrape_generation += 1
    gen = srv._scrape_generation

    # Override ACTIVE_RANGE so scrapers use our custom range
    srv.ACTIVE_RANGE['from_iso'] = from_iso
    srv.ACTIVE_RANGE['to_iso'] = to_iso
    srv.ACTIVE_RANGE['is_custom'] = True

    srv._run_all_scrapers(from_iso, to_iso, from_dd, to_dd, gen)

    # Collect documents filtered to our date range
    all_docs = []
    for dtype in keys:
        c = srv.cache[dtype]
        docs = list(c.get("data", []))
        docs = [d for d in docs if d.get("date_iso") and from_iso <= d["date_iso"] <= to_iso]
        for d in docs:
            d['_dtype'] = dtype
        all_docs.extend(docs)

    return all_docs


def download_pdf(doc, index, total):
    """Download a single PDF. Returns result dict."""
    dtype = doc['_dtype']
    doc_id = doc.get('id', 'unknown')
    pdf_url = doc.get('pdf_url', '')
    page_url = doc.get('page_url', '')
    title = doc.get('company') or doc.get('title') or doc_id
    date = doc.get('date', '')

    src_label = dtype
    src_cfg = srv.SOURCES.get(dtype, {})
    folder = src_cfg.get('folder', os.path.join(DL_DIR, dtype))

    result = {
        'index': index,
        'source': dtype,
        'title': title,
        'date': date,
        'doc_id': doc_id,
        'page_url': page_url,
        'pdf_url': pdf_url,
        'status': 'pending',
        'error': None,
        'filename': None,
        'size_kb': 0,
    }

    if not pdf_url:
        # Try resolving SEBI PDF URL from page
        if page_url and 'sebi.gov.in' in page_url:
            try:
                resolved = srv.get_sebi_pdf_url(page_url)
                if resolved:
                    pdf_url = resolved
                    result['pdf_url'] = resolved
            except Exception as e:
                result['status'] = 'failed'
                result['error'] = f'PDF resolution failed: {e}'
                return result
        if not pdf_url:
            result['status'] = 'failed'
            result['error'] = 'No PDF URL available'
            return result

    # Build filename
    safe_title = re.sub(r'[<>:"/\\|?*\0]', '', title).strip('. ')
    safe_title = re.sub(r'\s+', ' ', safe_title)
    if len(safe_title) > 120:
        safe_title = safe_title[:115]
    if date:
        safe_date = date.replace('/', '-')
        filename = f"{safe_date} — {safe_title}.pdf"
    else:
        filename = f"{safe_title}.pdf"

    os.makedirs(folder, exist_ok=True)
    filepath = os.path.join(folder, filename)
    if os.path.exists(filepath):
        base, ext = os.path.splitext(filename)
        filename = f"{base}_{doc_id[-6:]}{ext}"
        filepath = os.path.join(folder, filename)

    tmp_path = filepath + '.tmp'

    # Download
    ua = srv.SEBI_UA
    referer = srv._referer_for(pdf_url, dtype)
    last_err = None

    for attempt in range(3):
        if attempt > 0:
            time.sleep(3 * attempt)
        try:
            # Try curl first for better compatibility
            ok, err_msg = srv._curl_download(pdf_url, tmp_path, referer)
            if not ok:
                # Fallback to urllib
                req = urllib.request.Request(pdf_url, headers={
                    'User-Agent': ua,
                    'Accept': 'application/pdf,*/*',
                    'Referer': referer,
                })
                with urllib.request.urlopen(req, timeout=PDF_TIMEOUT, context=srv.SSL_CTX) as resp:
                    with open(tmp_path, 'wb') as f:
                        while True:
                            chunk = resp.read(65536)
                            if not chunk:
                                break
                            f.write(chunk)

            file_size = os.path.getsize(tmp_path) if os.path.exists(tmp_path) else 0
            if file_size < 500:
                raise ValueError(f"File too small ({file_size} bytes)")

            # Validate PDF
            with open(tmp_path, 'rb') as f:
                header = f.read(8)
            if not header[:5].startswith(b'%PDF'):
                with open(tmp_path, 'rb') as f:
                    first_500 = f.read(500).lower()
                if b'tspd' in first_500 or b'please enable javascript' in first_500:
                    raise ValueError("Bot-protection page returned instead of PDF")
                if b'<html' in first_500 or b'<!doctype' in first_500:
                    raise ValueError("HTML page returned instead of PDF")

            os.replace(tmp_path, filepath)
            size_kb = file_size // 1024
            result['status'] = 'success'
            result['filename'] = filename
            result['size_kb'] = size_kb
            print(f"  [{index}/{total}] ✓ {dtype}/{filename} ({size_kb} KB)")
            last_err = None
            break

        except Exception as e:
            last_err = str(e)
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    if last_err:
        result['status'] = 'failed'
        result['error'] = last_err
        print(f"  [{index}/{total}] ✗ {dtype}: {title[:50]} — {last_err[:80]}")

    return result


def generate_report(results, from_iso, to_iso, report_dir):
    """Generate evidence report as JSON + TXT."""
    success = [r for r in results if r['status'] == 'success']
    failed = [r for r in results if r['status'] == 'failed']
    no_pdf = [r for r in results if r['status'] == 'no_pdf']

    total_size = sum(r['size_kb'] for r in success)

    report = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'date_range': {'from': from_iso, 'to': to_iso},
        'summary': {
            'total_documents': len(results),
            'downloaded': len(success),
            'failed': len(failed),
            'total_size_kb': total_size,
            'total_size_mb': round(total_size / 1024, 1),
        },
        'downloaded': [{
            'source': r['source'],
            'title': r['title'],
            'date': r['date'],
            'filename': r['filename'],
            'size_kb': r['size_kb'],
            'pdf_url': r['pdf_url'],
        } for r in success],
        'failed': [{
            'source': r['source'],
            'title': r['title'],
            'date': r['date'],
            'website': r.get('page_url') or r.get('pdf_url', ''),
            'pdf_url': r['pdf_url'],
            'error': r['error'],
        } for r in failed],
    }

    # Write JSON report
    json_path = os.path.join(report_dir, 'download_report.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Write readable TXT report
    txt_path = os.path.join(report_dir, 'download_report.txt')
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("  LUCIO BRIEFCASE — DOWNLOAD EVIDENCE REPORT\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"  Date Range:     {from_iso}  →  {to_iso}\n")
        f.write(f"  Generated:      {report['generated_at']}\n")
        f.write(f"  Total Docs:     {len(results)}\n")
        f.write(f"  Downloaded:     {len(success)}\n")
        f.write(f"  Failed:         {len(failed)}\n")
        f.write(f"  Total Size:     {report['summary']['total_size_mb']} MB\n")
        f.write("\n" + "-" * 80 + "\n")
        f.write("  SUCCESSFULLY DOWNLOADED\n")
        f.write("-" * 80 + "\n\n")
        for i, r in enumerate(success, 1):
            f.write(f"  {i:3d}. [{r['source']}] {r['title']}\n")
            f.write(f"       Date: {r['date']}  |  Size: {r['size_kb']} KB\n")
            f.write(f"       File: {r['filename']}\n")
            f.write(f"       URL:  {r['pdf_url']}\n\n")

        if failed:
            f.write("\n" + "-" * 80 + "\n")
            f.write("  FAILED DOWNLOADS\n")
            f.write("-" * 80 + "\n\n")
            for i, r in enumerate(failed, 1):
                f.write(f"  {i:3d}. [{r['source']}] {r['title']}\n")
                f.write(f"       Date:    {r['date']}\n")
                f.write(f"       Website: {r['website']}\n")
                f.write(f"       PDF URL: {r['pdf_url']}\n")
                f.write(f"       Error:   {r['error']}\n\n")

        f.write("=" * 80 + "\n")
        f.write("  END OF REPORT\n")
        f.write("=" * 80 + "\n")

    return json_path, txt_path, report


def main():
    parser = argparse.ArgumentParser(description='Download all scraped PDFs to your laptop')
    parser.add_argument('--from', dest='from_date', type=str, default='',
                        help='Start date YYYY-MM-DD')
    parser.add_argument('--to', dest='to_date', type=str, default='',
                        help='End date YYYY-MM-DD')
    parser.add_argument('--sources', type=str, default='',
                        help='Comma-separated source keys')
    args = parser.parse_args()

    # Default: current month
    now = datetime.now()
    if args.from_date and args.to_date:
        from_iso = args.from_date
        to_iso = args.to_date
    else:
        from_iso, to_iso, _, _ = srv._month_range(now.year, now.month)

    target_keys = None
    if args.sources:
        target_keys = [k.strip().upper() for k in args.sources.split(',') if k.strip()]

    # Step 1: Scrape
    print(f"\n🔍 Step 1: Scraping documents ({from_iso} to {to_iso})...")
    docs = scrape_all_sources(from_iso, to_iso, target_keys)
    print(f"\n   Found {len(docs)} documents")

    has_pdf = [d for d in docs if d.get('pdf_url')]
    page_only = [d for d in docs if not d.get('pdf_url') and d.get('page_url')]
    print(f"   → {len(has_pdf)} with direct PDF URL")
    print(f"   → {len(page_only)} need PDF resolution (SEBI pages)")

    if not docs:
        print("\n   No documents found for this date range.")
        return

    # Step 2: Download PDFs
    print(f"\n📥 Step 2: Downloading {len(docs)} PDFs to ~/Desktop/Repositories/...\n")
    os.makedirs(DL_DIR, exist_ok=True)

    results = []
    total = len(docs)

    # Use thread pool for parallel downloads
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {}
        for i, doc in enumerate(docs, 1):
            f = pool.submit(download_pdf, doc, i, total)
            futures[f] = doc

        for f in as_completed(futures):
            try:
                result = f.result()
                results.append(result)
            except Exception as e:
                doc = futures[f]
                results.append({
                    'index': 0, 'source': doc.get('_dtype', '?'),
                    'title': doc.get('title', '?'), 'date': doc.get('date', ''),
                    'doc_id': doc.get('id', ''), 'page_url': doc.get('page_url', ''),
                    'pdf_url': doc.get('pdf_url', ''), 'status': 'failed',
                    'error': str(e), 'filename': None, 'size_kb': 0,
                })

    # Sort by source then date
    results.sort(key=lambda r: (r['source'], r.get('date', '')))

    # Step 3: Generate report
    print(f"\n📊 Step 3: Generating evidence report...")
    json_path, txt_path, report = generate_report(results, from_iso, to_iso, DL_DIR)

    # Summary
    s = report['summary']
    print(f"\n{'='*70}")
    print(f"  DOWNLOAD COMPLETE")
    print(f"{'='*70}")
    print(f"  Documents found:    {s['total_documents']}")
    print(f"  Downloaded:         {s['downloaded']}")
    print(f"  Failed:             {s['failed']}")
    print(f"  Total size:         {s['total_size_mb']} MB")
    print(f"  Saved to:           {DL_DIR}")
    print(f"  JSON report:        {json_path}")
    print(f"  Text report:        {txt_path}")
    print(f"{'='*70}\n")

    if report['failed']:
        print("  ⚠ FAILED DOWNLOADS:")
        for r in report['failed']:
            print(f"    [{r['source']}] {r['title']}")
            print(f"      Website: {r['website']}")
            print(f"      PDF:     {r['pdf_url']}")
            print(f"      Error:   {r['error']}")
            print()


if __name__ == '__main__':
    main()
