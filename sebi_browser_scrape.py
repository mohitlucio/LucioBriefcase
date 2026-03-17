#!/usr/bin/env python3
"""
SEBI Browser Scraper — Uses Chrome via AppleScript to bypass SEBI WAF.

1. Opens each SEBI URL in Chrome (real browser passes WAF/Cloudflare)
2. Uses AppleScript+JavaScript to fill date forms and submit
3. Extracts rendered HTML via JavaScript
4. Parses docs using the server's existing parser
5. Injects results into the running server via /api/browser_inject

Usage: python3 sebi_browser_scrape.py [from_date] [to_date]
"""

import os, sys, json, time, re, subprocess, urllib.request, urllib.parse, tempfile
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'backend'))
import server as srv

# ─── Config ───────────────────────────────────────────────────────────────────
FROM_ISO = sys.argv[1] if len(sys.argv) > 1 else '2026-02-16'
TO_ISO   = sys.argv[2] if len(sys.argv) > 2 else '2026-03-16'
FROM_DD  = datetime.strptime(FROM_ISO, "%Y-%m-%d").strftime("%d/%m/%Y")
TO_DD    = datetime.strptime(TO_ISO,   "%Y-%m-%d").strftime("%d/%m/%Y")

API = 'http://localhost:8765'
SEBI_BASE = "https://www.sebi.gov.in"

SEBI_LISTING_SOURCES = {k: v for k, v in srv.SOURCES.items() if v.get('kind') == 'sebi'}
SEBI_REG_SOURCES = {k: v for k, v in srv.SOURCES.items() if v.get('kind') == 'sebi_reg'}

G = '\033[92m'; R = '\033[91m'; Y = '\033[93m'; C = '\033[96m'; D = '\033[90m'
BOLD = '\033[1m'; RST = '\033[0m'

TMPDIR = tempfile.mkdtemp(prefix='sebi_browser_')

# ─── AppleScript Helpers ─────────────────────────────────────────────────────

def run_applescript(script, timeout=60):
    """Run an AppleScript and return stdout."""
    r = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip() if r.returncode == 0 else ''


def chrome_navigate(url, wait_secs=5):
    """Navigate Chrome's active tab to a URL and wait for load."""
    script = f'''
    tell application "Google Chrome"
        activate
        if (count of windows) = 0 then
            make new window
        end if
        set URL of active tab of front window to "{url}"
        delay 3
        set maxWait to 30
        set waited to 0
        repeat while (loading of active tab of front window) and waited < maxWait
            delay 1
            set waited to waited + 1
        end repeat
        delay {wait_secs}
    end tell
    '''
    run_applescript(script, timeout=60)


def chrome_js(js_code, timeout=30):
    """Execute JavaScript in Chrome's active tab and return the result.
    Writes JS to a temp file and reads via osascript to avoid escaping nightmares."""
    # Write JS to temp file
    js_file = os.path.join(TMPDIR, '_chrome_exec.js')
    with open(js_file, 'w') as f:
        f.write(js_code)
    
    # AppleScript that reads the JS file and executes it
    script = f'''
    set jsCode to read POSIX file "{js_file}" as «class utf8»
    tell application "Google Chrome"
        execute active tab of front window javascript jsCode
    end tell
    '''
    return run_applescript(script, timeout=timeout)


def chrome_get_page_html():
    """Get full page HTML from Chrome via writing to a temp file."""
    out_file = os.path.join(TMPDIR, '_page.html')
    
    # Use JS to get the HTML and store it so we can read via AppleScript
    html = chrome_js("document.documentElement.outerHTML")
    
    if html and len(html) > 500:
        return html
    
    # Try body only as fallback
    html = chrome_js("document.body.innerHTML")
    return html or ''


def chrome_wait_loaded(max_wait=25):
    """Wait for Chrome page to finish loading."""
    for _ in range(max_wait):
        state = chrome_js("document.readyState")
        if 'complete' in state:
            return True
        time.sleep(1)
    return False


# ─── SEBI Date Form ─────────────────────────────────────────────────────────

def sebi_submit_date_search(from_dd, to_dd):
    """Fill SEBI date fields and submit the search form via JavaScript."""
    js = f'''(function() {{
    var f = document.querySelector('input[name="fromDate"]');
    var t = document.querySelector('input[name="toDate"]');
    if (f) f.value = '{from_dd}';
    if (t) t.value = '{to_dd}';
    var r = document.querySelector('input[value="date"]');
    if (r) r.checked = true;
    var btns = document.querySelectorAll('input[type="submit"], input[type="button"]');
    for (var i = 0; i < btns.length; i++) {{
        var v = (btns[i].value || '').toLowerCase();
        if (v === 'go' || v === 'search' || v === 'submit') {{ btns[i].click(); return 'clicked:' + v; }}
    }}
    var form = document.forms[0];
    if (form) {{ form.submit(); return 'form-submitted'; }}
    return 'no-form';
}})()'''
    return chrome_js(js)


def sebi_ajax_next_page(page_num, src):
    """Fetch the next page of SEBI results using synchronous XHR in Chrome's context."""
    sid = src['sid']; ssid = src['ssid']; smid = src['smid']
    ajax_url = f"{SEBI_BASE}/sebiweb/ajax/home/getnewslistinfo.jsp"
    
    params = urllib.parse.urlencode({
        'nextValue': str(page_num), 'next': 'n', 'search': '',
        'fromDate': FROM_DD, 'toDate': TO_DD,
        'fromYear': '', 'toYear': '', 'deptId': '',
        'sid': sid, 'ssid': ssid, 'smid': smid,
        'ssidhidden': ssid, 'intmid': '-1',
        'sText': '', 'ssText': '', 'smText': '',
        'doDirect': str(page_num),
    })
    
    js = f'''(function() {{
    var xhr = new XMLHttpRequest();
    xhr.open('POST', '{ajax_url}', false);
    xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
    xhr.send('{params}');
    if (xhr.status === 200) return xhr.responseText;
    return 'ERROR:' + xhr.status;
}})()'''
    
    resp = chrome_js(js, timeout=30)
    if resp and '#@#' in resp:
        return resp.split('#@#')[0]
    return resp or ''


# ─── Scraping Logic ─────────────────────────────────────────────────────────

def scrape_sebi_listing(dtype, src):
    """Scrape one SEBI listing source via Chrome."""
    sid = src['sid']; ssid = src['ssid']; smid = src['smid']
    
    list_url = f"{SEBI_BASE}/sebiweb/home/HomeAction.do?doListing=yes&sid={sid}&ssid={ssid}&smid={smid}"
    print(f"  {C}[{dtype}]{RST} Opening listing page...")
    chrome_navigate(list_url, wait_secs=3)
    
    # Check for WAF
    preview = chrome_js("(document.body ? document.body.innerText : '').substring(0, 300)")
    if 'blocked' in preview.lower() or 'captcha' in preview.lower() or 'challenge' in preview.lower():
        print(f"  {Y}[{dtype}]{RST} WAF challenge — waiting 15s (solve manually if needed)...")
        time.sleep(15)
        chrome_wait_loaded()
    
    # Submit date search
    print(f"  {C}[{dtype}]{RST} Submitting date filter: {FROM_DD} → {TO_DD}")
    result = sebi_submit_date_search(FROM_DD, TO_DD)
    print(f"  {D}[{dtype}]{RST} Submit result: {result}")
    
    time.sleep(5)
    chrome_wait_loaded()
    time.sleep(2)
    
    # Get page HTML
    html = chrome_get_page_html()
    if not html or len(html) < 300:
        print(f"  {R}[{dtype}]{RST} Empty HTML after form submit")
        return []
    
    all_docs, total = srv.parse_sebi_listing(html, dtype)
    print(f"  {C}[{dtype}]{RST} Page 1: {len(all_docs)} docs (total: {total})")
    
    if not all_docs:
        return []
    
    # Paginate
    seen_ids = {d['id'] for d in all_docs}
    page_num = 1
    
    while page_num < 100 and (not total or len(all_docs) < total):
        time.sleep(2)
        page_html = sebi_ajax_next_page(page_num, src)
        
        if not page_html or len(page_html) < 100:
            break
        
        page_docs, _ = srv.parse_sebi_listing(page_html, dtype)
        new_docs = [d for d in page_docs if d['id'] not in seen_ids]
        
        if not new_docs:
            break
        
        seen_ids.update(d['id'] for d in new_docs)
        all_docs.extend(new_docs)
        page_num += 1
        
        print(f"  {C}[{dtype}]{RST} Page {page_num}: +{len(new_docs)}, total {len(all_docs)}")
        
        oldest_iso = min((d['date_iso'] for d in new_docs if d['date_iso']), default='')
        if oldest_iso and oldest_iso < FROM_ISO:
            break
    
    # Filter
    all_docs = [d for d in all_docs if d.get('date_iso') and FROM_ISO <= d['date_iso'] <= TO_ISO]
    return all_docs


def scrape_sebi_reg(dtype, src):
    """Scrape one SEBI regulation source via Chrome."""
    entry_id = src.get('sebi_entry_id', '')
    url = f"{SEBI_BASE}/sebiweb/home/HomeAction.do?doListingAmendment=yes&hfield={entry_id}"
    
    print(f"  {C}[{dtype}]{RST} Opening regulation page...")
    chrome_navigate(url, wait_secs=5)
    
    html = chrome_get_page_html()
    if not html or len(html) < 300:
        return []
    
    docs = []
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)
    for row in rows:
        dm = re.search(r'(\w{3}\s+\d{1,2},\s+\d{4})', row)
        if not dm:
            continue
        date_text = dm.group(1)
        lm = re.search(r'href=["\']([^"\']+)["\'][^>]*>([^<]+)', row, re.IGNORECASE)
        if not lm:
            continue
        href = lm.group(1).strip()
        title = lm.group(2).strip()
        if not href.startswith('http'):
            href = SEBI_BASE + href
        try:
            date_iso = datetime.strptime(date_text, "%b %d, %Y").strftime("%Y-%m-%d")
        except Exception:
            continue
        if FROM_ISO <= date_iso <= TO_ISO:
            doc_id = re.sub(r'\W+', '_', href[-30:])
            docs.append({
                "date": date_text, "date_iso": date_iso,
                "title": title, "company": "",
                "page_url": href, "pdf_url": "",
                "type": dtype, "id": doc_id,
            })
    return docs


def inject_to_server(dtype, docs):
    """Push docs into the running server via /api/browser_inject."""
    try:
        payload = json.dumps({"type": dtype, "docs": docs}).encode()
        req = urllib.request.Request(
            f'{API}/api/browser_inject', data=payload,
            headers={'Content-Type': 'application/json'}, method='POST')
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read()).get('status') == 'ok'
    except Exception as e:
        print(f"  {R}[{dtype}]{RST} Inject failed: {e}")
        return False


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{BOLD}  SEBI Browser Scraper (Chrome){RST}")
    print(f"  {D}Date range: {FROM_ISO} → {TO_ISO} ({FROM_DD} → {TO_DD}){RST}")
    print(f"  {D}Chrome will open each SEBI page to bypass WAF{RST}")
    print(f"  {D}Results injected into server at {API}{RST}\n")
    
    all_sources = list(SEBI_LISTING_SOURCES.items()) + list(SEBI_REG_SOURCES.items())
    total_docs = 0
    results = {}
    
    for i, (dtype, src) in enumerate(all_sources):
        print(f"\n  {BOLD}[{i+1}/{len(all_sources)}] {dtype}{RST}")
        
        try:
            if src.get('kind') == 'sebi_reg':
                docs = scrape_sebi_reg(dtype, src)
            else:
                docs = scrape_sebi_listing(dtype, src)
            
            results[dtype] = docs
            total_docs += len(docs)
            print(f"  {G}[{dtype}]{RST} ✓ {len(docs)} documents")
            
            if inject_to_server(dtype, docs):
                print(f"  {D}[{dtype}]{RST} → Injected into server")
            
        except Exception as e:
            print(f"  {R}[{dtype}]{RST} ✗ Error: {e}")
            results[dtype] = []
            # Still inject empty to mark as done (not fetching)
            inject_to_server(dtype, [])
        
        if i < len(all_sources) - 1:
            time.sleep(3)
    
    # Summary
    print(f"\n{'═' * 60}")
    print(f"{BOLD}  SEBI BROWSER SCRAPE RESULTS{RST}")
    print(f"{'═' * 60}")
    for dtype, docs in sorted(results.items()):
        count = len(docs)
        sym = f"{G}✓{RST}" if count > 0 else f"{Y}○{RST}"
        print(f"  {sym} {dtype:25s} {count} docs")
    print(f"\n  {C}Total: {total_docs} SEBI documents{RST}")
    print(f"  {D}Refresh dashboard at {API} to see results{RST}\n")
    
    import shutil
    shutil.rmtree(TMPDIR, ignore_errors=True)


if __name__ == '__main__':
    main()
