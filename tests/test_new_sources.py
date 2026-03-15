#!/usr/bin/env python3
"""Test all 9 newly added sources."""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))
import server as S

NEW_SOURCES = [
    'SEBI_CIRCULARS', 'SEBI_FINAL_OFFER',
    'SEBI_LODR', 'SEBI_ICDR', 'SEBI_TAKEOVER', 'SEBI_AIF',
    'RBI_FEMA_DIR', 'RBI_FEMA_CIRC', 'RBI_FEMA_NOTIF',
]

from_iso, to_iso, from_dd, to_dd = S._month_range(2026, 3)
print(f'\nDate range: {from_iso} to {to_iso}')
print(f'Testing {len(NEW_SOURCES)} new sources...')
print('=' * 80)

results = []
for dtype in NEW_SOURCES:
    cfg = S.SOURCES[dtype]
    kind = cfg.get('kind', '')
    S.cache[dtype] = S._empty_cache()
    t0 = time.time()
    error = None
    try:
        if kind == 'sebi':
            S.scrape_sebi(dtype, from_dd, to_dd)
        else:
            rec = S.SCRAPER_DISPATCH.get(kind)
            if rec:
                fn, _ = rec
                fn(dtype, from_iso, to_iso)
            else:
                error = f'No dispatch for kind={kind}'
    except Exception as e:
        error = str(e)

    elapsed = time.time() - t0
    c = S.cache[dtype]
    docs = c.get('data', [])
    has_pdf = sum(1 for d in docs if d.get('pdf_url'))
    err_msg = error or c.get('error') or ''
    status = 'PASS' if not err_msg else 'FAIL'

    print(f'\n[{status}] {dtype}')
    print(f'  Docs: {len(docs)} | PDFs: {has_pdf} | Time: {elapsed:.1f}s')
    if err_msg:
        print(f'  Error: {err_msg[:80]}')
    if docs:
        d = docs[0]
        print(f'  Sample: [{d.get("date_iso", "")}] {d.get("title", "")[:70]}')
        print(f'  PDF:    {d.get("pdf_url", "")[:80] or "(none)"}')

    results.append({
        'source': dtype, 'docs': len(docs), 'pdfs': has_pdf,
        'error': err_msg, 'time': round(elapsed, 1)
    })

print('\n' + '=' * 80)
total_docs = sum(r['docs'] for r in results)
total_pdfs = sum(r['pdfs'] for r in results)
passed = sum(1 for r in results if not r['error'])
print(f'RESULT: {passed}/{len(results)} passed | {total_docs} total docs | {total_pdfs} PDFs')
if passed < len(results):
    print('Failed:')
    for r in results:
        if r['error']:
            print(f"  {r['source']}: {r['error'][:60]}")
print()
