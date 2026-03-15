#!/usr/bin/env python3
"""
Comprehensive test script that invokes every scraper function individually
and reports results — document count, PDF URL availability, and sample data.
Tests with a recent month so most sources should have data.
"""
import sys, os, time, json, traceback
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))
import server as S

# Use a recent month for testing
TEST_YEAR, TEST_MONTH = 2026, 2
from_iso, to_iso, from_dd, to_dd = S._month_range(TEST_YEAR, TEST_MONTH)

print(f"\n{'='*80}")
print(f"  COMPREHENSIVE SOURCE TEST — {TEST_YEAR}-{TEST_MONTH:02d}")
print(f"  Date range: {from_iso} → {to_iso}")
print(f"  Total sources: {len(S.SOURCES)}")
print(f"{'='*80}\n")

results = {}

def test_source(dtype):
    """Test one source and return a result dict."""
    cfg = S.SOURCES[dtype]
    kind = cfg.get('kind', '')
    
    # Reset cache
    S.cache[dtype] = S._empty_cache()
    
    t0 = time.time()
    error = None
    try:
        if kind == 'sebi':
            S.scrape_sebi(dtype, from_dd, to_dd)
        elif kind == 'bse':
            # BSE is shared — test via the combined function
            S.cache['BSE_PLACEMENT'] = S._empty_cache()
            S.cache['BSE_PRELIMINARY'] = S._empty_cache()
            S.scrape_bse_qip(from_iso, to_iso)
        else:
            rec = S.SCRAPER_DISPATCH.get(kind)
            if rec:
                fn, _ = rec
                fn(dtype, from_iso, to_iso)
            else:
                error = f"No dispatch for kind={kind}"
    except Exception as e:
        error = str(e)
        traceback.print_exc()
    
    elapsed = time.time() - t0
    c = S.cache[dtype]
    docs = c.get('data', [])
    
    has_pdf = sum(1 for d in docs if d.get('pdf_url'))
    no_pdf = sum(1 for d in docs if not d.get('pdf_url'))
    
    # Sample first doc
    sample = None
    if docs:
        d = docs[0]
        sample = {
            'title': (d.get('title', '') or '')[:80],
            'date': d.get('date', ''),
            'date_iso': d.get('date_iso', ''),
            'pdf_url': (d.get('pdf_url', '') or '')[:100],
            'page_url': (d.get('page_url', '') or '')[:100],
        }
    
    return {
        'dtype': dtype,
        'kind': kind,
        'total': len(docs),
        'has_pdf': has_pdf,
        'no_pdf': no_pdf,
        'error': error or c.get('error'),
        'elapsed_s': round(elapsed, 1),
        'sample': sample,
    }


# Group by kind so BSE only runs once
tested_bse = False
for dtype in sorted(S.SOURCES.keys()):
    cfg = S.SOURCES[dtype]
    kind = cfg.get('kind', '')
    
    if kind == 'bse':
        if tested_bse:
            # Just report BSE results from shared cache
            c = S.cache[dtype]
            docs = c.get('data', [])
            results[dtype] = {
                'dtype': dtype, 'kind': kind,
                'total': len(docs),
                'has_pdf': sum(1 for d in docs if d.get('pdf_url')),
                'no_pdf': sum(1 for d in docs if not d.get('pdf_url')),
                'error': c.get('error'),
                'elapsed_s': 0,
                'sample': {'title': docs[0]['title'][:80], 'date': docs[0].get('date','')} if docs else None,
            }
            continue
        tested_bse = True
    
    print(f"Testing {dtype} ({kind})...", end=' ', flush=True)
    r = test_source(dtype)
    results[dtype] = r
    
    status = '✓' if r['total'] > 0 and not r['error'] else '✗' if r['error'] else '○'
    print(f"{status}  {r['total']} docs ({r['has_pdf']} with PDF)  [{r['elapsed_s']}s]"
          + (f"  ERROR: {r['error'][:60]}" if r['error'] else ''))


# Summary
print(f"\n{'='*80}")
print("  SUMMARY")
print(f"{'='*80}")

ok = sum(1 for r in results.values() if r['total'] > 0 and not r['error'])
empty = sum(1 for r in results.values() if r['total'] == 0 and not r['error'])
errored = sum(1 for r in results.values() if r['error'])
total_docs = sum(r['total'] for r in results.values())
total_pdfs = sum(r['has_pdf'] for r in results.values())

print(f"  Sources with data:  {ok}")
print(f"  Sources empty:      {empty}  (no docs in date range — may be normal)")
print(f"  Sources errored:    {errored}")
print(f"  Total documents:    {total_docs}")
print(f"  Total with PDF:     {total_pdfs}")
print(f"  Total without PDF:  {total_docs - total_pdfs}")

if errored:
    print(f"\n  ERRORS:")
    for r in sorted(results.values(), key=lambda x: x['dtype']):
        if r['error']:
            print(f"    {r['dtype']}: {r['error'][:100]}")

# Print sample data for key sources to verify correctness
print(f"\n{'='*80}")
print("  SAMPLE DATA — KEY SOURCES")
print(f"{'='*80}")
focus_keys = ['RHP', 'DRHP', 'BSE_PLACEMENT', 'CCI_FORM1', 'CCI_GREEN', 'CCI_GUN_JUMPING',
              'CCI_ANTI_S26_1', 'RBI_MD', 'IRDAI_CIRC', 'TRAI_REG']
for k in focus_keys:
    r = results.get(k)
    if r:
        print(f"\n  {k}: {r['total']} docs, {r['has_pdf']} PDFs")
        if r['sample']:
            print(f"    Sample: {r['sample'].get('title','')}")
            print(f"    Date:   {r['sample'].get('date','')} ({r['sample'].get('date_iso','')})")
            print(f"    PDF:    {r['sample'].get('pdf_url','(none)')}")
        if r['error']:
            print(f"    ERROR:  {r['error'][:100]}")

# Save full report
report_path = os.path.join(os.path.dirname(__file__), '_test_results.json')
with open(report_path, 'w') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print(f"\nFull report saved to: {report_path}")
