#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║              LUCIO AI BRIEFCASE — One-File Runner                ║
║                                                                  ║
║  Double-click Briefcase.command  (or run: python3 briefcase.py)  ║
║  Scrapes 93 regulatory sources & downloads all PDFs locally.     ║
║  All files saved to ~/Desktop/Repositories/                      ║
║  No server, no browser, no GitHub — just this one script.        ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os, sys, json, time, threading, calendar
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─── Setup ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)
# Ensure local mode — remove any cloud env vars before importing server
for _env_key in ('CLOUD', 'RENDER', 'DOWNLOAD_DIR'):
    os.environ.pop(_env_key, None)

sys.path.insert(0, os.path.join(PROJECT_ROOT, 'backend'))
import server as srv

DOWNLOAD_DIR = srv.BASE_DOWNLOAD_DIR  # ~/Desktop/Repositories/

# ─── Terminal Colors ──────────────────────────────────────────────────────────
G = '\033[92m'   # green
R = '\033[91m'   # red
Y = '\033[93m'   # yellow
B = '\033[94m'   # blue
C = '\033[96m'   # cyan
W = '\033[97m'   # white
D = '\033[90m'   # dim
BOLD = '\033[1m'
RST = '\033[0m'

def clear():
    os.system('clear' if os.name != 'nt' else 'cls')

# ─── Banner ───────────────────────────────────────────────────────────────────
def banner():
    print(f"""
{BOLD}{W}╔══════════════════════════════════════════════════════════════╗
║{C}              LUCIO AI BRIEFCASE{W}                                ║
║{D}  93 Sources · All PDFs · Your Desktop{W}                         ║
╚══════════════════════════════════════════════════════════════╝{RST}
""")

# ─── Date Input ───────────────────────────────────────────────────────────────
def get_dates():
    now = datetime.now()
    from_default = f"{now.year}-{now.month:02d}-01"
    last_day = calendar.monthrange(now.year, now.month)[1]
    to_default = f"{now.year}-{now.month:02d}-{last_day:02d}"

    print(f"{BOLD}  Date Range{RST}")
    print(f"  {D}Default: current month ({from_default} to {to_default}){RST}")
    print(f"  {D}Enter dates as YYYY-MM-DD or press Enter for default{RST}")
    print()

    from_input = input(f"  {W}From date [{from_default}]: {RST}").strip()
    to_input = input(f"  {W}  To date [{to_default}]: {RST}").strip()

    from_iso = from_input if from_input else from_default
    to_iso = to_input if to_input else to_default

    # Validate
    try:
        fd = datetime.strptime(from_iso, "%Y-%m-%d")
        td = datetime.strptime(to_iso, "%Y-%m-%d")
        assert fd <= td
    except Exception:
        print(f"\n  {R}Invalid dates. Using defaults.{RST}")
        from_iso, to_iso = from_default, to_default

    return from_iso, to_iso


# ─── Live Progress Display ───────────────────────────────────────────────────
_lock = threading.Lock()
_src_status = {}  # key -> {'status': 'waiting'|'scraping'|'done'|'error'|'downloading'|'dl_done', 'docs': 0, 'error': '', 'label': ''}

# Source labels from the server
def _label(key):
    cfg = srv.SOURCES.get(key, {})
    kind = cfg.get('kind', '')
    # Build a simple label
    labels = {
        'sebi': 'SEBI', 'bse': 'BSE', 'cci': 'CCI', 'cci_combo': 'CCI',
        'cci_antitrust': 'CCI', 'cci_green': 'CCI', 'rbi': 'RBI',
        'rbi_md_entity': 'RBI', 'irdai': 'IRDAI', 'irdai_regs': 'IRDAI',
        'inx_circ': 'INX', 'inx_issuer': 'INX', 'tg_rera': 'RERA',
        'tg_rera_circ': 'RERA', 'tn_rera': 'RERA', 'dtcp_ka': 'RERA',
        'maha_rera': 'RERA', 'ka_reat': 'RERA', 'ka_rera': 'RERA',
        'hr_reat': 'RERA', 'dl_reat': 'RERA', 'trai': 'TRAI',
        'cgst': 'GST', 'ibbi_nclt': 'IBBI', 'eu_comp': 'EU',
        'epo_boa': 'EPO', 'edpb': 'EDPB', 'adgm': 'UAE', 'difc_ca': 'UAE',
        'mohre': 'UAE', 'govuk_finder': 'UK', 'uk_cat': 'UK',
        'uk_utiac': 'UK', 'national_archives': 'UK', 'sebi_reg': 'SEBI',
        'rbi_fema': 'RBI',
    }
    return labels.get(kind, kind.upper()[:6]) + '/' + key

def _init_status():
    for key in srv.SOURCES:
        _src_status[key] = {'status': 'waiting', 'docs': 0, 'error': '', 'label': _label(key)}

def print_progress():
    counts = {'waiting': 0, 'scraping': 0, 'done': 0, 'error': 0, 'downloading': 0, 'dl_done': 0, 'dl_error': 0}
    total_docs = 0
    for v in _src_status.values():
        counts[v['status']] = counts.get(v['status'], 0) + 1
        total_docs += v['docs']

    done = counts['done'] + counts['error']
    total = len(srv.SOURCES)
    pct = int(done / total * 100) if total else 0
    bar_w = 40
    filled = int(bar_w * pct / 100)
    bar = '█' * filled + '░' * (bar_w - filled)

    line = (f"\r  {B}[{bar}]{RST} {pct:3d}%  "
            f"{G}✓{counts['done']}{RST} "
            f"{R}✗{counts['error']}{RST} "
            f"{Y}⟳{counts['scraping']}{RST} "
            f"{D}◦{counts['waiting']}{RST}  "
            f"{C}{total_docs} docs{RST}")
    _real_stdout.write(line)
    _real_stdout.flush()

_real_stdout = sys.stdout  # save before any redirect
_real_stderr = sys.stderr


# ─── Scrape Phase ────────────────────────────────────────────────────────────
class _LogCapture:
    """Capture server print output to a log file instead of mixing with our progress bar."""
    def __init__(self, path):
        self.path = path
        self.f = open(path, 'w')
    def write(self, s):
        self.f.write(s)
        self.f.flush()
    def flush(self):
        self.f.flush()
    def restore(self):
        sys.stdout = _real_stdout
        sys.stderr = _real_stderr
        self.f.close()

def run_scrape(from_iso, to_iso):
    print(f"\n  {BOLD}Phase 1: Scraping {len(srv.SOURCES)} sources...{RST}")
    print(f"  {D}(Detailed logs: {DOWNLOAD_DIR}/scrape.log){RST}\n")
    _init_status()

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    log = _LogCapture(os.path.join(DOWNLOAD_DIR, 'scrape.log'))
    sys.stdout = log
    sys.stderr = log

    # Start watchdog
    threading.Thread(target=srv._watchdog, daemon=True).start()

    # Set active range
    from_dt = datetime.strptime(from_iso, "%Y-%m-%d")
    to_dt = datetime.strptime(to_iso, "%Y-%m-%d")
    from_dd = from_dt.strftime("%d/%m/%Y")
    to_dd = to_dt.strftime("%d/%m/%Y")

    srv.ACTIVE_MONTH['year'] = from_dt.year
    srv.ACTIVE_MONTH['month'] = from_dt.month
    srv.ACTIVE_RANGE['from_iso'] = from_iso
    srv.ACTIVE_RANGE['to_iso'] = to_iso

    for k in srv.SOURCES:
        srv.cache[k]["fetching"] = True

    srv._scrape_generation += 1
    gen = srv._scrape_generation

    # Run scrapers in background
    scrape_thread = threading.Thread(
        target=srv._run_all_scrapers,
        args=(from_iso, to_iso, from_dd, to_dd, gen),
        daemon=True
    )
    scrape_thread.start()

    # Monitor progress
    while scrape_thread.is_alive():
        with _lock:
            for key in srv.SOURCES:
                c = srv.cache[key]
                docs = [d for d in c.get('data', [])
                        if d.get('date_iso') and from_iso <= d['date_iso'] <= to_iso]
                if c.get('error'):
                    _src_status[key]['status'] = 'error'
                    _src_status[key]['error'] = str(c['error'])
                elif not c['fetching'] and not c.get('error'):
                    _src_status[key]['status'] = 'done'
                elif c['fetching']:
                    _src_status[key]['status'] = 'scraping'
                _src_status[key]['docs'] = len(docs)
        print_progress()
        time.sleep(1)

    # Final update
    for key in srv.SOURCES:
        c = srv.cache[key]
        docs = [d for d in c.get('data', [])
                if d.get('date_iso') and from_iso <= d['date_iso'] <= to_iso]
        if c.get('error'):
            _src_status[key]['status'] = 'error'
            _src_status[key]['error'] = str(c['error'])
        else:
            _src_status[key]['status'] = 'done'
        _src_status[key]['docs'] = len(docs)
    print_progress()
    _real_stdout.write('\n')  # newline after progress bar

    # Restore stdout
    log.restore()


def collect_docs(from_iso, to_iso):
    """Collect all scraped documents within the date range."""
    all_docs = []
    for dtype in srv.SOURCES:
        docs = list(srv.cache[dtype].get('data', []))
        docs = [d for d in docs if d.get('date_iso') and from_iso <= d['date_iso'] <= to_iso]
        for d in docs:
            all_docs.append({
                'id': d.get('id', ''),
                'title': d.get('title', ''),
                'date': d.get('date', ''),
                'date_iso': d.get('date_iso', ''),
                'page_url': d.get('page_url', ''),
                'pdf_url': d.get('pdf_url', ''),
                'type': dtype,
            })
    return all_docs


# ─── Download Phase ──────────────────────────────────────────────────────────
def run_downloads(all_docs):
    if not all_docs:
        print(f"\n  {Y}No documents to download.{RST}")
        return

    print(f"\n  {BOLD}Phase 2: Downloading {len(all_docs)} documents...{RST}")
    print(f"  {D}Saving to: {DOWNLOAD_DIR}{RST}")
    print(f"  {D}(Detailed logs: {DOWNLOAD_DIR}/download.log){RST}\n")

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    dl_log = _LogCapture(os.path.join(DOWNLOAD_DIR, 'download.log'))
    sys.stdout = dl_log
    sys.stderr = dl_log

    # Queue all for download
    for doc in all_docs:
        doc_id = doc['id']
        srv.download_progress[doc_id] = {
            'status': 'queued', 'filename': doc['title'], 'type': doc['type'],
            'title': doc['title'], 'date': doc['date'],
            'page_url': doc['page_url'], 'pdf_url': doc['pdf_url'],
        }

    # Download using thread pool
    total = len(all_docs)
    done_count = [0]
    err_count = [0]
    skip_count = [0]

    def _dl_one(doc):
        doc_id = doc['id']
        pdf_url = doc['pdf_url']
        page_url = doc['page_url']
        title = doc['title']
        dtype = doc['type']
        try:
            srv.resolve_and_download(doc_id, pdf_url, page_url, title, dtype)
            st = srv.download_progress.get(doc_id, {}).get('status', '')
            if st == 'done':
                done_count[0] += 1
            elif st == 'error':
                err_count[0] += 1
            else:
                skip_count[0] += 1
        except Exception as e:
            err_count[0] += 1

        # Print progress
        completed = done_count[0] + err_count[0] + skip_count[0]
        pct = int(completed / total * 100) if total else 0
        bar_w = 40
        filled = int(bar_w * pct / 100)
        bar = '█' * filled + '░' * (bar_w - filled)
        line = (f"\r  {B}[{bar}]{RST} {pct:3d}%  "
                f"{G}✓{done_count[0]}{RST} "
                f"{R}✗{err_count[0]}{RST} "
                f"{D}of {total}{RST}")
        _real_stdout.write(line)
        _real_stdout.flush()

    # Group by source for smarter parallelism
    from collections import defaultdict
    by_source = defaultdict(list)
    for doc in all_docs:
        by_source[doc['type']].append(doc)

    # Run downloads with limited concurrency per source
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = []
        for src_docs in by_source.values():
            for doc in src_docs:
                futures.append(pool.submit(_dl_one, doc))
        for f in as_completed(futures):
            try:
                f.result(timeout=300)
            except Exception:
                pass

    _real_stdout.write('\n')  # newline after progress bar
    dl_log.restore()
    return done_count[0], err_count[0], skip_count[0]


# ─── Summary Report ──────────────────────────────────────────────────────────
def print_scrape_summary(from_iso, to_iso):
    print(f"\n{BOLD}{'═' * 62}{RST}")
    print(f"{BOLD}  SCRAPE RESULTS{RST}")
    print(f"{'═' * 62}")

    ok_sources = [k for k, v in _src_status.items() if v['status'] == 'done']
    err_sources = [k for k, v in _src_status.items() if v['status'] == 'error']
    empty_sources = [k for k, v in _src_status.items() if v['status'] == 'done' and v['docs'] == 0]
    total_docs = sum(v['docs'] for v in _src_status.values())

    print(f"  {G}✓ OK: {len(ok_sources)} sources{RST}")
    print(f"  {R}✗ Errors: {len(err_sources)} sources{RST}")
    print(f"  {Y}○ Empty: {len(empty_sources)} sources{RST}")
    print(f"  {C}📄 Total documents: {total_docs}{RST}")
    print(f"  {D}📅 Date range: {from_iso} → {to_iso}{RST}")

    # Show sources with documents
    print(f"\n  {BOLD}Sources with documents:{RST}")
    for key in sorted(srv.SOURCES.keys()):
        v = _src_status.get(key, {})
        if v.get('docs', 0) > 0:
            print(f"    {G}✓{RST} {v['label']:40s} {C}{v['docs']:4d} docs{RST}")

    # Show errors
    if err_sources:
        print(f"\n  {BOLD}Failed sources:{RST}")
        for key in err_sources:
            v = _src_status[key]
            err_msg = v['error'][:60] if v['error'] else 'Unknown'
            print(f"    {R}✗{RST} {v['label']:40s} {D}{err_msg}{RST}")

    return total_docs


def print_download_summary(done, errors, skipped, total):
    print(f"\n{'═' * 62}")
    print(f"{BOLD}  DOWNLOAD RESULTS{RST}")
    print(f"{'═' * 62}")
    print(f"  {G}✓ Downloaded: {done}{RST}")
    print(f"  {R}✗ Failed: {errors}{RST}")
    if skipped:
        print(f"  {Y}○ Skipped: {skipped}{RST}")
    print(f"  {D}📁 Location: {DOWNLOAD_DIR}{RST}")

    # Show failed downloads
    failed = [(k, v) for k, v in srv.download_progress.items()
              if v.get('status') == 'error']
    if failed:
        print(f"\n  {BOLD}Failed downloads:{RST}")
        for doc_id, info in failed[:30]:
            title = info.get('title', doc_id)[:50]
            err = info.get('error', 'Unknown')[:50]
            dtype = info.get('type', '?')
            print(f"    {R}✗{RST} [{dtype}] {title}")
            print(f"      {D}{err}{RST}")
        if len(failed) > 30:
            print(f"    {D}... and {len(failed) - 30} more{RST}")

    # Save report
    report_path = os.path.join(DOWNLOAD_DIR, 'download_report.json')
    report = {
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total': total,
        'downloaded': done,
        'failed': errors,
        'skipped': skipped,
        'failed_items': [
            {
                'id': k,
                'title': v.get('title', ''),
                'type': v.get('type', ''),
                'error': v.get('error', ''),
                'pdf_url': v.get('pdf_url', ''),
                'page_url': v.get('page_url', ''),
            }
            for k, v in srv.download_progress.items()
            if v.get('status') == 'error'
        ]
    }
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n  {D}Report saved: {report_path}{RST}")


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    clear()
    banner()

    from_iso, to_iso = get_dates()

    print(f"\n  {BOLD}{C}Scraping {len(srv.SOURCES)} sources for {from_iso} → {to_iso}{RST}")
    print(f"  {D}Downloads will be saved to: {DOWNLOAD_DIR}{RST}")
    print()

    # Phase 1: Scrape
    t0 = time.time()
    run_scrape(from_iso, to_iso)
    scrape_time = time.time() - t0

    total_docs = print_scrape_summary(from_iso, to_iso)

    if total_docs == 0:
        print(f"\n  {Y}No documents found for this date range.{RST}")
        print(f"\n{D}  Done in {scrape_time:.0f}s{RST}\n")
        return

    # Ask to download
    print()
    choice = input(f"  {W}Download all {total_docs} documents? [Y/n]: {RST}").strip().lower()
    if choice in ('n', 'no'):
        print(f"\n  {D}Skipping downloads. Done in {scrape_time:.0f}s{RST}\n")
        return

    # Phase 2: Download
    all_docs = collect_docs(from_iso, to_iso)
    t1 = time.time()
    result = run_downloads(all_docs)
    dl_time = time.time() - t1

    if result:
        done, errors, skipped = result
        print_download_summary(done, errors, skipped, len(all_docs))

    total_time = time.time() - t0
    print(f"\n{'═' * 62}")
    print(f"  {BOLD}Total time: {int(total_time // 60)}m {int(total_time % 60)}s{RST}")
    print(f"  {D}Scrape: {int(scrape_time // 60)}m {int(scrape_time % 60)}s · Download: {int(dl_time // 60)}m {int(dl_time % 60)}s{RST}")
    print(f"{'═' * 62}\n")

    # Open the folder
    if sys.platform == 'darwin':
        os.system(f'open "{DOWNLOAD_DIR}"')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n  {Y}Stopped by user.{RST}\n")
