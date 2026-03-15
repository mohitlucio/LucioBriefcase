#!/usr/bin/env python3
"""
Unified 4-Source Filing Portal Backend
Sources:
  1. SEBI RHP   — sebi.gov.in smid=11 → Desktop/RHP/
  2. SEBI DRHP  — sebi.gov.in smid=10 → Desktop/DRHP/
  3. BSE Placement         — bseindia.com/corporates/qip.aspx → Desktop/BSE_Placement/
  4. BSE Preliminary Placement — same page → Desktop/BSE_Preliminary/
"""

import ssl, urllib.request, urllib.parse, re, json, os, time, threading, traceback, calendar, http.cookiejar, html, gzip
import socketserver, subprocess, tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta

class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    request_queue_size = 64

# ─── SSL ────────────────────────────────────────────────────────────────────────
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# Separate context for SEBI — proper TLS verification (like a real browser) to
# avoid WAF fingerprinting that flags CERT_NONE connections as bots.
SEBI_SSL_CTX = ssl.create_default_context()  # verifies certs, sends SNI — browser-like

SEBI_UA  = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
BSE_UA   = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'

SEBI_BASE = "https://www.sebi.gov.in"
BSE_BASE  = "https://www.bseindia.com"

# ─── SOURCES ────────────────────────────────────────────────────────────────────
# ─── BASE DOWNLOAD DIRECTORY ─────────────────────────────────────────────────
# All downloads go under one main folder on the Desktop.
# Structure: ~/Desktop/Repositories/<SourceType>/document.pdf
BASE_DOWNLOAD_DIR = os.path.expanduser("~/Desktop/Repositories")

def _dl(*parts):
    """Build a download folder path under BASE_DOWNLOAD_DIR.
    Each source gets its own sub-folder directly inside Repositories/.
    e.g. _dl('RHP') → ~/Desktop/Repositories/RHP/
    """
    return os.path.join(BASE_DOWNLOAD_DIR, *parts)

SOURCES = {
    # ── SEBI — Public Issues ──────────────────────────────────────────────────
    "RHP":             {"sid": "3", "ssid": "15", "smid": "11",  "folder": _dl("RHP"),             "kind": "sebi"},
    "DRHP":            {"sid": "3", "ssid": "15", "smid": "10",  "folder": _dl("DRHP"),            "kind": "sebi"},
    "RIGHTS_LOF":      {"sid": "3", "ssid": "16", "smid": "14",  "folder": _dl("Rights_LoF"),      "kind": "sebi"},
    # SEBI — InvIT Rights Issue
    "INVIT_RI_FINAL":  {"sid": "3", "ssid": "89", "smid": "124", "folder": _dl("InvIT_RI_Final"),  "kind": "sebi"},
    "INVIT_RI_DRAFT":  {"sid": "3", "ssid": "89", "smid": "127", "folder": _dl("InvIT_RI_Draft"),  "kind": "sebi"},
    # SEBI — InvIT Public Issue
    "INVIT_PUB_FINAL": {"sid": "3", "ssid": "55", "smid": "73",  "folder": _dl("InvIT_Pub_Final"), "kind": "sebi"},
    "INVIT_PUB_DRAFT": {"sid": "3", "ssid": "55", "smid": "66",  "folder": _dl("InvIT_Pub_Draft"), "kind": "sebi"},
    # SEBI — InvIT Private Issue
    "INVIT_PVT_FINAL": {"sid": "3", "ssid": "73", "smid": "76",  "folder": _dl("InvIT_Pvt_Final"), "kind": "sebi"},
    "INVIT_PVT_DRAFT": {"sid": "3", "ssid": "73", "smid": "121", "folder": _dl("InvIT_Pvt_Draft"), "kind": "sebi"},
    # SEBI — REIT
    "REIT_FINAL":      {"sid": "3", "ssid": "74", "smid": "83",  "folder": _dl("REIT_Final"),      "kind": "sebi"},
    "REIT_DRAFT":      {"sid": "3", "ssid": "74", "smid": "80",  "folder": _dl("REIT_Draft"),      "kind": "sebi"},
    # SEBI — Informal Guidance & Consultation Papers
    "SEBI_INFORMAL":   {"sid": "2", "ssid": "10", "smid": "0",  "folder": _dl("SEBI_Informal"),     "kind": "sebi"},
    "SEBI_CONSULT":    {"sid": "4", "ssid": "38", "smid": "35", "folder": _dl("SEBI_Consultation"),  "kind": "sebi"},
    # ── BSE ───────────────────────────────────────────────────────────────────
    "BSE_PLACEMENT":   {"folder": _dl("BSE_Placement"),   "kind": "bse"},
    "BSE_PRELIMINARY": {"folder": _dl("BSE_Preliminary"), "kind": "bse"},
    # ── CCI — Combination Orders (s.31) ───────────────────────────────────────
    "CCI_FORM1":       {"form_type": "I",   "folder": _dl("CCI_Form1"), "kind": "cci"},
    "CCI_FORM2":       {"form_type": "II",  "folder": _dl("CCI_Form2"), "kind": "cci"},
    "CCI_FORM3":       {"form_type": "III", "folder": _dl("CCI_Form3"), "kind": "cci"},
    # CCI — Combination (other endpoints)
    "CCI_GUN_JUMPING":  {"cci_combo_url": "orders-section43a_44",          "folder": _dl("CCI_Gun_Jumping"),  "kind": "cci_combo"},
    "CCI_APPROVED_MOD": {"cci_combo_url": "cases-approved-with-modification", "folder": _dl("CCI_Approved_Mod"), "kind": "cci_combo"},
    # CCI — Antitrust
    "CCI_ANTI_S26_1":  {"section_id": "6",  "folder": _dl("CCI_Antitrust_S26_1"), "kind": "cci_antitrust"},
    "CCI_ANTI_S26_2":  {"section_id": "7",  "folder": _dl("CCI_Antitrust_S26_2"), "kind": "cci_antitrust"},
    "CCI_ANTI_S26_6":  {"section_id": "8",  "folder": _dl("CCI_Antitrust_S26_6"), "kind": "cci_antitrust"},
    "CCI_ANTI_S26_7":  {"section_id": "9",  "folder": _dl("CCI_Antitrust_S26_7"), "kind": "cci_antitrust"},
    "CCI_ANTI_S27":    {"section_id": "10", "folder": _dl("CCI_Antitrust_S27"),   "kind": "cci_antitrust"},
    "CCI_ANTI_S33":    {"section_id": "11", "folder": _dl("CCI_Antitrust_S33"),   "kind": "cci_antitrust"},
    "CCI_ANTI_OTHER":  {"section_id": "12", "folder": _dl("CCI_Antitrust_Other"), "kind": "cci_antitrust"},
    # CCI — Green Channel Notices
    "CCI_GREEN":       {"folder": _dl("CCI_GreenChannel"), "kind": "cci_green"},
    # ── RBI — Master Directions & Circulars ───────────────────────────────────
    "RBI_MD":          {"rbi_path": "master-directions",  "folder": _dl("RBI_MasterDir"),    "kind": "rbi"},
    "RBI_MC":          {"rbi_path": "master-circulars",   "folder": _dl("RBI_MasterCirc"),   "kind": "rbi"},
    # RBI — Master Directions (entity-wise)
    "RBI_MD_COMM":    {"rbi_did": "403", "folder": _dl("RBI_MD_CommBanks"),  "kind": "rbi_md_entity"},
    "RBI_MD_SFB":     {"rbi_did": "404", "folder": _dl("RBI_MD_SFB"),        "kind": "rbi_md_entity"},
    "RBI_MD_PAY":     {"rbi_did": "405", "folder": _dl("RBI_MD_PayBanks"),   "kind": "rbi_md_entity"},
    "RBI_MD_LAB":     {"rbi_did": "406", "folder": _dl("RBI_MD_LocalArea"),  "kind": "rbi_md_entity"},
    "RBI_MD_RRB":     {"rbi_did": "407", "folder": _dl("RBI_MD_RRB"),        "kind": "rbi_md_entity"},
    "RBI_MD_UCB":     {"rbi_did": "408", "folder": _dl("RBI_MD_UCB"),        "kind": "rbi_md_entity"},
    "RBI_MD_RCB":     {"rbi_did": "409", "folder": _dl("RBI_MD_RCB"),        "kind": "rbi_md_entity"},
    "RBI_MD_AIFI":    {"rbi_did": "410", "folder": _dl("RBI_MD_AIFI"),       "kind": "rbi_md_entity"},
    "RBI_MD_NBFC":    {"rbi_did": "411", "folder": _dl("RBI_MD_NBFC"),       "kind": "rbi_md_entity"},
    # ── IRDAI ─────────────────────────────────────────────────────────────────
    "IRDAI_CIRC":      {"folder": _dl("IRDAI_Circulars"),    "kind": "irdai"},
    "IRDAI_REGS":      {"folder": _dl("IRDAI_Regulations"),  "kind": "irdai_regs"},
    # ── India INX ─────────────────────────────────────────────────────────────
    "INX_CIRC":        {"folder": _dl("INX_Circulars"),  "kind": "inx_circ"},
    "INX_ISSUER":      {"folder": _dl("INX_Issuer"),     "kind": "inx_issuer"},
    # ── Telangana RERA — Orders ───────────────────────────────────────────────
    "TG_RERA_ADJ":   {"tgrera_url": "https://rera.telangana.gov.in/384798wfybwev9fya62435-TG-RERA-skfjdgky483yunskljghfdgjh",
                       "folder": _dl("TG_RERA_Adjudication"), "kind": "tg_rera"},
    "TG_RERA_AUTH":  {"tgrera_url": "https://rera.telangana.gov.in/586784u3y5dsgfg-TG-RERA-45678jklshihnfgsfdg",
                       "folder": _dl("TG_RERA_Authority"),     "kind": "tg_rera"},
    "TG_RERA_SUO":   {"tgrera_url": "https://rera.telangana.gov.in/SUOMOTU-TG-RERA-15121976ORDERS",
                       "folder": _dl("TG_RERA_SuoMotu"),       "kind": "tg_rera"},
    # Telangana RERA — Circulars
    "TG_RERA_CIRC":  {"tgrera_url": "https://rera.telangana.gov.in/amavlnjoiu7532845972-TG-RERA-74698ijgsdfjgbi349529",
                       "folder": _dl("TG_RERA_Circulars"),     "kind": "tg_rera_circ"},
    # ── Tamil Nadu RERA ───────────────────────────────────────────────────────
    "TN_RERA":       {"folder": _dl("TN_RERA_Orders"),     "kind": "tn_rera"},
    # ── DTCP Karnataka ────────────────────────────────────────────────────────
    "DTCP_KA":       {"folder": _dl("DTCP_KA_Circulars"),  "kind": "dtcp_ka"},
    # ── Maharashtra RERA ──────────────────────────────────────────────────────
    "MAHA_RERA":     {"folder": _dl("MahaRERA_Circulars"), "kind": "maha_rera"},
    # ── Karnataka REAT & RERA ─────────────────────────────────────────────────
    "KA_REAT":       {"folder": _dl("KA_REAT_Orders"),  "kind": "ka_reat"},
    "KA_RERA":       {"folder": _dl("KA_RERA_Orders"),  "kind": "ka_rera"},
    # ── Haryana REAT ──────────────────────────────────────────────────────────
    "HR_REAT":       {"folder": _dl("HR_REAT_Judgements"), "kind": "hr_reat"},
    # ── Delhi REAT ────────────────────────────────────────────────────────────
    "DL_REAT":       {"folder": _dl("DL_REAT_Orders"),      "kind": "dl_reat"},
    # ── TRAI ──────────────────────────────────────────────────────────────────
    "TRAI_DIR":      {"trai_path": "directions",       "folder": _dl("TRAI_Directions"),      "kind": "trai"},
    "TRAI_REG":      {"trai_path": "regulations",      "folder": _dl("TRAI_Regulations"),     "kind": "trai"},
    "TRAI_REC":      {"trai_path": "recommendation",   "folder": _dl("TRAI_Recommendations"), "kind": "trai"},
    "TRAI_CON":      {"trai_path": "consultation",     "folder": _dl("TRAI_Consultation"),    "kind": "trai"},
    # ── CGST ──────────────────────────────────────────────────────────────────
    "CGST_CIRC":     {"folder": _dl("CGST_Circulars"), "kind": "cgst"},
    # ── IBBI / NCLT ───────────────────────────────────────────────────────────
    "IBBI_RES":      {"ibbi_title": "Resolution", "folder": _dl("IBBI_Resolution"), "kind": "ibbi_nclt"},
    "IBBI_ADM":      {"ibbi_title": "Admission",  "folder": _dl("IBBI_Admission"),  "kind": "ibbi_nclt"},
    # ── EU Commission — Competition Decisions ─────────────────────────────────
    "EU_MERGER":     {"eu_instrument": "M",             "eu_min_date": "2004-05-01", "folder": _dl("EU_Mergers"),          "kind": "eu_comp"},
    "EU_ANTITRUST":  {"eu_instrument": "AT",            "eu_min_date": None,         "folder": _dl("EU_Antitrust"),        "kind": "eu_comp"},
    "EU_DMA":        {"eu_instrument": "InstrumentDMA", "eu_min_date": None,         "folder": _dl("EU_DMA"),              "kind": "eu_comp"},
    "EU_FS":         {"eu_instrument": "InstrumentFS",  "eu_min_date": None,         "folder": _dl("EU_ForeignSubsidies"), "kind": "eu_comp"},
    # ── EPO — Board of Appeal Decisions ───────────────────────────────────────
    "EPO_BOA":        {"folder": _dl("EPO_BOA_Decisions"), "kind": "epo_boa"},
    # ── EDPB — Consistency Findings & Guidance ────────────────────────────────
    "EDPB_BINDING":   {"edpb_url": "https://www.edpb.europa.eu/our-work-tools/consistency-findings/binding-decisions_en",              "folder": _dl("EDPB_Binding"),    "kind": "edpb", "no_month_filter": True},
    "EDPB_OPINIONS":  {"edpb_url": "https://www.edpb.europa.eu/our-work-tools/consistency-findings/opinions_en",                       "folder": _dl("EDPB_Opinions"),   "kind": "edpb"},
    "EDPB_GUIDELINES":{"edpb_url": "https://www.edpb.europa.eu/our-work-tools/general-guidance/guidelines-recommendations-best-practices_en", "folder": _dl("EDPB_Guidelines"), "kind": "edpb"},
    # ── UAE ───────────────────────────────────────────────────────────────────
    "ADGM_ORDERS":      {"folder": _dl("ADGM_Judgments"),      "kind": "adgm"},
    "DIFC_CA_ORDERS":   {"folder": _dl("DIFC_CA_Judgments"),   "kind": "difc_ca"},
    "MOHRE_LAWS":       {"mohre_path": "/en/laws-and-regulations/laws",                      "mohre_cat": "1557", "folder": _dl("MOHRE_Laws"),        "kind": "mohre", "no_month_filter": True},
    "MOHRE_RESOLUTIONS":{"mohre_path": "/en/laws-and-regulations/resolutions-and-circulars", "mohre_cat": "1558", "folder": _dl("MOHRE_Resolutions"), "kind": "mohre", "no_month_filter": True},
    # ── UK Tribunals & Competition ────────────────────────────────────────────
    "UK_ET_ENG":        {"govuk_base": "employment-tribunal-decisions",
                         "govuk_params": "tribunal_decision_country%5B%5D=england-and-wales&tribunal_decision_categories%5B%5D=unfair-dismissal",
                         "govuk_date_param": "tribunal_decision_decision_date",
                         "folder": _dl("UK_ET_England"),   "kind": "govuk_finder"},
    "UK_AAC":           {"govuk_base": "administrative-appeals-tribunal-decisions",
                         "govuk_params": "",
                         "govuk_date_param": "tribunal_decision_decision_date",
                         "folder": _dl("UK_AAC"),          "kind": "govuk_finder"},
    "UK_CAT":           {"folder": _dl("UK_CAT_Judgments"),                            "kind": "uk_cat"},
    "UK_CMA_MERGERS":   {"govuk_base": "cma-cases",
                         "govuk_params": "case_type%5B%5D=mergers",
                         "govuk_date_param": "closed_date",
                         "govuk_final_only": True,
                         "govuk_fallback_months": 12,
                         "folder": _dl("UK_CMA_Mergers"),  "kind": "govuk_finder"},
    "UK_CMA_NONMERGER": {"govuk_base": "cma-cases",
                         "govuk_params": "case_type%5B%5D=ca98-and-civil-cartels&case_type%5B%5D=competition-disqualification&case_type%5B%5D=consumer-enforcement&case_type%5B%5D=criminal-cartels&case_type%5B%5D=digital-markets-unit&case_type%5B%5D=information-and-advice-to-government&case_type%5B%5D=markets&case_type%5B%5D=oim-project&case_type%5B%5D=regulatory-references-and-appeals&case_type%5B%5D=review-of-orders-and-undertakings&case_type%5B%5D=sau-referral",
                         "govuk_date_param": "closed_date",
                         "govuk_final_only": True,
                         "govuk_fallback_months": 24,
                         "folder": _dl("UK_CMA_NonMerger"), "kind": "govuk_finder"},
    "UK_EAT":           {"govuk_base": "employment-appeal-tribunal-decisions",
                         "govuk_params": "",
                         "govuk_date_param": "tribunal_decision_decision_date",
                         "folder": _dl("UK_EAT"),          "kind": "govuk_finder"},
    "UK_ET_SCOT":       {"govuk_base": "employment-tribunal-decisions",
                         "govuk_params": "tribunal_decision_country%5B%5D=scotland",
                         "govuk_date_param": "tribunal_decision_decision_date",
                         "folder": _dl("UK_ET_Scotland"),  "kind": "govuk_finder"},
    "UK_UTIAC":         {"folder": _dl("UK_UTIAC"),                                    "kind": "uk_utiac"},
    "UK_LAND":          {"na_court": "ukut/lc", "folder": _dl("UK_Land_Chamber"),      "kind": "national_archives"},
    "UK_TAX_CHANCERY":  {"govuk_base": "tax-and-chancery-tribunal-decisions",
                         "govuk_params": "",
                         "govuk_date_param": "tribunal_decision_decision_date",
                         "folder": _dl("UK_TaxChancery"),  "kind": "govuk_finder"},
    "UK_TAX_FTT":       {"na_court": "ukftt/tc", "folder": _dl("UK_Tax_FTT"),          "kind": "national_archives"},
    # ── SEBI — Circulars & Final Offer Documents ─────────────────────────────
    "SEBI_CIRCULARS":  {"sid": "1", "ssid": "7", "smid": "0",  "folder": _dl("SEBI_Circulars"),   "kind": "sebi"},
    "SEBI_FINAL_OFFER":{"sid": "3", "ssid": "15", "smid": "12", "folder": _dl("SEBI_FinalOffer"), "kind": "sebi"},
    # ── SEBI — Regulation Pages (Related Articles tracker) ────────────────────
    "SEBI_LODR":       {"sebi_reg_url": "https://www.sebi.gov.in/legal/regulations/feb-2023/securities-and-exchange-board-of-india-listing-obligations-and-disclosure-requirements-regulations-2015-last-amended-on-february-07-2023-_69224.html",
                        "sebi_entry_id": "69224", "folder": _dl("SEBI_LODR"),      "kind": "sebi_reg", "no_month_filter": True},
    "SEBI_ICDR":       {"sebi_reg_url": "https://www.sebi.gov.in/legal/regulations/may-2024/securities-and-exchange-board-of-india-issue-of-capital-and-disclosure-requirements-regulations-2018-last-amended-on-may-17-2024-_80421.html",
                        "sebi_entry_id": "80421", "folder": _dl("SEBI_ICDR"),      "kind": "sebi_reg", "no_month_filter": True},
    "SEBI_TAKEOVER":   {"sebi_reg_url": "https://www.sebi.gov.in/legal/regulations/may-2024/securities-and-exchange-board-of-india-substantial-acquisition-of-shares-and-takeovers-regulations-2011-last-amended-on-may-17-2024-_69218.html",
                        "sebi_entry_id": "69218", "folder": _dl("SEBI_Takeover"), "kind": "sebi_reg", "no_month_filter": True},
    "SEBI_AIF":        {"sebi_reg_url": "https://www.sebi.gov.in/legal/regulations/aug-2024/securities-and-exchange-board-of-india-alternative-investment-funds-regulations-2012-last-amended-on-august-06-2024-_85618.html",
                        "sebi_entry_id": "85618", "folder": _dl("SEBI_AIF"),       "kind": "sebi_reg", "no_month_filter": True},
    # ── RBI — FEMA / FDI ─────────────────────────────────────────────────────
    "RBI_FEMA_DIR":    {"rbi_fema_fn": "5", "rbi_fema_fnn": "2764", "folder": _dl("RBI_FEMA_Directions"),    "kind": "rbi_fema", "no_month_filter": True},
    "RBI_FEMA_CIRC":   {"rbi_fema_fn": "5", "rbi_fema_fnn": "2763", "folder": _dl("RBI_FEMA_Circulars"),     "kind": "rbi_fema", "no_month_filter": True},
    "RBI_FEMA_NOTIF":  {"rbi_fema_fn": "5", "rbi_fema_fnn": None,   "folder": _dl("RBI_FEMA_Notifications"), "kind": "rbi_fema", "no_month_filter": True},
}

# ─── ACTIVE MONTH ────────────────────────────────────────────────────────────────
# Only fetch one month at a time for quality over quantity
def _month_range(year, month):
    """Return (first_day_iso, last_day_iso, first_day_ddmmyyyy, last_day_ddmmyyyy) for a given month."""
    first = f"{year:04d}-{month:02d}-01"
    last_day = calendar.monthrange(year, month)[1]
    last = f"{year:04d}-{month:02d}-{last_day:02d}"
    first_dd = f"01/{month:02d}/{year:04d}"
    last_dd = f"{last_day:02d}/{month:02d}/{year:04d}"
    return first, last, first_dd, last_dd

_now = datetime.now()
ACTIVE_MONTH = {"year": _now.year, "month": _now.month}  # e.g. {"year": 2026, "month": 2}
# Active fetch range — may span multiple months when user sets a custom range
_now_from, _now_to, _, _ = _month_range(_now.year, _now.month)
ACTIVE_RANGE = {"from_iso": _now_from, "to_iso": _now_to, "is_custom": False}

# ─── CACHE ───────────────────────────────────────────────────────────────────────
def _empty_cache():
    return {"data": [], "fetching": False, "error": None, "total": 0, "pages_done": 0, "fetch_started_at": 0}

cache = {k: _empty_cache() for k in SOURCES}
download_progress = {}
_download_sem = threading.Semaphore(40)  # global cap; adaptive per-source workers below

# ─── HTTP helpers ────────────────────────────────────────────────────────────
def _urlopen_retry(req, timeout=60, retries=2, ctx=None):
    """urlopen with retries for transient timeouts."""
    last_exc = None
    for attempt in range(retries + 1):
        try:
            return urllib.request.urlopen(req, timeout=timeout, context=ctx or SSL_CTX)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_exc = e
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            raise last_exc

# ─── PARALLEL SCRAPER RUNNER ─────────────────────────────────────────────────
_scrape_generation = 0  # bumped on every month switch; runner stops if stale
SCRAPER_TIMEOUT = 1800  # max 30 min per scraper — allows wide date-range full pagination
SCRAPER_WORKERS = len(SOURCES)  # one worker per source — all sources run in parallel (pure I/O-bound)

def _run_all_scrapers(from_iso, to_iso, from_dd, to_dd, generation):
    """Run all scrapers in parallel using a thread pool.  Stops early if generation is stale.
    Non-SEBI sources run in parallel.  SEBI listing and regulation sources run
    sequentially in dedicated threads to avoid WAF rate-limiting.
    """
    global _scrape_generation

    def _scrape_one(dtype):
        """Execute the appropriate scraper for one non-SEBI source type."""
        if _scrape_generation != generation:
            return
        cfg = SOURCES[dtype]
        kind = cfg.get('kind', '')
        try:
            rec = SCRAPER_DISPATCH.get(kind)
            if rec:
                fn, _ = rec
                fn(dtype, from_iso, to_iso)
            else:
                cache[dtype].update({"fetching": False})
        except Exception as e:
            print(f"[RUNNER] {dtype} raised {e}")
            cache[dtype].update({"error": str(e), "fetching": False})

    def _scrape_bse():
        """Run the shared BSE scraper (covers BSE_PLACEMENT + BSE_PRELIMINARY)."""
        if _scrape_generation != generation:
            return
        try:
            scrape_bse_qip(from_iso, to_iso)
        except Exception as e:
            print(f"[RUNNER] BSE raised {e}")
            for bt in ["BSE_PLACEMENT", "BSE_PRELIMINARY"]:
                if cache[bt]["fetching"]:
                    cache[bt].update({"error": str(e), "fetching": False})

    def _run_sebi_listing_sequential():
        """Run all SEBI listing sources one-by-one to avoid WAF rate-limiting."""
        sebi_types = [dt for dt in SOURCES if SOURCES[dt].get('kind') == 'sebi']
        consec_fail = 0  # consecutive WAF-blocked failures
        for i, dtype in enumerate(sebi_types):
            if _scrape_generation != generation:
                break
            # If WAF blocked 3+ sources in a row, wait 5 min for IP release
            if consec_fail >= 3:
                print(f"[RUNNER] WAF block detected ({consec_fail} consecutive failures), cooling down 300s...")
                time.sleep(300)
                consec_fail = 0
            # Pre-flight WAF check — if blocked, wait before even trying
            working_ip = _sebi_waf_ok()
            if not working_ip:
                print(f"[RUNNER] WAF pre-check failed before {dtype}, waiting 120s...")
                time.sleep(120)
                working_ip = _sebi_waf_ok()
                if not working_ip:
                    print(f"[RUNNER] WAF still blocking, extended wait 300s...")
                    time.sleep(300)
                    working_ip = _sebi_waf_ok()  # one more try
            ok = True
            try:
                scrape_sebi(dtype, from_dd, to_dd, _resolve_ip=working_ip or None)
            except Exception as e:
                ok = False
                print(f"[RUNNER] {dtype} raised {e}")
                cache[dtype].update({"error": str(e), "fetching": False})
            if ok:
                consec_fail = 0
            else:
                consec_fail += 1
            # Longer cooldown after failures to let WAF reset
            if i < len(sebi_types) - 1:
                gap = 20 if ok else 45
                time.sleep(gap)

    def _run_sebi_regs_sequential():
        """Run all sebi_reg sources one-by-one after listing sources finish."""
        sebi_reg_types = [dt for dt in SOURCES if SOURCES[dt].get('kind') == 'sebi_reg']
        consec_fail = 0
        for i, dtype in enumerate(sebi_reg_types):
            if _scrape_generation != generation:
                break
            if consec_fail >= 3:
                print(f"[RUNNER] WAF block detected ({consec_fail} consecutive failures), cooling down 300s...")
                time.sleep(300)
                consec_fail = 0
            working_ip = _sebi_waf_ok()
            if not working_ip:
                print(f"[RUNNER] WAF pre-check failed before {dtype}, waiting 120s...")
                time.sleep(120)
                working_ip = _sebi_waf_ok()
                if not working_ip:
                    print(f"[RUNNER] WAF still blocking, extended wait 300s...")
                    time.sleep(300)
                    working_ip = _sebi_waf_ok()
            ok = True
            try:
                scrape_sebi_reg(dtype, from_iso, to_iso, _resolve_ip=working_ip or None)
            except Exception as e:
                ok = False
                print(f"[RUNNER] {dtype} raised {e}")
                cache[dtype].update({"error": str(e), "fetching": False})
            if ok:
                consec_fail = 0
            else:
                consec_fail += 1
            if i < len(sebi_reg_types) - 1:
                gap = 20 if ok else 45
                time.sleep(gap)

    def _run_all_sebi():
        """Run listing then regulation sources — all sequential, zero overlap."""
        _run_sebi_listing_sequential()
        time.sleep(5)  # breathing room before regulation sources
        _run_sebi_regs_sequential()

    with ThreadPoolExecutor(max_workers=SCRAPER_WORKERS) as pool:
        futures = {}
        # Submit BSE as one combined task
        futures[pool.submit(_scrape_bse)] = "BSE"
        # Submit ALL SEBI sources (listing + reg) as one sequential chain
        futures[pool.submit(_run_all_sebi)] = "SEBI_ALL"
        # Submit every non-BSE, non-SEBI source in parallel
        for dtype in SOURCES:
            kind = SOURCES[dtype].get('kind', '')
            if kind in ('bse', 'sebi', 'sebi_reg'):
                continue
            if _scrape_generation != generation:
                break
            futures[pool.submit(_scrape_one, dtype)] = dtype

        for f in as_completed(futures):
            dtype = futures[f]
            try:
                f.result(timeout=SCRAPER_TIMEOUT)
            except TimeoutError:
                print(f"[RUNNER] {dtype} timed out after {SCRAPER_TIMEOUT}s")
                if dtype in ("BSE", "SEBI_ALL"):
                    pass  # these are group tasks; individual sources handle their own errors
                elif dtype in cache and cache[dtype]["fetching"]:
                    cache[dtype].update({"error": f"Timeout after {SCRAPER_TIMEOUT}s", "fetching": False})
            except Exception as e:
                print(f"[RUNNER] {dtype} future error: {e}")

    if _scrape_generation == generation:
        print(f"[RUNNER] generation {generation} complete — all sources done")

# ─── WATCHDOG — reset stuck scrapers ─────────────────────────────────────────
SCRAPE_TIMEOUT = 600  # seconds before a scraper is considered stuck

def _watchdog():
    """Run every 30s; if a source has been 'fetching' for > SCRAPE_TIMEOUT seconds, reset it."""
    while True:
        time.sleep(30)
        now = time.time()
        for k, c in cache.items():
            if c["fetching"] and c["fetch_started_at"] > 0:
                elapsed = now - c["fetch_started_at"]
                if elapsed > SCRAPE_TIMEOUT:
                    has_data = len(c.get("data", [])) > 0
                    if has_data:
                        # Source has partial data — keep data, mark done with warning
                        print(f"[WATCHDOG] {k} stuck for {elapsed:.0f}s but has {len(c['data'])} docs — keeping partial data")
                        c.update({"fetching": False, "error": None, "fetch_started_at": 0})
                    else:
                        print(f"[WATCHDOG] {k} stuck for {elapsed:.0f}s — resetting")
                        c.update({"fetching": False, "error": f"Timeout after {int(elapsed)}s", "fetch_started_at": 0})

# ─── DATE FORMAT HELPER ─────────────────────────────────────────────────────────
def _fmt_date(date_str):
    """Normalize any date string to 'DD Mon YYYY' (e.g. '18 Feb 2026')."""
    for fmt in ("%d/%m/%Y", "%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%d %b %Y")
        except Exception:
            continue
    return date_str  # fallback: return as-is


def _clean_text(raw):
    """Strip HTML tags, decode entities, collapse whitespace → clean plain text."""
    if not raw:
        return ''
    # Decode HTML entities first (e.g. &amp; &nbsp; &rsquo;)
    text = html.unescape(str(raw))
    # Remove all HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Collapse multiple whitespace / newlines into single space
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _extract_informal_company(title):
    """Extract company name from SEBI Informal Guidance title patterns."""
    # "In the matter of X under SEBI ..." / "in the matter of X with respect ..."
    m = re.search(r'[Ii]n\s+the\s+matter\s+of\s+(.+?)\s+(?:under\s+SEBI|with\s+respect)', title)
    if m:
        return m.group(1).strip().rstrip('.')
    # "in the matter of X Ltd." at end or mid-sentence
    m = re.search(r'[Ii]n\s+the\s+matter\s+of\s+(.+?(?:Limited|Ltd)\.?)', title)
    if m:
        return m.group(1).strip().rstrip('.')
    # "... received from X seeking ..." / "... received from X with respect ..."
    # / "... received from X in relation ..." / "... received from X on ..."
    m = re.search(r'received\s+from\s+(.+?)\s+(?:seeking|with\s+respect|in\s+relation|on\s+applicability)', title, re.IGNORECASE)
    if m:
        return m.group(1).strip().rstrip(',').rstrip('.')
    # "received from X," or "received from X (alias),"
    m = re.search(r'received\s+from\s+(.+?)\s*[,]', title, re.IGNORECASE)
    if m:
        return m.group(1).strip().rstrip('.')
    # Last resort: "by CompanyName Limited" (skip "by way of")
    m = re.search(r'\bby\s+(?!way\s+of\b)(.+?(?:Limited|Ltd|Bank|Trust|Inc|Fund|Corporation)\.?)\b', title, re.IGNORECASE)
    if m:
        return m.group(1).strip().rstrip('.')
    return ''  # No company found


# ════════════════════════════════════════════════════════════════════════════════
#  HTTP HELPERS
# ════════════════════════════════════════════════════════════════════════════════

def make_sebi_opener():
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=SEBI_SSL_CTX),
        urllib.request.HTTPCookieProcessor(cj))
    opener.addheaders = [
        ('User-Agent', SEBI_UA),
        ('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'),
        ('Accept-Language', 'en-US,en;q=0.9'),
        ('Accept-Encoding', 'gzip, deflate, br'),
        ('Connection', 'keep-alive')]
    return opener


def _sebi_resolve_ips():
    """Resolve www.sebi.gov.in to its backend IPs via DNS."""
    try:
        import socket
        return list({addr[4][0] for addr in socket.getaddrinfo('www.sebi.gov.in', 443, socket.AF_INET)})
    except Exception:
        return []

def _sebi_waf_ok():
    """Quick GET check on a Struts endpoint — returns working IP or empty string.
    Tests the actual listing URL (not just homepage) since WAF may block dynamic paths."""
    test_url = 'https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=3&ssid=15&smid=0'
    for ip in _sebi_resolve_ips():
        try:
            r = subprocess.run(
                ['curl', '-s', '--max-time', '8', '--connect-timeout', '6',
                 '--tlsv1.2', '--tls-max', '1.2',
                 '-o', '/dev/null', '-w', '%{http_code}',
                 '--resolve', f'www.sebi.gov.in:443:{ip}',
                 test_url],
                capture_output=True, timeout=15)
            code = r.stdout.decode().strip()
            if r.returncode == 0 and code.startswith(('2', '3')):
                return ip
        except Exception:
            continue
    return ''


def _sebi_curl(url, post_data=None, cookie_file=None, timeout=30, referer=None, resolve_ip=None):
    """Fetch a SEBI URL via curl subprocess — bypasses Python urllib's HTTP/1.1
    TLS fingerprint that triggers SEBI's WAF (Connection reset by peer).
    curl uses HTTP/2 and has a browser-like TLS fingerprint.
    If resolve_ip is given, pin DNS to that IP. Otherwise try all SEBI IPs."""
    ips = [resolve_ip] if resolve_ip else _sebi_resolve_ips()
    if not ips:
        ips = ['']  # fall back to normal DNS
    last_err = None
    for ip in ips:
        cmd = ['curl', '-s', '--compressed', '-L',
               '--tlsv1.2', '--tls-max', '1.2', '--http2',
               '--connect-timeout', str(min(timeout, 15)),
               '--max-time', str(timeout)]
        if ip:
            cmd.extend(['--resolve', f'www.sebi.gov.in:443:{ip}'])
        if cookie_file:
            cmd.extend(['-b', cookie_file, '-c', cookie_file])
        cmd.extend([
            '-H', f'User-Agent: {SEBI_UA}',
            '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            '-H', 'Accept-Language: en-US,en;q=0.9',
        ])
        if referer:
            cmd.extend(['-H', f'Referer: {referer}'])
        if post_data:
            cmd.extend(['-H', 'Content-Type: application/x-www-form-urlencoded', '-d', post_data])
        cmd.append(url)
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=timeout + 15)
            if r.returncode == 0:
                body = r.stdout.decode('utf-8', 'ignore')
                if body:
                    return body
                last_err = urllib.error.URLError("curl returned empty response")
            else:
                last_err = urllib.error.URLError(f"curl error (rc={r.returncode}): {r.stderr.decode('utf-8','ignore')[:200]}")
        except Exception as e:
            last_err = e
    raise last_err


def fetch_simple(url, ua=SEBI_UA, retries=3, timeout=25):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': ua,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            })
            with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
                return r.read().decode('utf-8', errors='ignore')
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(3.0)
            else:
                raise


def _extract_total(html):
    m = re.search(r'(\d+)\s+to\s+\d+\s+of\s+([\d,]+)\s+records', html)
    return int(m.group(2).replace(',', '')) if m else 0


# ════════════════════════════════════════════════════════════════════════════════
#  SEBI SCRAPING
# ════════════════════════════════════════════════════════════════════════════════

def sebi_fetch_html(smid, sid='3', ssid='15'):
    """Fetch latest SEBI listing (no date filter) — single-page, no session required."""
    list_url = f"{SEBI_BASE}/sebiweb/home/HomeAction.do?doListing=yes&sid={sid}&ssid={ssid}&smid={smid}"
    return _sebi_curl(list_url)


def parse_sebi_listing(html, doc_type):
    """Parse SEBI GridView HTML (unclosed <td> for title cell)."""
    docs, total = [], _extract_total(html)
    rows = re.findall(r"<tr[^>]*role=['\"]row['\"][^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE)
    for row in rows:
        dm = re.search(r'<td[^>]*>\s*([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})\s*</td>', row, re.IGNORECASE)
        if not dm:
            continue
        date_text = dm.group(1).strip()
        lm = re.search(r'href=["\']([^"\']+\.html)["\'][^>]*title=["\']([^"\']+)["\']', row, re.IGNORECASE)
        if not lm:
            lm = re.search(r'title=["\']([^"\']+)["\'][^>]*href=["\']([^"\']+\.html)["\']', row, re.IGNORECASE)
            if lm:
                title, href = lm.group(1).strip(), lm.group(2).strip()
            else:
                continue
        else:
            href, title = lm.group(1).strip(), lm.group(2).strip()
        if not href.startswith('http'):
            href = SEBI_BASE + href
        try:
            date_iso = datetime.strptime(date_text, "%b %d, %Y").strftime("%Y-%m-%d")
        except Exception:
            date_iso = ""
        doc_id = href.split('_')[-1].replace('.html', '').replace('.HTML', '') if '_' in href else re.sub(r'\W+', '_', href[-20:])
        # Clean trailing HTML artifacts from title (e.g. '<a href=')
        title = re.sub(r'<[^>]*$', '', title).strip().rstrip('.')
        title = _clean_text(title) if '<' in title else title
        # Extract company name based on document type
        if doc_type == 'SEBI_CONSULT':
            company = ''  # Consultation papers have no associated company
        elif doc_type == 'SEBI_INFORMAL':
            company = _extract_informal_company(title)
        else:
            company = re.sub(
                r'\s*[-–]?\s*(?:U?DRHP|RHP|'
                r'[Aa]ddendum\s+(?:to\s+(?:D?RHP|U?DRHP|LOF|LoF)|cum\s+Corrig\w*)|'
                r'[Cc]orrigendum(?:\s+to\s+(?:D?RHP|U?DRHP|LOF|LoF))?|'
                r'Draft\s+(?:Red\s+Herring|Offer|Letter)|'
                r'Final\s+(?:Offer|Letter)|'
                r'Offer\s+Document|Letter\s+of\s+Offer|'
                r'LOF|LoF)\b.*$',
                '', title, flags=re.IGNORECASE
            ).strip().rstrip('-').rstrip('–').strip()
        docs.append({"date": _fmt_date(date_text), "date_iso": date_iso, "title": title, "company": company,
                     "page_url": href, "pdf_url": "", "type": doc_type, "id": doc_id})
    return docs, total


def get_sebi_pdf_url(page_url, retries=3):
    """Extract PDF URL from SEBI document detail page — 4 fallback patterns."""
    for attempt in range(retries):
        try:
            html = _sebi_curl(page_url)
            m = re.search(r'[?&]file=(https?://[^\s&\'"<>]+\.(?:pdf|PDF))', html, re.IGNORECASE)
            if m: return m.group(1)
            m = re.search(r"<iframe[^>]+src=['\"]([^'\"]*sebi_data[^'\"]*\.(?:pdf|PDF))['\"]", html, re.IGNORECASE)
            if m:
                s = m.group(1)
                return s if s.startswith('http') else SEBI_BASE + '/' + s.lstrip('/')
            m = re.search(r"<iframe[^>]+src=['\"]([^'\"]*\.(?:pdf|PDF))['\"][^>]*>", html, re.IGNORECASE)
            if m:
                s = m.group(1)
                fm = re.search(r'file=(https?://[^\s&\'"<>]+)', s, re.IGNORECASE)
                if fm: return fm.group(1)
                return s if s.startswith('http') else SEBI_BASE + '/' + s.lstrip('/')
            m = re.search(r'href=["\']([^"\']*sebi_data[^"\']*\.(?:pdf|PDF))["\']', html, re.IGNORECASE)
            if m:
                p = m.group(1)
                return p if p.startswith('http') else SEBI_BASE + p
            return None
        except Exception:
            if attempt < retries - 1:
                time.sleep(3.0)
    return None


def scrape_sebi(doc_type, from_date=None, to_date=None, _resolve_ip=None):
    """Background thread — fetch SEBI listing for any SEBI source, paginating through all pages."""
    src = SOURCES[doc_type]
    smid = src["smid"]
    sid  = src.get("sid", "3")
    ssid = src.get("ssid", "15")
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    print(f"[{doc_type}] Fetching {'{'+from_date+' to '+to_date+'}' if from_date else '(latest)'}")

    # Pre-compute ISO date range for local filtering
    fd_iso = td_iso = None
    if from_date and to_date:
        try:
            fd_iso = datetime.strptime(from_date, "%d/%m/%Y").strftime("%Y-%m-%d")
            td_iso = datetime.strptime(to_date,   "%d/%m/%Y").strftime("%Y-%m-%d")
        except Exception:
            pass

    last_err = None
    for attempt in range(6):
      cfile = None
      try:
        # Pin all session requests to one working SEBI backend IP
        resolve_ip = _resolve_ip
        if from_date and to_date:
            # Session-based pagination using SEBI's AJAX endpoint.
            # SEBI renders page 1 via a full-page POST to HomeAction.do, then
            # pages 2+ via AJAX POST to getnewslistinfo.jsp with `doDirect=page_num`
            # (0-indexed: 1=page2, 2=page3, ...) — ALL requests share one opener.
            list_url = f"{SEBI_BASE}/sebiweb/home/HomeAction.do?doListing=yes&sid={sid}&ssid={ssid}&smid={smid}"
            base_url = f"{SEBI_BASE}/sebiweb/home/HomeAction.do"
            ajax_url = f"{SEBI_BASE}/sebiweb/ajax/home/getnewslistinfo.jsp"

            cfile = tempfile.mktemp(suffix='.cookies')
            # Establish session and obtain CSRF token (via curl to bypass WAF)
            init_html = _sebi_curl(list_url, cookie_file=cfile, resolve_ip=resolve_ip)
            time.sleep(2)  # small delay to look more human
            tok_m = re.search(
                r'name=["\']org\.apache\.struts\.taglib\.html\.TOKEN["\'][^>]*value=["\']([^"\']+)["\']',
                init_html)
            token = tok_m.group(1) if tok_m else ''

            all_docs = []
            seen_ids = set()
            total_on_server = None
            pages_done = 0
            MAX_PAGES = 300  # safety cap (~7500 docs)

            for page_num in range(MAX_PAGES):
                # Per-page retry — transient timeouts shouldn't restart the full session
                html = None
                for _pr in range(3):
                    try:
                        if page_num == 0:
                            # Page 1: full POST to HomeAction.do
                            post_str = urllib.parse.urlencode({
                                'doListing': 'yes', 'sid': sid, 'ssid': ssid, 'smid': smid,
                                'fromDate': from_date, 'toDate': to_date, 'searchOpt': 'date',
                                'org.apache.struts.taglib.html.TOKEN': token,
                                'nextValue': '1',
                            })
                            html = _sebi_curl(base_url, post_data=post_str, cookie_file=cfile, referer=list_url, resolve_ip=resolve_ip)
                        else:
                            # Pages 2+: AJAX POST — nextValue and doDirect both equal page_num
                            ajax_str = urllib.parse.urlencode({
                                'nextValue': str(page_num), 'next': 'n', 'search': '',
                                'fromDate': from_date, 'toDate': to_date,
                                'fromYear': '', 'toYear': '', 'deptId': '',
                                'sid': sid, 'ssid': ssid, 'smid': smid,
                                'ssidhidden': ssid, 'intmid': '-1',
                                'sText': '', 'ssText': '', 'smText': '',
                                'doDirect': str(page_num),
                            })
                            ajax_resp = _sebi_curl(ajax_url, post_data=ajax_str, cookie_file=cfile, referer=base_url, resolve_ip=resolve_ip)
                            # AJAX response: div1 (results + pagination) #@# div2 (breadcrumbs)
                            parts = ajax_resp.split('#@#')
                            html = parts[0] if parts else ajax_resp
                        break  # page fetch succeeded
                    except Exception as _pe:
                        if _pr < 2:
                            time.sleep(5 * (_pr + 1))
                        else:
                            raise  # propagate to outer attempt loop

                page_docs, page_total = parse_sebi_listing(html, doc_type)
                pages_done = page_num + 1

                if total_on_server is None and page_total:
                    total_on_server = page_total

                new_docs = [d for d in page_docs if d['id'] not in seen_ids]
                if not new_docs:
                    break  # no new data: pagination complete

                seen_ids.update(d['id'] for d in new_docs)
                all_docs.extend(new_docs)

                print(f"[{doc_type}] Page {page_num+1}: {len(new_docs)} new, "
                      f"{len(all_docs)}/{total_on_server or '?'} total")

                # Early-exit: SEBI returns results newest-first. Once the oldest doc
                # on this page is before our from_date, all further pages are older too.
                if fd_iso:
                    oldest_iso = min((d['date_iso'] for d in new_docs if d['date_iso']), default='')
                    if oldest_iso and oldest_iso < fd_iso:
                        break

                # Stop when all server docs collected or partial page (last page)
                if (total_on_server and len(all_docs) >= total_on_server) or len(page_docs) < 25:
                    break

                time.sleep(3.0)  # inter-page delay to avoid WAF trigger

            docs = all_docs
            total = total_on_server or len(docs)
        else:
            # Single fetch for latest docs (no date filter)
            html = sebi_fetch_html(smid, sid=sid, ssid=ssid)
            docs, total = parse_sebi_listing(html, doc_type)
            pages_done = 1

        # Apply date filter locally (catches any server-side boundary quirks)
        if fd_iso and td_iso:
            docs = [d for d in docs if d["date_iso"] and fd_iso <= d["date_iso"] <= td_iso]

        # Preserve cached pdf_url values
        old = {d["id"]: d.get("pdf_url") for d in cache[doc_type]["data"]}
        for d in docs:
            if old.get(d["id"]):
                d["pdf_url"] = old[d["id"]]

        # Bulk-resolve PDF URLs for docs that don't have one yet
        # DISABLED during main scrape to reduce request volume and avoid SEBI WAF block.
        # PDF URLs are resolved on-demand via /api/pdf_url when users click download.
        # unresolved = [d for d in docs if not d.get("pdf_url")]
        # if unresolved:
        #     print(f"[{doc_type}] Resolving {len(unresolved)} PDF URLs...")
        #     for ui, doc in enumerate(unresolved):
        #         try:
        #             url = get_sebi_pdf_url(doc["page_url"])
        #             if url:
        #                 doc["pdf_url"] = url
        #         except Exception:
        #             pass
        #         if ui < len(unresolved) - 1:
        #             time.sleep(2)
        #     resolved = sum(1 for d in unresolved if d.get("pdf_url"))
        #     print(f"[{doc_type}] Resolved {resolved}/{len(unresolved)} PDF URLs")

        cache[doc_type].update({"data": docs, "total": total, "pages_done": pages_done, "fetching": False})
        print(f"[{doc_type}] Done — {len(docs)} docs across {pages_done} page(s) (server total: {total})")
        return  # success
      except Exception as e:
        last_err = e
        if attempt < 5:
            # WAF SSL blocks (rc=35) need longer waits than generic errors
            is_waf = 'rc=35' in str(e) or 'reset by peer' in str(e).lower()
            wait = (40 if is_waf else 20) * (attempt + 1)
            print(f"[{doc_type}] Attempt {attempt+1}/6 failed ({e}), retrying in {wait}s...")
            time.sleep(wait)
      finally:
        if cfile:
            try:
                os.unlink(cfile)
            except OSError:
                pass
    cache[doc_type].update({"error": str(last_err), "fetching": False})
    print(f"[{doc_type}] Failed after 6 attempts: {last_err}")


# ════════════════════════════════════════════════════════════════════════════════
#  BSE QIP SCRAPING
# ════════════════════════════════════════════════════════════════════════════════

def parse_bse_qip_page(html):
    """
    Parse BSE QIP GridView HTML. Each data row has:
      <td class="TTRow_left">Company Name</td>
      <td><a href="/corporates/download/.../QIP Open/PPD_...pdf">DD/MM/YYYY</a></td>  ← Preliminary
      <td><a href="/corporates/download/.../QIP Open/Placement...pdf">DD/MM/YYYY</a></td>  ← Placement
      <td>Allottees link</td>
      <td>SHP link</td>
    Returns (placement_docs, preliminary_docs)
    """
    placement, preliminary = [], []

    # Find all data rows (class TTRow)
    row_pattern = re.compile(
        r'<td\s+class=["\']TTRow_left["\']>(.*?)</td>(.*?)'
        r'(?=<td\s+class=["\']TTRow_left["\']|</table)',
        re.DOTALL | re.IGNORECASE
    )
    # Alternative: find all <tr> that contain TTRow_left
    tr_pattern = re.compile(r'<tr\b[^>]*>(.*?)</tr>', re.DOTALL | re.IGNORECASE)
    trs = tr_pattern.findall(html)

    for tr in trs:
        # Company name
        co_m = re.search(r'class=["\']TTRow_left["\'][^>]*>(.*?)</td>', tr, re.IGNORECASE | re.DOTALL)
        if not co_m:
            continue
        company = re.sub(r'<[^>]+>', '', co_m.group(1)).strip()
        if not company:
            continue

        # All <td> cells in row
        cells = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL | re.IGNORECASE)
        # Cells: [0]=company, [1]=preliminary/draft, [2]=placement, [3]=allottees, [4]=shp
        if len(cells) < 3:
            continue

        def extract_link_and_date(cell):
            lm = re.search(r'href=["\'](/corporates/download/[^"\']+\.(?:pdf|PDF))["\'][^>]*>(\d{2}/\d{2}/\d{4})', cell, re.IGNORECASE)
            if lm:
                url = BSE_BASE + lm.group(1)
                date_str = lm.group(2)  # DD/MM/YYYY
                try:
                    date_iso = datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
                except Exception:
                    date_iso = ""
                return url, date_str, date_iso
            return None, None, None

        # Cell 1 = Preliminary (Draft Placement)
        prelim_url, prelim_date, prelim_iso = extract_link_and_date(cells[1] if len(cells) > 1 else "")
        # Cell 2 = Placement
        place_url, place_date, place_iso = extract_link_and_date(cells[2] if len(cells) > 2 else "")

        doc_id_base = re.sub(r'[^a-z0-9]', '_', company.lower())[:30]

        if prelim_url and prelim_date:
            preliminary.append({
                "date": _fmt_date(prelim_date),
                "date_iso": prelim_iso,
                "title": f"{company} – Preliminary Placement Document",
                "company": company,
                "pdf_url": prelim_url,
                "page_url": f"{BSE_BASE}/corporates/qip.aspx",
                "type": "BSE_PRELIMINARY",
                "id": f"prelim_{doc_id_base}_{prelim_iso}",
            })

        if place_url and place_date:
            placement.append({
                "date": _fmt_date(place_date),
                "date_iso": place_iso,
                "title": f"{company} – Placement Document",
                "company": company,
                "pdf_url": place_url,
                "page_url": f"{BSE_BASE}/corporates/qip.aspx",
                "type": "BSE_PLACEMENT",
                "id": f"place_{doc_id_base}_{place_iso}",
            })

    return placement, preliminary


def scrape_bse_qip(from_date_iso=None, to_date_iso=None):
    """Background thread — fetch BSE QIP page and populate both BSE caches."""
    for t in ["BSE_PLACEMENT", "BSE_PRELIMINARY"]:
        cache[t].update({"fetching": True, "error": None, "fetch_started_at": time.time()})

    print(f"[BSE QIP] Fetching {'('+from_date_iso+' to '+to_date_iso+')' if from_date_iso else '(latest)'}")
    try:
        headers = {
            'User-Agent': BSE_UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Referer': 'https://www.bseindia.com',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        req = urllib.request.Request(f"{BSE_BASE}/corporates/qip.aspx", headers=headers)
        with urllib.request.urlopen(req, timeout=25, context=SSL_CTX) as r:
            html = r.read().decode('utf-8', errors='ignore')

        placement, preliminary = parse_bse_qip_page(html)

        # Apply date filter if provided
        if from_date_iso and to_date_iso:
            placement    = [d for d in placement    if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]
            preliminary  = [d for d in preliminary  if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]

        # Sort descending by date
        placement.sort(   key=lambda d: d["date_iso"], reverse=True)
        preliminary.sort( key=lambda d: d["date_iso"], reverse=True)

        cache["BSE_PLACEMENT"].update({
            "data": placement, "total": len(placement),
            "pages_done": 1, "fetching": False
        })
        cache["BSE_PRELIMINARY"].update({
            "data": preliminary, "total": len(preliminary),
            "pages_done": 1, "fetching": False
        })
        print(f"[BSE QIP] Done — {len(placement)} Placement, {len(preliminary)} Preliminary")

    except Exception as e:
        for t in ["BSE_PLACEMENT", "BSE_PRELIMINARY"]:
            cache[t].update({"error": str(e), "fetching": False})
        print(f"[BSE QIP] Error: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  CCI ORDERS SCRAPING
# ════════════════════════════════════════════════════════════════════════════════

def scrape_cci(doc_type, from_date_iso=None, to_date_iso=None):
    """Background thread — fetch CCI Orders for a specific form type."""
    form_type = SOURCES[doc_type]["form_type"]
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    print(f"[{doc_type}] Fetching {'('+from_date_iso+' to '+to_date_iso+')' if from_date_iso else '(latest)'}")

    last_err = None
    for _cci_attempt in range(3):
      try:
        url = "https://www.cci.gov.in/combination/orders-section31"
        # NOTE: CCI's server-side fromdate/todate filter is broken (always returns 0
        # when dates are supplied). Fetch all records and filter locally instead.
        query = {
            'draw': '1', 'start': '0', 'length': '2000',
            'form_type': form_type,
            'order_status': '', 'searchString': '', 'search_type': '',
            'fromdate': '', 'todate': '',
        }

        q_str = urllib.parse.urlencode(query)
        req = urllib.request.Request(url + '?' + q_str, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json'
        })

        with _urlopen_retry(req) as r:
            json_data = json.loads(r.read().decode('utf-8', errors='ignore'))

        docs = []
        raw_records = json_data.get('data', [])

        for row in raw_records:
            # Only use order_file_content — summaries are not orders and must be excluded
            pdf_url = ''
            raw_json = row.get('order_file_content') or ''
            if not raw_json or str(raw_json).strip() in ('None', 'null', '', '[]'):
                continue  # skip entries that have no order PDF
            try:
                parsed = json.loads(html.unescape(str(raw_json)))
                if isinstance(parsed, list) and parsed:
                    fp = parsed[0].get('file_name', '')
                    if fp:
                        pdf_url = 'https://www.cci.gov.in/' + fp.lstrip('/')
            except Exception:
                pass
            if not pdf_url:
                continue  # skip if we still couldn't get an order PDF

            party_name = _clean_text(row.get('party_name', ''))
            combo_no   = _clean_text(row.get('combination_no', ''))
            # Use decision_date as primary; notification_date as fallback
            date_str = (row.get('decision_date') or row.get('notification_date') or '').strip()

            try:
                date_iso = datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
            except Exception:
                date_iso = ""

            row_id = str(row.get('id') or '')
            page_url = (
                f"https://www.cci.gov.in/combination/order/details/order/{row_id}/0/orders-section31"
                if row_id else "https://www.cci.gov.in/combination/orders-section31"
            )

            safe_combo = re.sub(r'[^a-zA-Z0-9_-]', '_', combo_no)
            doc_id = f"cci_{form_type}_{safe_combo}"
            docs.append({
                "date":     _fmt_date(date_str),
                "date_iso": date_iso,
                "title":    f"[{combo_no}] {party_name}",
                "company":  party_name,
                "pdf_url":  pdf_url,
                "page_url": page_url,
                "type":     doc_type,
                "id":       doc_id,
            })

        # Apply local date filtering (API-side date filter is broken)
        if from_date_iso and to_date_iso:
            docs = [d for d in docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]

        cache[doc_type].update({"data": docs, "total": len(docs), "pages_done": 1, "fetching": False})
        print(f"[{doc_type}] Done — {len(docs)} orders found")
        return  # success

      except Exception as e:
        last_err = e
        if _cci_attempt < 2:
            wait = 10 * (_cci_attempt + 1)
            print(f"[{doc_type}] Attempt {_cci_attempt+1}/3 failed ({e}), retrying in {wait}s...")
            time.sleep(wait)

    cache[doc_type].update({"error": str(last_err), "fetching": False})
    print(f"[{doc_type}] Failed after 3 attempts: {last_err}")
    traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  CCI COMBINATION (gun-jumping / approved-with-modification) SCRAPING
# ════════════════════════════════════════════════════════════════════════════════

def scrape_cci_combo(doc_type, from_date_iso=None, to_date_iso=None):
    """Background thread — fetch CCI Combination orders from a custom endpoint."""
    endpoint = SOURCES[doc_type]["cci_combo_url"]
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    print(f"[{doc_type}] Fetching {'('+from_date_iso+' to '+to_date_iso+')' if from_date_iso else '(latest)'}")

    try:
        url = f"https://www.cci.gov.in/combination/{endpoint}"
        query = {
            'draw': '1', 'start': '0', 'length': '2000',
            'searchString': '', 'search_type': ''
        }
        # NOTE: CCI's server-side fromdate/todate filter is broken (always returns 0
        # when dates are supplied). Fetch all records and filter locally instead.
        query['fromdate'] = ''
        query['todate']   = ''

        q_str = urllib.parse.urlencode(query)
        req = urllib.request.Request(url + '?' + q_str, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json'
        })

        with _urlopen_retry(req) as r:
            json_data = json.loads(r.read().decode('utf-8', errors='ignore'))

        docs = []
        raw_records = json_data.get('data', [])

        for row in raw_records:
            order_json_str = row.get('order_file_content')
            if not order_json_str or str(order_json_str).strip() in ('None', 'null', ''):
                continue

            try:
                clean_json = html.unescape(order_json_str)
                order_files = json.loads(clean_json)
                if not order_files or not isinstance(order_files, list):
                    continue
                file_path = order_files[0].get('file_name', '')
                if not file_path:
                    continue
                pdf_url = "https://www.cci.gov.in/" + file_path.lstrip('/')
            except Exception:
                continue

            party_name = _clean_text(row.get('party_name', ''))
            combo_no = _clean_text(row.get('combination_no', ''))
            date_str = row.get('decision_date', '').strip()

            try:
                date_iso = datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
            except Exception:
                date_iso = ""

            safe_combo = re.sub(r'[^a-zA-Z0-9_-]', '_', combo_no)
            doc_id = f"cci_combo_{endpoint[:10]}_{safe_combo}"
            docs.append({
                "date": _fmt_date(date_str),
                "date_iso": date_iso,
                "title": f"[{combo_no}] {party_name}",
                "company": party_name,
                "pdf_url": pdf_url,
                "page_url": f"https://www.cci.gov.in/combination/{endpoint}",
                "type": doc_type,
                "id": doc_id,
            })

        # Apply local date filtering (CCI API-side date filter is broken)
        if from_date_iso and to_date_iso:
            docs = [d for d in docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]

        cache[doc_type].update({"data": docs, "total": len(docs), "pages_done": 1, "fetching": False})
        print(f"[{doc_type}] Done — {len(docs)} combo orders found")

    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        print(f"[{doc_type}] Error: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  CCI ANTITRUST SCRAPING
# ════════════════════════════════════════════════════════════════════════════════

def scrape_cci_antitrust(doc_type, from_date_iso=None, to_date_iso=None):
    """Background thread — fetch CCI Antitrust Orders for a specific section."""
    section_id = int(SOURCES[doc_type]["section_id"])
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    print(f"[{doc_type}] Fetching {'('+from_date_iso+' to '+to_date_iso+')' if from_date_iso else '(latest)'}")
    
    try:
        url = "https://www.cci.gov.in/antitrust/orders/list"
        query = {
            'draw': '1', 'start': '0', 'length': '2000',
            'searchString': '', 'search_type': ''
        }
        # NOTE: CCI's server-side fromdate/todate filter is broken (always returns 0
        # when dates are supplied). Fetch all records and filter locally instead.
        query['fromdate'] = ''
        query['todate']   = ''

        q_str = urllib.parse.urlencode(query)
        req = urllib.request.Request(url + '?' + q_str, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json'
        })
        
        with _urlopen_retry(req) as r:
            json_data = json.loads(r.read().decode('utf-8', errors='ignore'))
            
        docs = []
        raw_records = json_data.get('data', [])
        
        for row in raw_records:
            # Filter by section_id — API doesn't do this server-side, must filter client-side
            try:
                row_section = int(row.get('antitrust_categories_id', 0))
            except (ValueError, TypeError):
                row_section = 0
            if row_section != section_id:
                continue
                
            file_content = row.get('file_content')
            if not file_content or str(file_content).strip() in ('None', 'null', ''):
                continue  # Skip if no order file exists

            try:
                # CCI returns HTML escaped JSON: [{&quot;file_name&quot;:...}]
                clean_json = html.unescape(file_content)
                # Parse embedded JSON: [{"file_name":"images/antitrustorder/...","file_size":"..."}]
                order_files = json.loads(clean_json)
                if not order_files or not isinstance(order_files, list):
                    continue
                file_path = order_files[0].get('file_name', '')
                if not file_path:
                    continue
                pdf_url = "https://www.cci.gov.in/" + file_path.lstrip('/')
            except Exception:
                continue

            case_no = _clean_text(row.get('case_no', ''))
            description = _clean_text(row.get('description', ''))
            date_str = row.get('order_date', '').strip()
            
            try:
                date_iso = datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
            except Exception:
                date_iso = ""

            # Sanitize ID: only keep alphanumeric, underscore, hyphen
            safe_case = re.sub(r'[^a-zA-Z0-9_-]', '_', case_no)
            doc_id = f"cci_anti_{section_id}_{safe_case}"
            docs.append({
                "date": _fmt_date(date_str),
                "date_iso": date_iso,
                "title": f"[{case_no}] {description}",
                "company": description,
                "pdf_url": pdf_url,
                "page_url": "https://www.cci.gov.in/antitrust/orders",
                "type": doc_type,
                "id": doc_id,
            })

        # Apply fallback local filtering in case CCI API misses it
        if from_date_iso and to_date_iso:
            docs = [d for d in docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]

        cache[doc_type].update({"data": docs, "total": len(docs), "pages_done": 1, "fetching": False})
        print(f"[{doc_type}] Done — {len(docs)} antitrust orders found (section {section_id})")

    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        print(f"[{doc_type}] Error: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  RBI SCRAPING
# ════════════════════════════════════════════════════════════════════════════════

def _rbi_aspx_fetch(page_url, year=None, retries=2):
    """Fetch an rbi.org.in ASP.NET page, optionally with year postback.
    Returns the HTML string for the given year-filtered view."""
    last_exc = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(page_url, headers={"User-Agent": SEBI_UA})
            with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
                page_html = r.read().decode("utf-8", errors="ignore")
            if year is None:
                return page_html
            vs  = re.search(r'__VIEWSTATE.*?value="([^"]+)"', page_html)
            vsg = re.search(r'__VIEWSTATEGENERATOR.*?value="([^"]+)"', page_html)
            ev  = re.search(r'__EVENTVALIDATION.*?value="([^"]+)"', page_html)
            data = urllib.parse.urlencode({
                "__EVENTTARGET": "", "__EVENTARGUMENT": "",
                "__VIEWSTATE": vs.group(1) if vs else "",
                "__VIEWSTATEGENERATOR": vsg.group(1) if vsg else "",
                "__EVENTVALIDATION": ev.group(1) if ev else "",
                "hdnYear": str(year),
                "UsrFontCntr$btn": "",
            }).encode()
            req2 = urllib.request.Request(page_url, data=data, headers={
                "User-Agent": SEBI_UA,
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": page_url,
            })
            with urllib.request.urlopen(req2, timeout=30, context=SSL_CTX) as r2:
                return r2.read().decode("utf-8", errors="ignore")
        except Exception as e:
            last_exc = e
            if attempt < retries:
                time.sleep(3 * (attempt + 1))
                continue
    raise last_exc


def _rbi_parse_entries(page_html, doc_type, detail_aspx):
    """Parse RBI entries from an rbi.org.in page.
    detail_aspx: e.g. 'BS_ViewMasCirculardetails' or 'BS_ViewMasDirections'
    Returns list of doc dicts."""
    docs = []
    current_date_str = ""
    current_dept = ""
    rbi_prefix = "rbi_mc" if "Circular" in detail_aspx else "rbi_md"
    for row in re.split(r"<tr>", page_html):
        # Check for section/date header
        hdr = re.search(r'class="tableheader"[^>]*>\s*<b>([^<]+)</b>', row)
        if hdr:
            txt = hdr.group(1).strip()
            try:
                datetime.strptime(txt, "%b %d, %Y")
                current_date_str = txt
            except Exception:
                current_dept = txt
            continue
        # Check for entry row
        title_m = re.search(
            r"href=['\"]?" + re.escape(detail_aspx) + r"\.aspx\?id=(\d+)['\"]?>\s*([^<]+)<", row)
        if not title_m:
            continue
        entry_id = title_m.group(1)
        title = html.unescape(title_m.group(2).strip())
        # PDF URL — may be single-quoted or double-quoted
        pdf_m = re.search(
            r"href=['\"]?(https?://rbidocs\.rbi\.org\.in/rdocs/notification/PDFs/[^'\">\s]+)",
            row, re.IGNORECASE)
        pdf_url = pdf_m.group(1) if pdf_m else ""
        page_url = f"https://rbi.org.in/Scripts/{detail_aspx}.aspx?id={entry_id}"
        try:
            date_iso = datetime.strptime(current_date_str, "%b %d, %Y").strftime("%Y-%m-%d")
        except Exception:
            date_iso = ""
        docs.append({
            "date":     _fmt_date(current_date_str),
            "date_iso": date_iso,
            "title":    f"[{current_dept}] {title}" if current_dept else title,
            "company":  current_dept,
            "page_url": page_url,
            "pdf_url":  pdf_url,
            "type":     doc_type,
            "id":       f"{rbi_prefix}_{entry_id}",
        })
    return docs


def _rbi_years_for_range(from_iso, to_iso, is_financial_year):
    """Return the set of year filter values needed for a date range.
    MC uses financial years: year N = Apr (N-1) to Mar N.
    MD uses calendar years: year N = Jan N to Dec N."""
    from_dt = datetime.strptime(from_iso, "%Y-%m-%d")
    to_dt   = datetime.strptime(to_iso,   "%Y-%m-%d")
    years = set()
    if is_financial_year:
        # FY year value: if month >= April, FY = year+1; else FY = year
        for y in range(from_dt.year, to_dt.year + 2):
            fy_start = datetime(y - 1, 4, 1)
            fy_end   = datetime(y, 3, 31)
            if fy_start <= to_dt and fy_end >= from_dt:
                years.add(y)
    else:
        for y in range(from_dt.year, to_dt.year + 1):
            years.add(y)
    return sorted(years)


def scrape_rbi(doc_type, from_date_iso=None, to_date_iso=None):
    """Fetch RBI Master Directions or Master Circulars from rbi.org.in with year filter."""
    rbi_path = SOURCES[doc_type]["rbi_path"]
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    print(f"[{doc_type}] Fetching {'('+from_date_iso+' to '+to_date_iso+')' if from_date_iso else '(latest)'}")

    try:
        if rbi_path == "master-circulars":
            page_url    = "https://rbi.org.in/Scripts/BS_ViewMasterCirculardetails.aspx"
            detail_aspx = "BS_ViewMasCirculardetails"
            is_fy       = True
        else:  # master-directions
            page_url    = "https://rbi.org.in/scripts/bs_viewmasterdirections.aspx"
            detail_aspx = "BS_ViewMasDirections"
            is_fy       = False

        if from_date_iso and to_date_iso:
            years = _rbi_years_for_range(from_date_iso, to_date_iso, is_fy)
        else:
            years = [datetime.now().year]

        all_docs = []
        seen_ids = set()
        for i, yr in enumerate(years):
            print(f"[{doc_type}] Fetching year {yr} ({i+1}/{len(years)})")
            page_html = _rbi_aspx_fetch(page_url, year=yr)
            entries = _rbi_parse_entries(page_html, doc_type, detail_aspx)
            for d in entries:
                if d["id"] not in seen_ids:
                    seen_ids.add(d["id"])
                    all_docs.append(d)
            cache[doc_type].update({"pages_done": i + 1, "total": len(all_docs),
                                    "fetch_started_at": time.time()})
            if i < len(years) - 1:
                time.sleep(1.0)

        docs = all_docs
        if from_date_iso and to_date_iso:
            docs = [d for d in docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]

        cache[doc_type].update({"data": docs, "total": len(docs), "pages_done": len(years),
                                "fetching": False})
        print(f"[{doc_type}] Done — {len(docs)} docs")

    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        print(f"[{doc_type}] Error: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  IRDAI SCRAPING
# ════════════════════════════════════════════════════════════════════════════════

def scrape_irdai(doc_type, from_date_iso=None, to_date_iso=None):
    """Background thread — fetch IRDAI Circulars (all pages)."""
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    print(f"[{doc_type}] Fetching {'('+from_date_iso+' to '+to_date_iso+')' if from_date_iso else '(latest)'}")

    try:
        IRDAI_DELTA = 20
        all_docs = []
        seen_ids = set()
        cur_page = 1
        MAX_PAGES = 100  # safety cap

        for _page in range(MAX_PAGES):
            url = (f"https://irdai.gov.in/circulars?"
                   f"_com_irdai_document_media_IRDAIDocumentMediaPortlet_delta={IRDAI_DELTA}"
                   f"&_com_irdai_document_media_IRDAIDocumentMediaPortlet_cur={cur_page}"
                   f"&_com_irdai_document_media_IRDAIDocumentMediaPortlet_resetCur=false")
            html_text = fetch_simple(url)

            # Find the table
            table_m = re.search(r'<table[^>]*class="[^"]*table[^"]*"[^>]*>(.*?)</table>', html_text, re.DOTALL)
            if not table_m:
                break

            table = table_m.group(1)
            rows = re.findall(r'<tr\b[^>]*>(.*?)</tr>', table, re.DOTALL)

            page_docs = []
            for row in rows[1:]:  # skip header row
                cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
                if len(cells) < 6:
                    continue

                title = _clean_text(cells[2])
                date_str = re.sub(r'<[^>]+>', '', cells[4]).strip()
                pdf_m = re.search(r'href="([^"]+\.pdf[^"]*)"', cells[5])
                pdf_url = pdf_m.group(1) if pdf_m else ""

                if not title or not date_str or len(date_str) != 10:
                    continue

                try:
                    date_iso = datetime.strptime(date_str, "%d-%m-%Y").strftime("%Y-%m-%d")
                except Exception:
                    date_iso = ""

                slug = re.sub(r'[^a-z0-9]', '_', title.lower())[:40]
                doc_id = f"irdai_{slug}_{date_str}"

                page_docs.append({
                    "date": _fmt_date(date_str.replace('-', '/')),
                    "date_iso": date_iso,
                    "title": title,
                    "company": "",
                    "page_url": "https://irdai.gov.in/circulars",
                    "pdf_url": pdf_url,
                    "type": doc_type,
                    "id": doc_id,
                })

            new_docs = [d for d in page_docs if d['id'] not in seen_ids]
            if not new_docs:
                break  # No new results — done
            for d in new_docs:
                seen_ids.add(d['id'])
                all_docs.append(d)

            if len(page_docs) < IRDAI_DELTA:
                break  # Last page (partial)

            cur_page += 1
            time.sleep(0.5)

        docs = all_docs
        if from_date_iso and to_date_iso:
            docs = [d for d in docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]

        cache[doc_type].update({"data": docs, "total": len(docs), "pages_done": cur_page, "fetching": False})
        print(f"[{doc_type}] Done — {len(docs)} circulars")

    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        print(f"[{doc_type}] Error: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  INDIA INX CIRCULARS SCRAPING
# ════════════════════════════════════════════════════════════════════════════════

def scrape_inx_circulars(doc_type, from_date_iso=None, to_date_iso=None):
    """Background thread — fetch India INX Circulars (first page, 10 items)."""
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    print(f"[{doc_type}] Fetching {'('+from_date_iso+' to '+to_date_iso+')' if from_date_iso else '(latest)'}")

    try:
        url = 'https://www.indiainx.com/markets/CircularsLR.aspx'
        html_text = fetch_simple(url)

        trs = re.findall(r'<tr[^>]*>(.*?)</tr>', html_text, re.DOTALL | re.IGNORECASE)
        data_rows = [t for t in trs if 'lnkNavigate' in t]

        docs = []
        for row in data_rows:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)
            if len(cells) < 6:
                continue

            date_text = re.sub(r'<[^>]+>', '', cells[0]).strip()
            circ_no = re.sub(r'<[^>]+>', '', cells[1]).strip()
            link_m = re.search(r'href="([^"]+)"[^>]*>([^<]+)', cells[2])
            segment = re.sub(r'<[^>]+>', '', cells[3]).strip()

            if not link_m:
                continue

            pdf_raw = link_m.group(1).strip().replace('\\', '/')
            title = _clean_text(link_m.group(2))
            pdf_url = pdf_raw if pdf_raw.startswith('http') else f"https://www.indiainx.com/{pdf_raw.lstrip('/')}"

            # Date: "February 04,2026" → normalize comma spacing
            date_norm = date_text.replace(',', ', ').replace('  ', ' ').strip()
            try:
                dt = datetime.strptime(date_norm, "%B %d, %Y")
                date_iso = dt.strftime("%Y-%m-%d")
                date_display = dt.strftime("%d %b %Y")
            except Exception:
                date_iso = ""
                date_display = date_text

            safe_no = re.sub(r'[^a-zA-Z0-9_-]', '_', circ_no)
            doc_id = f"inx_circ_{safe_no}"

            # Extract issuer company from title (pattern: "... by CompanyName")
            issuer = ''
            by_m = re.search(r'\bby\s+(.+?)$', title, re.IGNORECASE)
            if by_m:
                issuer = by_m.group(1).strip()
                # Strip trailing "due in YYYY" or "due YYYY"
                issuer = re.sub(r'\s+due\s+(?:in\s+)?\d{4}.*$', '', issuer).strip()
            elif 'Programme by ' in title:
                issuer = title.split('Programme by ')[-1].strip()
                issuer = re.sub(r'\s+due\s+(?:in\s+)?\d{4}.*$', '', issuer).strip()

            docs.append({
                "date": date_display,
                "date_iso": date_iso,
                "title": f"[{circ_no}] {title}",
                "company": issuer if issuer else segment,
                "page_url": url,
                "pdf_url": pdf_url,
                "type": doc_type,
                "id": doc_id,
            })

        if from_date_iso and to_date_iso:
            docs = [d for d in docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]

        cache[doc_type].update({"data": docs, "total": len(docs), "pages_done": 1, "fetching": False})
        print(f"[{doc_type}] Done — {len(docs)} circulars")

    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        print(f"[{doc_type}] Error: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  INDIA INX ISSUER DOCUMENTS SCRAPING
# ════════════════════════════════════════════════════════════════════════════════

def scrape_inx_issuer(doc_type, from_date_iso=None, to_date_iso=None):
    """Background thread — fetch India INX Issuer Documents (first page, 20 items)."""
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    print(f"[{doc_type}] Fetching {'('+from_date_iso+' to '+to_date_iso+')' if from_date_iso else '(latest)'}")

    try:
        url = 'https://www.indiainx.com/static/issuer_details.aspx'
        html_text = fetch_simple(url)

        trs = re.findall(r'<tr[^>]*>(.*?)</tr>', html_text, re.DOTALL | re.IGNORECASE)
        data_rows = [t for t in trs if 'IssuerDetails' in t or 'lnkDoc' in t]

        docs = []
        for row in data_rows:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)
            if len(cells) < 5:
                continue

            # Company from img alt or text
            comp_m = re.search(r'alt="([^"]+)"', cells[0])
            company = _clean_text(comp_m.group(1)) if comp_m else _clean_text(re.sub(r'<[^>]+>', '', cells[0]))
            date_str = re.sub(r'<[^>]+>', '', cells[1]).strip()
            doc_m = re.search(r'href="([^"]+)"[^>]*>([^<]+)', cells[2])
            doc_type_text = re.sub(r'<[^>]+>', '', cells[3]).strip()

            if not doc_m:
                continue

            doc_url_raw = doc_m.group(1).strip()
            title = _clean_text(doc_m.group(2))
            doc_url = doc_url_raw if doc_url_raw.startswith('http') else f"https://www.indiainx.com/{doc_url_raw.lstrip('/')}"

            # Date: DD/MM/YYYY
            try:
                date_iso = datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
            except Exception:
                date_iso = ""

            slug = re.sub(r'[^a-z0-9]', '_', title.lower())[:30]
            doc_id = f"inx_iss_{slug}_{date_iso}"

            docs.append({
                "date": _fmt_date(date_str),
                "date_iso": date_iso,
                "title": f"{company} — {title}",
                "company": company,
                "page_url": url,
                "pdf_url": doc_url,
                "type": doc_type,
                "id": doc_id,
            })

        if from_date_iso and to_date_iso:
            docs = [d for d in docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]

        cache[doc_type].update({"data": docs, "total": len(docs), "pages_done": 1, "fetching": False})
        print(f"[{doc_type}] Done — {len(docs)} issuer docs")

    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        print(f"[{doc_type}] Error: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  RBI MASTER DIRECTIONS (ENTITY-WISE) SCRAPING
# ════════════════════════════════════════════════════════════════════════════════

RBI_MD_ENTITY_NAMES = {
    "403": "Commercial Banks", "404": "Small Finance Banks", "405": "Payments Banks",
    "406": "Local Area Banks", "407": "Regional Rural Banks", "408": "Urban Co-operative Banks",
    "409": "Rural Co-operative Banks", "410": "All India Financial Institutions",
    "411": "NBFCs",
}

def scrape_rbi_md_entity(doc_type, from_date_iso=None, to_date_iso=None):
    """Background thread — fetch RBI Master Directions for a specific entity type (did=403..411)."""
    rbi_did = SOURCES[doc_type]["rbi_did"]
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    entity_name = RBI_MD_ENTITY_NAMES.get(rbi_did, rbi_did)
    print(f"[{doc_type}] Fetching RBI MD {entity_name} (did={rbi_did})")

    try:
        url = f"https://www.rbi.org.in/Scripts/BS_ViewMasterDirections.aspx?did={rbi_did}"
        html_text = fetch_simple(url)

        # Parse <tr> blocks for date headers and document rows
        rows = re.findall(r'<tr>(.*?)</tr>', html_text, re.DOTALL)
        current_date = None
        docs = []

        for row in rows:
            # Date header: <td class="tableheader" colspan="4"...><b>Nov 28, 2025</b>
            date_m = re.search(
                r'<td class="tableheader" colspan="4"[^>]*><b>'
                r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{1,2}, \d{4})</b>',
                row)
            if date_m:
                current_date = date_m.group(1)
                continue

            # Document link: <a class="link2" href=BS_ViewMasDirections.aspx?id=XXXXX> Title</a>
            doc_m = re.search(
                r'<a class="link2" href=["\']?(BS_ViewMasDirections\.aspx\?id=(\d+))["\']?>\s*([^<]+)',
                row)
            if not doc_m:
                continue

            page_path = doc_m.group(1)
            rid = doc_m.group(2)
            title = _clean_text(doc_m.group(3))

            # PDF link: href='https://rbidocs.rbi.org.in/rdocs/notification/PDFs/XXXMD.PDF'
            pdf_m = re.search(r"href='(https://rbidocs\.rbi\.org\.in[^']+\.PDF)'", row, re.IGNORECASE)
            pdf_url = pdf_m.group(1) if pdf_m else ""

            page_url = f"https://www.rbi.org.in/Scripts/{page_path}"

            date_text = current_date or ''
            try:
                date_iso = datetime.strptime(date_text, "%b %d, %Y").strftime("%Y-%m-%d")
            except Exception:
                date_iso = ""

            doc_id = f"rbi_md_{rbi_did}_{rid}"

            docs.append({
                "date": _fmt_date(date_text) if date_text else "",
                "date_iso": date_iso,
                "title": title,
                "company": "",
                "page_url": page_url,
                "pdf_url": pdf_url,
                "type": doc_type,
                "id": doc_id,
            })

        if from_date_iso and to_date_iso:
            docs = [d for d in docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]

        cache[doc_type].update({"data": docs, "total": len(docs), "pages_done": 1, "fetching": False})
        print(f"[{doc_type}] Done — {len(docs)} master directions ({entity_name})")

    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        print(f"[{doc_type}] Error: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  TELANGANA RERA — ORDERS (Adjudication / Authority / Suo Motu)
# ════════════════════════════════════════════════════════════════════════════════

def scrape_tg_rera(doc_type, from_date_iso=None, to_date_iso=None):
    """Scrape TG RERA orders pages — data is fully embedded in HTML (DataTables)."""
    url = SOURCES[doc_type]["tgrera_url"]
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    print(f"[{doc_type}] Fetching TG RERA from {url}")

    last_err = None
    for attempt in range(3):
      try:
        html_text = fetch_simple(url, retries=3, timeout=30)
        # Table id="pdflistgrid", 4 cols: [sno, title, date(DD/MM/YYYY), pdf_td]
        table_m = re.search(r'<table[^>]*id="pdflistgrid"[^>]*>(.*?)</table>', html_text, re.S)
        if not table_m:
            raise ValueError("pdflistgrid table not found")

        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_m.group(1), re.S)
        docs = []
        for row in rows:
            tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
            if len(tds) < 4:
                continue

            title = _clean_text(tds[1])
            if not title:
                continue
            date_raw = _clean_text(tds[2])  # DD/MM/YYYY
            pdf_m = re.search(r"href=['\"]([^'\"]+ShowPdf[^'\"]*)['\"]", row)
            if pdf_m:
                raw_href = pdf_m.group(1)
                pdf_url = raw_href if raw_href.startswith('http') else f"https://rera.telangana.gov.in{raw_href}"
            else:
                pdf_url = url

            date_text = _fmt_date(date_raw) if date_raw else ""
            try:
                date_iso = datetime.strptime(date_raw.strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
            except Exception:
                date_iso = ""

            doc_id = f"tgrera_{doc_type}_{len(docs)}"
            docs.append({
                "date": date_text, "date_iso": date_iso,
                "title": title, "company": "",
                "page_url": url, "pdf_url": pdf_url,
                "type": doc_type, "id": doc_id,
            })

        if from_date_iso and to_date_iso:
            docs = [d for d in docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]

        cache[doc_type].update({"data": docs, "total": len(docs), "pages_done": 1, "fetching": False})
        print(f"[{doc_type}] Done — {len(docs)} TG RERA orders")
        return  # success

      except Exception as e:
        last_err = e
        if attempt < 2:
            wait = 10 * (attempt + 1)
            print(f"[{doc_type}] Attempt {attempt+1}/3 failed ({e}), retrying in {wait}s...")
            time.sleep(wait)

    cache[doc_type].update({"error": str(last_err), "fetching": False})
    print(f"[{doc_type}] Failed after 3 attempts: {last_err}")
    traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  TELANGANA RERA — CIRCULARS
# ════════════════════════════════════════════════════════════════════════════════

def scrape_tg_rera_circ(doc_type, from_date_iso=None, to_date_iso=None):
    """Scrape TG RERA circulars — table has 5 cols: [sno, circular_no, title, date, pdf]."""
    url = SOURCES[doc_type]["tgrera_url"]
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    print(f"[{doc_type}] Fetching TG RERA Circulars")

    last_err = None
    for attempt in range(3):
      try:
        html_text = fetch_simple(url, retries=3, timeout=30)
        table_m = re.search(r'<table[^>]*id="pdflistgrid"[^>]*>(.*?)</table>', html_text, re.S)
        if not table_m:
            raise ValueError("pdflistgrid table not found")

        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_m.group(1), re.S)
        docs = []
        for row in rows:
            tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
            if len(tds) < 5:
                continue

            circ_no = _clean_text(tds[1])
            title_text = _clean_text(tds[2])
            title = f"{circ_no} — {title_text}" if circ_no else title_text
            if not title_text:
                continue
            date_raw = _clean_text(tds[3])
            pdf_m = re.search(r"href=['\"]([^'\"]+ShowPdf[^'\"]*)['\"]", row)
            if pdf_m:
                raw_href = pdf_m.group(1)
                pdf_url = raw_href if raw_href.startswith('http') else f"https://rera.telangana.gov.in{raw_href}"
            else:
                pdf_url = ""

            date_text = _fmt_date(date_raw) if date_raw else ""
            try:
                date_iso = datetime.strptime(date_raw.strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
            except Exception:
                date_iso = ""

            doc_id = f"tgrera_circ_{len(docs)}"
            docs.append({
                "date": date_text, "date_iso": date_iso,
                "title": title, "company": "",
                "page_url": url, "pdf_url": pdf_url,
                "type": doc_type, "id": doc_id,
            })

        if from_date_iso and to_date_iso:
            docs = [d for d in docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]

        cache[doc_type].update({"data": docs, "total": len(docs), "pages_done": 1, "fetching": False})
        print(f"[{doc_type}] Done — {len(docs)} TG RERA circulars")
        return  # success

      except Exception as e:
        last_err = e
        if attempt < 2:
            wait = 10 * (attempt + 1)
            print(f"[{doc_type}] Attempt {attempt+1}/3 failed ({e}), retrying in {wait}s...")
            time.sleep(wait)

    cache[doc_type].update({"error": str(last_err), "fetching": False})
    print(f"[{doc_type}] Failed after 3 attempts: {last_err}")
    traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  TAMIL NADU RERA — ORDERS
# ════════════════════════════════════════════════════════════════════════════════

def scrape_tn_rera(doc_type, from_date_iso=None, to_date_iso=None):
    """Scrape TN RERA orders for all years in the requested date range.
    Table id='example', 7 cols: [sno, complaint_no, complainant, respondent, project, date, order_pdf]."""
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    now_year  = datetime.now().year
    from_year = int(from_date_iso[:4]) if from_date_iso else now_year
    to_year   = int(to_date_iso[:4])   if to_date_iso   else now_year
    to_year   = max(to_year, now_year)   # always include current year
    from_year = max(from_year, 2018)     # TN RERA operational from ~2018
    print(f"[{doc_type}] Fetching TN RERA Orders for {from_year}–{to_year}")

    try:
        all_docs = []
        for year in range(to_year, from_year - 1, -1):  # most-recent year first
            url = f"https://rera.tn.gov.in/cms/tnrera_judgements/{year}.php"
            try:
                html_text = fetch_simple(url)
            except Exception as e:
                print(f"[{doc_type}] year {year} fetch failed: {e}, skipping")
                continue

            table_m = re.search(r'<table[^>]*id="example"[^>]*>(.*?)</table>', html_text, re.S)
            if not table_m:
                print(f"[{doc_type}] year {year}: table not found, skipping")
                continue

            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_m.group(1), re.S)
            year_docs = 0
            for row in rows:
                tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
                if len(tds) < 7:
                    continue

                sno = _clean_text(tds[0])
                if not sno or not sno[0].isdigit():
                    continue  # skip header row

                complaint_no = _clean_text(tds[1])
                complainant  = _clean_text(tds[2])
                respondent   = _clean_text(tds[3])
                project      = _clean_text(tds[4])
                date_raw     = _clean_text(tds[5])  # DD.MM.YYYY

                title = f"{complaint_no} — {complainant} vs {respondent}"
                if project:
                    title += f" [{project[:60]}]"

                pdf_m = re.search(r'href="([^"]+\.pdf)"', row, re.I)
                pdf_url = pdf_m.group(1) if pdf_m else ""
                if pdf_url and not pdf_url.startswith("http"):
                    pdf_url = (f"https://rera.tn.gov.in{pdf_url}" if pdf_url.startswith("/")
                               else f"https://rera.tn.gov.in/cms/tnrera_judgements/{pdf_url}")

                try:
                    date_iso  = datetime.strptime(date_raw.strip(), "%d.%m.%Y").strftime("%Y-%m-%d")
                    date_text = datetime.strptime(date_raw.strip(), "%d.%m.%Y").strftime("%d %b %Y")
                except Exception:
                    date_iso  = ""
                    date_text = date_raw

                doc_id = f"tnrera_{complaint_no.replace('/', '_').replace(' ', '')}_{len(all_docs)}"
                all_docs.append({
                    "date": date_text, "date_iso": date_iso,
                    "title": title, "company": respondent,
                    "page_url": url, "pdf_url": pdf_url,
                    "type": doc_type, "id": doc_id,
                })
                year_docs += 1

            print(f"  [{doc_type}] year {year}: {year_docs} orders found")
            cache[doc_type].update({"pages_done": to_year - year + 1, "fetch_started_at": time.time()})
            if year > from_year:
                time.sleep(1.0)  # polite pause between year fetches

        if from_date_iso and to_date_iso:
            all_docs = [d for d in all_docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]

        cache[doc_type].update({"data": all_docs, "total": len(all_docs),
                                 "pages_done": to_year - from_year + 1, "fetching": False})
        print(f"[{doc_type}] Done — {len(all_docs)} TN RERA orders ({from_year}–{to_year})")

    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        print(f"[{doc_type}] Error: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  DTCP KARNATAKA — CIRCULARS
# ════════════════════════════════════════════════════════════════════════════════

def scrape_dtcp_ka(doc_type, from_date_iso=None, to_date_iso=None):
    """Scrape DTCP Karnataka Government Circulars page.
    Single table, 6 cols: [sl_no, circular_no, title, pub_date, downloads, archive_date]."""
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    print(f"[{doc_type}] Fetching DTCP Karnataka Circulars")

    try:
        url = "http://www.dtcp.gov.in/en/circulars"
        html_text = fetch_simple(url)
        tables = re.findall(r'<table[^>]*>(.*?)</table>', html_text, re.S)
        if not tables:
            raise ValueError("No tables found")

        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tables[0], re.S)
        docs = []
        for row in rows:
            tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
            if len(tds) < 5:
                continue
            sl = _clean_text(tds[0])
            if not sl or not sl[0].isdigit():
                continue  # skip header

            circ_no = _clean_text(tds[1])
            title_text = _clean_text(tds[2])
            date_raw = _clean_text(tds[3])  # DD/MM/YYYY
            title = f"{circ_no} — {title_text}" if circ_no else title_text

            pdf_m = re.search(r'href="([^"]+)"', tds[4])
            pdf_url = ""
            if pdf_m:
                pdf_path = pdf_m.group(1)
                pdf_url = f"http://www.dtcp.gov.in{pdf_path}" if pdf_path.startswith("/") else pdf_path
            if not pdf_url:
                pdf_url = url  # fallback to page URL when no PDF link

            try:
                date_iso = datetime.strptime(date_raw.strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
                date_text = datetime.strptime(date_raw.strip(), "%d/%m/%Y").strftime("%d %b %Y")
            except Exception:
                date_iso = ""
                date_text = date_raw

            doc_id = f"dtcp_ka_{len(docs)}"
            docs.append({
                "date": date_text, "date_iso": date_iso,
                "title": title, "company": "",
                "page_url": url, "pdf_url": pdf_url,
                "type": doc_type, "id": doc_id,
            })

        if from_date_iso and to_date_iso:
            docs = [d for d in docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]

        cache[doc_type].update({"data": docs, "total": len(docs), "pages_done": 1, "fetching": False})
        print(f"[{doc_type}] Done — {len(docs)} DTCP Karnataka circulars")

    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        print(f"[{doc_type}] Error: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  MAHARASHTRA RERA — CIRCULARS
# ════════════════════════════════════════════════════════════════════════════════

def scrape_maha_rera(doc_type, from_date_iso=None, to_date_iso=None):
    """Scrape MahaRERA circulars — paginated (page=0 .. page=N).
    6 cols: [sno, circular_no, file_no, date(DD/MM/YYYY), description, pdf_size]."""
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    print(f"[{doc_type}] Fetching Maharashtra RERA Circulars")

    try:
        all_docs = []
        base_url = "https://maharera.maharashtra.gov.in/circular"

        for page_num in range(200):  # safety cap
            url = f"{base_url}?page={page_num}" if page_num > 0 else base_url
            html_text = fetch_simple(url)

            tables = re.findall(r'<table[^>]*>(.*?)</table>', html_text, re.S)
            if not tables:
                break

            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tables[0], re.S)
            page_docs = 0
            for row in rows:
                tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
                if len(tds) < 5:
                    continue

                sno = _clean_text(tds[0])
                if not sno or not sno[0].isdigit():
                    continue

                circ_no = _clean_text(tds[1])
                file_no = _clean_text(tds[2])
                date_raw = _clean_text(tds[3])
                desc = _clean_text(tds[4])

                title = f"{circ_no} — {desc}" if circ_no else desc

                pdf_m = re.search(r'href="([^"]+\.pdf[^"]*)"', row, re.I)
                pdf_url = ""
                if pdf_m:
                    pdf_path = pdf_m.group(1)
                    pdf_url = f"https://maharera.maharashtra.gov.in{pdf_path}" if pdf_path.startswith("/") else pdf_path

                try:
                    date_iso = datetime.strptime(date_raw.strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
                    date_text = datetime.strptime(date_raw.strip(), "%d/%m/%Y").strftime("%d %b %Y")
                except Exception:
                    date_iso = ""
                    date_text = date_raw

                doc_id = f"maharera_{len(all_docs)}"
                all_docs.append({
                    "date": date_text, "date_iso": date_iso,
                    "title": title, "company": file_no,
                    "page_url": url, "pdf_url": pdf_url,
                    "type": doc_type, "id": doc_id,
                })
                page_docs += 1

            # Update cache with FILTERED data so status checks are accurate
            if from_date_iso and to_date_iso:
                filtered = [d for d in all_docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]
            else:
                filtered = list(all_docs)
            cache[doc_type].update({"pages_done": page_num + 1, "total": len(filtered), "data": filtered,
                                     "fetch_started_at": time.time()})
            print(f"  [{doc_type}] page {page_num}: +{page_docs} docs (filtered: {len(filtered)})")

            if page_docs == 0:
                break
            # Early termination: if all docs on this page are before target date range, stop
            if from_date_iso:
                page_dates_maha = [d["date_iso"] for d in all_docs[-page_docs:] if d["date_iso"]]
                if page_dates_maha and all(d < from_date_iso for d in page_dates_maha):
                    print(f"  [{doc_type}] page {page_num}: all docs before {from_date_iso}, stopping")
                    break
            # Check if there's a next page link
            if f"page={page_num + 1}" not in html_text:
                break
            time.sleep(0.5)

        docs = all_docs
        if from_date_iso and to_date_iso:
            docs = [d for d in docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]

        cache[doc_type].update({"data": docs, "total": len(docs), "fetching": False})
        print(f"[{doc_type}] Done — {len(docs)} MahaRERA circulars")

    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        print(f"[{doc_type}] Error: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  KARNATAKA REAT & RERA — ORDERS
# ════════════════════════════════════════════════════════════════════════════════

_ka_html_cache = {"html": None, "ts": 0, "lock": threading.Lock()}

def _fetch_ka_html():
    """Fetch Karnataka tribunal page with caching so KA_REAT and KA_RERA don't
    hammer the same slow server simultaneously.  Falls back to curl if urllib fails."""
    with _ka_html_cache["lock"]:
        if _ka_html_cache["html"] and time.time() - _ka_html_cache["ts"] < 300:
            return _ka_html_cache["html"]
    url = "https://rera.karnataka.gov.in/tribunalDisposedList"
    try:
        html = fetch_simple(url, retries=4, timeout=90)
    except Exception:
        # Fallback: curl has different TLS fingerprint and may succeed
        r = subprocess.run(
            ['curl', '-s', '--compressed', '-L', '--max-time', '120',
             '--connect-timeout', '30',
             '-H', f'User-Agent: {SEBI_UA}', url],
            capture_output=True, timeout=140)
        if r.returncode != 0 or not r.stdout:
            raise
        html = r.stdout.decode('utf-8', 'ignore')
    with _ka_html_cache["lock"]:
        _ka_html_cache["html"] = html
        _ka_html_cache["ts"] = time.time()
    return html

def _scrape_ka_tribunal(doc_type, judgment_type, from_date_iso=None, to_date_iso=None):
    """Scrape Karnataka REAT or RERA orders from tribunalDisposedList.
    judgment_type = 'reat' → cols 8,9 (K-REAT date/copy), 'rera' → cols 6,7 (K-RERA date/copy).
    Table id='kreatList', single-quote hrefs: href='/download_jc?DOC_ID=...'  """
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    label = "K-REAT" if judgment_type == "reat" else "K-RERA"
    print(f"[{doc_type}] Fetching Karnataka {label} Orders")

    try:
        html_text = _fetch_ka_html()

        # Handle both single/double quotes, case-insensitive
        table_m = re.search(r'<table[^>]*id\s*=\s*["\']kreatList["\'][^>]*>(.*?)</table>', html_text, re.S | re.I)
        if not table_m:
            # Retry once — page is large (800KB+) and may not fully download
            print(f"[{doc_type}] kreatList not found on first try, retrying...")
            time.sleep(2)
            with _ka_html_cache["lock"]:
                _ka_html_cache["html"] = None  # invalidate cache
            html_text = _fetch_ka_html()
            table_m = re.search(r'<table[^>]*id\s*=\s*["\']kreatList["\'][^>]*>(.*?)</table>', html_text, re.S | re.I)
        if not table_m:
            raise ValueError("kreatList table not found after retry")

        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_m.group(1), re.S)
        docs = []
        date_col = 8 if judgment_type == "reat" else 6
        copy_col = 9 if judgment_type == "reat" else 7

        for row in rows:
            tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
            if len(tds) < 10:
                continue

            sno = _clean_text(tds[0])
            if not sno or not sno[0].isdigit():
                continue

            appeal_no = _clean_text(tds[1])
            fr_no = _clean_text(tds[2])
            petitioner = _clean_text(tds[3])
            respondent = _clean_text(tds[4])
            category = _clean_text(tds[5])
            date_raw = _clean_text(tds[date_col])  # DD-MM-YYYY

            # Extract download link (single-quote href)
            pdf_m = re.search(r"href='([^']+download_jc[^']*)'", tds[copy_col])
            if not pdf_m:
                continue  # No judgment copy yet

            pdf_path = pdf_m.group(1)
            pdf_url = f"https://rera.karnataka.gov.in{pdf_path}" if pdf_path.startswith("/") else pdf_path

            title = f"Appeal {appeal_no} — {petitioner} vs {respondent}"
            if category:
                title += f" ({category})"

            try:
                date_iso = datetime.strptime(date_raw.strip(), "%d-%m-%Y").strftime("%Y-%m-%d")
                date_text = datetime.strptime(date_raw.strip(), "%d-%m-%Y").strftime("%d %b %Y")
            except Exception:
                date_iso = ""
                date_text = date_raw

            doc_id = f"ka_{judgment_type}_{appeal_no.replace('/', '_')}_{len(docs)}"
            docs.append({
                "date": date_text, "date_iso": date_iso,
                "title": title, "company": respondent,
                "page_url": url, "pdf_url": pdf_url,
                "type": doc_type, "id": doc_id,
            })

        if from_date_iso and to_date_iso:
            docs = [d for d in docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]

        cache[doc_type].update({"data": docs, "total": len(docs), "pages_done": 1, "fetching": False})
        print(f"[{doc_type}] Done — {len(docs)} Karnataka {label} orders")

    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        print(f"[{doc_type}] Error: {e}")
        traceback.print_exc()


def scrape_ka_reat(doc_type, from_date_iso=None, to_date_iso=None):
    _scrape_ka_tribunal(doc_type, "reat", from_date_iso, to_date_iso)


def scrape_ka_rera(doc_type, from_date_iso=None, to_date_iso=None):
    """Scrape Karnataka K-RERA orders from the kreatList table.
    Both RERA and REAT orders share the same rows:
      RERA order → cols 6 (date) / 7 (pdf)
      REAT order → cols 8 (date) / 9 (pdf)
    Filter/display uses the K-RERA date from col 6."""
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    print(f"[{doc_type}] Fetching Karnataka K-RERA Orders (same rows as K-REAT)")

    try:
        html_text = _fetch_ka_html()

        table_m = re.search(r'<table[^>]*id\s*=\s*["\']kreatList["\'][^>]*>(.*?)</table>', html_text, re.S | re.I)
        if not table_m:
            print(f"[{doc_type}] kreatList not found on first try, retrying...")
            time.sleep(2)
            with _ka_html_cache["lock"]:
                _ka_html_cache["html"] = None  # invalidate cache
            html_text = _fetch_ka_html()
            table_m = re.search(r'<table[^>]*id\s*=\s*["\']kreatList["\'][^>]*>(.*?)</table>', html_text, re.S | re.I)
        if not table_m:
            raise ValueError("kreatList table not found after retry")

        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_m.group(1), re.S)
        docs = []

        for row in rows:
            tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
            if len(tds) < 10:
                continue
            sno = _clean_text(tds[0])
            if not sno or not sno[0].isdigit():
                continue

            # Use K-RERA date (col 6) for filtering and display
            rera_date_raw = _clean_text(tds[6]).strip()
            try:
                rera_iso  = datetime.strptime(rera_date_raw, "%d-%m-%Y").strftime("%Y-%m-%d")
                rera_text = datetime.strptime(rera_date_raw, "%d-%m-%Y").strftime("%d %b %Y")
            except Exception:
                continue  # No K-RERA date — skip row
            if from_date_iso and to_date_iso:
                if not (from_date_iso <= rera_iso <= to_date_iso):
                    continue  # K-RERA order is outside the selected month

            # Grab the K-RERA PDF from col 7
            pdf_m = re.search(r"href='([^']+download_jc[^']*)'", tds[7])
            if not pdf_m:
                continue  # No RERA order copy uploaded yet for this row

            pdf_path = pdf_m.group(1)
            pdf_url = f"https://rera.karnataka.gov.in{pdf_path}" if pdf_path.startswith("/") else pdf_path

            appeal_no  = _clean_text(tds[1])
            petitioner = _clean_text(tds[3])
            respondent = _clean_text(tds[4])
            category   = _clean_text(tds[5])
            title = f"Appeal {appeal_no} — {petitioner} vs {respondent}"
            if category:
                title += f" ({category})"

            doc_id = f"ka_rera_{appeal_no.replace('/', '_')}_{len(docs)}"
            docs.append({
                "date": rera_text, "date_iso": rera_iso,
                "title": title, "company": respondent,
                "page_url": url, "pdf_url": pdf_url,
                "type": doc_type, "id": doc_id,
            })

        cache[doc_type].update({"data": docs, "total": len(docs), "pages_done": 1, "fetching": False})
        print(f"[{doc_type}] Done — {len(docs)} Karnataka K-RERA orders (co-located with K-REAT)")

    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        print(f"[{doc_type}] Error: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  HARYANA REAT — RULINGS & JUDGEMENTS
# ════════════════════════════════════════════════════════════════════════════════

def scrape_hr_reat(doc_type, from_date_iso=None, to_date_iso=None):
    """Scrape Haryana REAT judgements from haryanarera.gov.in.
    Table id='compliant_hearing', 7 cols: [sno, appeal_no, appellant, respondent,
    date(YYYYMMDD DD-Mon-YYYY), view_judgement, upload_date].
    PDF in col-6: href='https://haryanarera.gov.in/assistancecontrol/viewOrderPdf/...'"""
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    print(f"[{doc_type}] Fetching Haryana REAT Judgements")

    try:
        url = "https://haryanarera.gov.in/admincontrol/judgements/3"
        html_text = fetch_simple(url)

        table_m = re.search(r'<table[^>]*id="compliant_hearing"[^>]*>(.*?)</table>', html_text, re.S)
        if not table_m:
            raise ValueError("compliant_hearing table not found")

        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_m.group(1), re.S)
        docs = []
        for row in rows:
            tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
            if len(tds) < 7:
                continue
            sno = _clean_text(tds[0])
            if not sno or not sno[0].isdigit():
                continue

            appeal_no = _clean_text(tds[1])
            appellant = _clean_text(tds[2])
            respondent = _clean_text(tds[3])

            # Date field: "20260217 17-Feb-2026"
            date_raw = _clean_text(tds[4])
            date_m = re.search(r'(\d{1,2}-[A-Za-z]{3}-\d{4})', date_raw)
            if not date_m:
                continue
            date_str = date_m.group(1)
            try:
                dt = datetime.strptime(date_str, "%d-%b-%Y")
                date_iso = dt.strftime("%Y-%m-%d")
                date_text = dt.strftime("%d %b %Y")
            except Exception:
                date_iso = ""
                date_text = date_str

            # PDF link in col 5 or 6 (View Judgement)
            pdf_m = re.search(r'href="(https?://[^"]*viewOrderPdf[^"]*)"', tds[5])
            if not pdf_m:
                pdf_m = re.search(r'href="(https?://[^"]*viewOrderPdf[^"]*)"', row)
            if not pdf_m:
                continue  # No judgement uploaded

            pdf_url = pdf_m.group(1)
            title = f"{appeal_no} — {appellant} vs {respondent}"

            doc_id = f"hr_reat_{appeal_no.replace(' ', '_').replace('/', '_')}_{len(docs)}"
            docs.append({
                "date": date_text, "date_iso": date_iso,
                "title": title, "company": respondent,
                "page_url": url, "pdf_url": pdf_url,
                "type": doc_type, "id": doc_id,
            })

        if from_date_iso and to_date_iso:
            docs = [d for d in docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]

        cache[doc_type].update({"data": docs, "total": len(docs), "pages_done": 1, "fetching": False})
        print(f"[{doc_type}] Done — {len(docs)} Haryana REAT judgements")

    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        print(f"[{doc_type}] Error: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  DELHI REAT — ORDERS FROM RERA
# ════════════════════════════════════════════════════════════════════════════════

def _dl_reat_fetch_page(url, ua=SEBI_UA):
    """Fetch a Delhi RERA page, tolerating HTTP 500 (site returns data with 500)."""
    req = urllib.request.Request(url, headers={'User-Agent': ua, 'Accept': 'text/html,*/*'})
    try:
        with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
            return r.read().decode('utf-8', errors='ignore')
    except urllib.error.HTTPError as e:
        # Delhi RERA returns HTTP 500 but the body still contains valid data
        if e.code == 500 and e.fp:
            return e.fp.read().decode('utf-8', errors='ignore')
        raise


def scrape_dl_reat(doc_type, from_date_iso=None, to_date_iso=None):
    """Scrape Delhi REAT orders from rera.delhi.gov.in.
    Table: 4 cols: [sno, date(DD/MM/YYYY), case_numbers, order_pdf_link].
    Paginated: 10 items/page, pages 0..N via ?page=N query param."""
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    print(f"[{doc_type}] Fetching Delhi REAT Orders")

    BASE_URL = "https://www.rera.delhi.gov.in/reat_cases_orders"

    try:
        docs = []
        page_num = 0
        max_pages = 500  # safety limit

        while page_num < max_pages:
            page_url = BASE_URL if page_num == 0 else f"{BASE_URL}?page={page_num}"

            try:
                html_text = _dl_reat_fetch_page(page_url)
            except Exception as e:
                if page_num == 0:
                    raise  # first page must work
                print(f"[{doc_type}] Stopped at page {page_num}: {e}")
                break

            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html_text, re.S)
            page_docs = 0
            for row in rows:
                tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
                if len(tds) < 4:
                    continue
                sno = _clean_text(tds[0])
                if not sno or not sno[0].isdigit():
                    continue

                date_raw = _clean_text(tds[1]).strip()  # DD/MM/YYYY
                title = _clean_text(tds[2])              # Case Numbers
                pdf_m = re.search(r'href="([^"]+\.pdf[^"]*)"', tds[3])
                if not pdf_m:
                    pdf_m = re.search(r'href="([^"]+\.pdf[^"]*)"', row)
                pdf_url = pdf_m.group(1) if pdf_m else ""
                if pdf_url and not pdf_url.startswith("http"):
                    pdf_url = f"https://www.rera.delhi.gov.in{pdf_url}"

                try:
                    dt = datetime.strptime(date_raw, "%d/%m/%Y")
                    date_iso = dt.strftime("%Y-%m-%d")
                    date_text = dt.strftime("%d %b %Y")
                except Exception:
                    date_iso = ""
                    date_text = date_raw

                doc_id = f"dl_reat_{len(docs)}"
                docs.append({
                    "date": date_text, "date_iso": date_iso,
                    "title": title, "company": "",
                    "page_url": page_url, "pdf_url": pdf_url,
                    "type": doc_type, "id": doc_id,
                })
                page_docs += 1

            cache[doc_type].update({"pages_done": page_num + 1, "total": len(docs)})
            # Heartbeat: reset watchdog timer on every page
            cache[doc_type]["fetch_started_at"] = time.time()

            if page_docs == 0:
                break  # no data rows on this page — we've passed the last page

            # Early termination: if all docs on this page are before our from-date, stop
            if from_date_iso:
                page_dates_dl = [d["date_iso"] for d in docs[-page_docs:] if d.get("date_iso")]
                if page_dates_dl and all(d < from_date_iso for d in page_dates_dl):
                    print(f"[{doc_type}] page {page_num}: all docs before {from_date_iso}, stopping early")
                    break

            # Check if there's a next page link
            if not re.search(r'class="pager-next"', html_text):
                break

            page_num += 1
            time.sleep(0.5)

        if from_date_iso and to_date_iso:
            docs = [d for d in docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]

        cache[doc_type].update({"data": docs, "total": len(docs), "pages_done": page_num + 1, "fetching": False})
        print(f"[{doc_type}] Done — {len(docs)} Delhi REAT orders across {page_num + 1} pages")

    except urllib.error.HTTPError as e:
        msg = f"Delhi RERA site down (HTTP {e.code})"
        cache[doc_type].update({"error": msg, "fetching": False})
        print(f"[{doc_type}] {msg}")
    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        print(f"[{doc_type}] Error: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  IRDAI — CONSOLIDATED & GAZETTE NOTIFIED REGULATIONS
# ════════════════════════════════════════════════════════════════════════════════

def scrape_irdai_regs(doc_type, from_date_iso=None, to_date_iso=None):
    """Scrape IRDAI Consolidated & Gazette Notified Regulations.
    Liferay table, 7 cols: [checkbox, archived_status, title, date(DD-MM-YYYY),
    description, file_no, hindi_title]. PDF links in cells."""
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    print(f"[{doc_type}] Fetching IRDAI Regulations")

    try:
        all_docs = []
        base_url = "https://irdai.gov.in/consolidated-gazette-notified-regulations"
        page_param = "_com_irdai_document_media_IRDAIDocumentMediaPortlet_cur"

        for page_num in range(1, 200):  # up to 199 pages
            url = f"{base_url}?{page_param}={page_num}"
            html_text = fetch_simple(url)

            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html_text, re.S)
            page_docs = 0
            for row in rows:
                tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
                if len(tds) < 6:
                    continue

                title = _clean_text(tds[2])
                date_raw = _clean_text(tds[3]).strip()
                file_no = _clean_text(tds[5])

                if not title or not date_raw or len(date_raw) != 10:
                    continue

                # PDF link — first href with download=true or .pdf
                pdf_m = re.search(r'href="([^"]+(?:download=true|\.pdf)[^"]*)"', row)
                pdf_url = pdf_m.group(1) if pdf_m else ""

                try:
                    dt = datetime.strptime(date_raw, "%d-%m-%Y")
                    date_iso = dt.strftime("%Y-%m-%d")
                    date_text = dt.strftime("%d %b %Y")
                except Exception:
                    date_iso = ""
                    date_text = date_raw

                slug = re.sub(r'[^a-z0-9]', '_', title.lower())[:40]
                doc_id = f"irdai_reg_{slug}_{len(all_docs)}"
                all_docs.append({
                    "date": date_text, "date_iso": date_iso,
                    "title": title, "company": file_no,
                    "page_url": url, "pdf_url": pdf_url,
                    "type": doc_type, "id": doc_id,
                })
                page_docs += 1

            # Update cache with FILTERED data so status checks are accurate
            if from_date_iso and to_date_iso:
                filtered_regs = [d for d in all_docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]
            else:
                filtered_regs = list(all_docs)
            cache[doc_type].update({"pages_done": page_num, "total": len(filtered_regs), "data": filtered_regs,
                                     "fetch_started_at": time.time()})
            print(f"  [{doc_type}] page {page_num}: +{page_docs} docs (filtered: {len(filtered_regs)})")

            if page_docs == 0:
                break
            # Early termination: if all docs on this page are before target date range, stop
            if from_date_iso:
                pg_dates = [d["date_iso"] for d in all_docs[-page_docs:] if d["date_iso"]]
                if pg_dates and all(d < from_date_iso for d in pg_dates):
                    print(f"  [{doc_type}] page {page_num}: all docs before {from_date_iso}, stopping")
                    break
            time.sleep(0.5)

        docs = all_docs
        if from_date_iso and to_date_iso:
            docs = [d for d in docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]

        cache[doc_type].update({"data": docs, "total": len(docs), "fetching": False})
        print(f"[{doc_type}] Done — {len(docs)} IRDAI regulations")

    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        print(f"[{doc_type}] Error: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  CCI — GREEN CHANNEL NOTICES
# ════════════════════════════════════════════════════════════════════════════════

def scrape_cci_green(doc_type, from_date_iso=None, to_date_iso=None):
    """Scrape CCI Green Channel Notices via DataTables server-side AJAX API.
    Returns JSON with {data: [{combination_no, party_name, notification_date,
    order_status, summary_file_content(JSON), ...}]}."""
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    print(f"[{doc_type}] Fetching CCI Green Channel Notices")

    try:
        url = "https://www.cci.gov.in/combination/green-channel"
        cols = ['DT_RowIndex', 'combination_no', 'party_name', 'form_type',
                'notification_date', 'order_status', 'summary_files']
        # NOTE: CCI's server-side fromdate/todate filter is broken (always returns 0
        # when dates are supplied). Fetch all records and filter locally instead.
        query = {'draw': '1', 'start': '0', 'length': '2000',
                 'searchString': '', 'search_type': '', 'fromdate': '', 'todate': ''}
        for i, c in enumerate(cols):
            query[f'columns[{i}][data]'] = c
            query[f'columns[{i}][name]'] = c
        query['order[0][column]'] = '0'
        query['order[0][dir]'] = 'desc'
        query['search[value]'] = ''
        query['search[regex]'] = 'false'

        q_str = urllib.parse.urlencode(query)
        req = urllib.request.Request(url + '?' + q_str, headers={
            'User-Agent': SEBI_UA,
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json'
        })

        with _urlopen_retry(req) as r:
            json_data = json.loads(r.read().decode('utf-8', errors='ignore'))

        docs = []
        for row in json_data.get('data', []):
            combo_no = _clean_text(row.get('combination_no', ''))
            party_name = _clean_text(row.get('party_name', ''))
            notif_date = row.get('notification_date', '').strip()
            status = _clean_text(row.get('order_status', ''))

            # PDF from summary_file_content JSON
            # The API returns both 'summary_files' (HTML) and 'summary_file_content' (JSON).
            # We prefer 'summary_file_content' which contains the actual file path JSON.
            pdf_url = ""
            sfc = row.get('summary_file_content') or row.get('summary_files')
            if sfc and str(sfc).strip() not in ('None', 'null', ''):
                try:
                    files = json.loads(html.unescape(str(sfc)))
                    if files and isinstance(files, list):
                        fname = files[0].get('file_name', '')
                        if fname:
                            pdf_url = "https://www.cci.gov.in/" + fname.lstrip('/').replace('\\/', '/').replace('\\', '/')
                except Exception:
                    pass

            try:
                dt = datetime.strptime(notif_date, "%d/%m/%Y")
                date_iso = dt.strftime("%Y-%m-%d")
                date_text = dt.strftime("%d %b %Y")
            except Exception:
                date_iso = row.get('decision_date', '')
                date_text = notif_date

            title = f"[{combo_no}] {party_name}"
            if status:
                title += f" — {status}"

            safe_no = re.sub(r'[^a-zA-Z0-9_-]', '_', combo_no)
            doc_id = f"cci_green_{safe_no}"
            docs.append({
                "date": date_text, "date_iso": date_iso,
                "title": title, "company": party_name,
                "page_url": url, "pdf_url": pdf_url,
                "type": doc_type, "id": doc_id,
            })

        if from_date_iso and to_date_iso:
            docs = [d for d in docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]

        cache[doc_type].update({"data": docs, "total": len(docs), "pages_done": 1, "fetching": False})
        print(f"[{doc_type}] Done — {len(docs)} CCI Green Channel notices")

    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        print(f"[{doc_type}] Error: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  TRAI — DIRECTIONS / REGULATIONS / RECOMMENDATIONS / CONSULTATION PAPERS
# ════════════════════════════════════════════════════════════════════════════════

def scrape_trai(doc_type, from_date_iso=None, to_date_iso=None):
    """Scrape TRAI publications (Drupal views-row, paginated).
    Extracts both PDF links (with aria-label) and non-PDF entries from views-rows.
    Date extracted from filename _DDMMYYYY.pdf, folder /YYYY-MM/, or page date spans.
    Paginated via ?page=0,1,2,..."""
    trai_path = SOURCES[doc_type]["trai_path"]
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    print(f"[{doc_type}] Fetching TRAI {trai_path}")

    try:
        all_docs = []
        seen_titles = set()  # dedup guard
        base_url = f"https://www.trai.gov.in/release-publication/{trai_path}"

        for page_num in range(300):  # safety cap
            url = f"{base_url}?page={page_num}" if page_num > 0 else base_url
            html_text = fetch_simple(url)

            # --- Method 1: PDF links with aria-label (most reliable) ---
            pdf_links = re.findall(
                r'<a\s+href="(/sites/default/files/[^"]+\.pdf)"[^>]*'
                r'aria-label="Download PDF for\s+(.+?)\s*-\s*\([\d.]+ [KMG]B\)[^"]*"',
                html_text, re.S
            )

            # --- Method 2: Extract date from views-row date spans ---
            # Each views-row can have <span class="date-display-single">DD/MM/YYYY</span>
            # or <div class="views-field views-field-field-date-of-release">
            row_dates = re.findall(
                r'class="date-display-single[^"]*"[^>]*>(\d{2}/\d{2}/\d{4})<',
                html_text
            )

            page_docs = 0
            for idx, (pdf_path, title_raw) in enumerate(pdf_links):
                pdf_url = f"https://www.trai.gov.in{pdf_path}"
                title = _clean_text(title_raw)
                if not title:
                    continue
                # Dedup by title
                title_key = re.sub(r'\s+', ' ', title.lower().strip())
                if title_key in seen_titles:
                    continue
                seen_titles.add(title_key)

                # Extract date (priority: filename → page date span → folder)
                date_iso = ""
                date_text = ""
                date_m = re.search(r'_(\d{2})(\d{2})(\d{4})\.pdf', pdf_path)
                if date_m:
                    dd, mm, yyyy = date_m.group(1), date_m.group(2), date_m.group(3)
                    try:
                        dt = datetime(int(yyyy), int(mm), int(dd))
                        date_iso = dt.strftime("%Y-%m-%d")
                        date_text = dt.strftime("%d %b %Y")
                    except Exception:
                        pass
                if not date_iso and idx < len(row_dates):
                    # Use date span from page
                    try:
                        dt = datetime.strptime(row_dates[idx], "%d/%m/%Y")
                        date_iso = dt.strftime("%Y-%m-%d")
                        date_text = dt.strftime("%d %b %Y")
                    except Exception:
                        pass
                if not date_iso:
                    folder_m = re.search(r'/(\d{4})-(\d{2})/', pdf_path)
                    if folder_m:
                        yyyy, mm = folder_m.group(1), folder_m.group(2)
                        date_iso = f"{yyyy}-{mm}-15"  # mid-month estimate
                        try:
                            date_text = datetime.strptime(f"{yyyy}-{mm}-15", "%Y-%m-%d").strftime("%b %Y")
                        except Exception:
                            date_text = f"{yyyy}-{mm}"

                slug = re.sub(r'[^a-z0-9]', '_', title.lower())[:40]
                doc_id = f"trai_{trai_path[:3]}_{slug}_{date_iso}"
                all_docs.append({
                    "date": date_text, "date_iso": date_iso,
                    "title": title, "company": "",
                    "page_url": base_url, "pdf_url": pdf_url,
                    "type": doc_type, "id": doc_id,
                })
                page_docs += 1

            # Update cache with FILTERED data (not raw) so status checks are accurate
            if from_date_iso and to_date_iso:
                filtered = [d for d in all_docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]
            else:
                filtered = list(all_docs)
            cache[doc_type].update({"pages_done": page_num + 1, "total": len(filtered), "data": filtered,
                                     "fetch_started_at": time.time()})
            print(f"  [{doc_type}] page {page_num}: +{page_docs} docs (filtered: {len(filtered)})")

            if page_docs == 0:
                break
            # Early termination: if all docs on this page are before our date range, stop
            if from_date_iso and page_docs > 0:
                page_dates = [d["date_iso"] for d in all_docs[-page_docs:] if d["date_iso"]]
                if page_dates and all(d < from_date_iso for d in page_dates):
                    print(f"  [{doc_type}] page {page_num}: all docs before {from_date_iso}, stopping")
                    break
            # Check if next page exists
            if f"page={page_num + 1}" not in html_text:
                break
            time.sleep(0.5)

        docs = all_docs
        if from_date_iso and to_date_iso:
            docs = [d for d in docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]

        cache[doc_type].update({"data": docs, "total": len(docs), "fetching": False})
        print(f"[{doc_type}] Done — {len(docs)} TRAI {trai_path}")

    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        print(f"[{doc_type}] Error: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  CGST — CIRCULARS
# ════════════════════════════════════════════════════════════════════════════════

def scrape_cgst(doc_type, from_date_iso=None, to_date_iso=None):
    """Scrape CGST Circulars from gstcouncil.gov.in.
    Table: 5 cols: [sno, circular_no, View(size), date(DD-MM-YYYY), description].
    Paginated via ?page=0,1,2,...
    Fixes: early termination, dedup by circular_no, filtered intermediate cache."""
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    print(f"[{doc_type}] Fetching CGST Circulars {'('+from_date_iso+' to '+to_date_iso+')' if from_date_iso else '(all)'}")

    try:
        all_docs = []
        seen_circ = set()  # dedup by circular number
        base_url = "https://gstcouncil.gov.in/cgst-circulars"

        for page_num in range(300):  # up to 300 pages
            url = f"{base_url}?page={page_num}" if page_num > 0 else base_url
            html_text = fetch_simple(url)

            tables = re.findall(r'<table[^>]*>(.*?)</table>', html_text, re.S)
            if not tables:
                break

            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tables[0], re.S)
            page_docs = 0
            page_dates = []
            for row in rows:
                tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
                if len(tds) < 5:
                    continue
                sno = _clean_text(tds[0])
                if not sno or not sno[0].isdigit():
                    continue

                circ_no = _clean_text(tds[1])
                desc = _clean_text(tds[4])
                date_raw = _clean_text(tds[3]).strip()  # DD-MM-YYYY
                title = f"{circ_no} — {desc}" if circ_no else desc

                # Dedup by circular number
                circ_key = circ_no.strip().lower()
                if circ_key and circ_key in seen_circ:
                    continue
                if circ_key:
                    seen_circ.add(circ_key)

                pdf_m = re.search(r'href="([^"]+\.pdf[^"]*)"', tds[2])
                pdf_url = ""
                if pdf_m:
                    pdf_path = pdf_m.group(1)
                    pdf_url = f"https://gstcouncil.gov.in{pdf_path}" if pdf_path.startswith("/") else pdf_path

                try:
                    dt = datetime.strptime(date_raw, "%d-%m-%Y")
                    date_iso = dt.strftime("%Y-%m-%d")
                    date_text = dt.strftime("%d %b %Y")
                except Exception:
                    date_iso = ""
                    date_text = date_raw

                if date_iso:
                    page_dates.append(date_iso)

                safe_circ = re.sub(r'[^a-zA-Z0-9_-]', '_', circ_no) if circ_no else str(len(all_docs))
                doc_id = f"cgst_{safe_circ}"
                all_docs.append({
                    "date": date_text, "date_iso": date_iso,
                    "title": title, "company": circ_no,
                    "page_url": url, "pdf_url": pdf_url,
                    "type": doc_type, "id": doc_id,
                })
                page_docs += 1

            # Update cache with FILTERED data so status checks are accurate
            if from_date_iso and to_date_iso:
                filtered = [d for d in all_docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]
            else:
                filtered = list(all_docs)
            cache[doc_type].update({"pages_done": page_num + 1, "total": len(filtered), "data": filtered,
                                     "fetch_started_at": time.time()})
            print(f"  [{doc_type}] page {page_num}: +{page_docs} docs (filtered: {len(filtered)})")

            if page_docs == 0:
                break
            # Early termination: if all docs on this page are before target date range, stop
            if from_date_iso and page_dates:
                if all(d < from_date_iso for d in page_dates):
                    print(f"  [{doc_type}] page {page_num}: all docs before {from_date_iso}, stopping")
                    break
            if f"page={page_num + 1}" not in html_text:
                break
            time.sleep(0.5)

        docs = all_docs
        if from_date_iso and to_date_iso:
            docs = [d for d in docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]

        cache[doc_type].update({"data": docs, "total": len(docs), "fetching": False})
        print(f"[{doc_type}] Done — {len(docs)} CGST circulars")

    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        print(f"[{doc_type}] Error: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  IBBI / NCLT — RESOLUTION PLAN & ADMISSION ORDERS
# ════════════════════════════════════════════════════════════════════════════════

def scrape_ibbi_nclt(doc_type, from_date_iso=None, to_date_iso=None):
    """Scrape IBBI NCLT orders (Resolution or Admission).
    Table: 4 cols: [sno, date(DD Mon, YYYY), title_with_onclick_pdf, type].
    PDF in onclick: javascript:newwindow1('/uploads/order/HASH.pdf').
    Paginated via ?page=N.
    Fixes: dedup by title+date+pdf, filtered intermediate cache."""
    ibbi_title = SOURCES[doc_type]["ibbi_title"]
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    print(f"[{doc_type}] Fetching IBBI NCLT {ibbi_title} Orders")

    try:
        all_docs = []
        seen_keys = set()  # dedup by title+date+pdf
        base_url = f"https://ibbi.gov.in/orders/nclt?title={ibbi_title}&date=&nclt="

        for page_num in range(1, 200):  # 1-indexed pages
            url = base_url if page_num == 1 else f"{base_url}&page={page_num}"
            html_text = fetch_simple(url)

            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html_text, re.S)
            page_docs = 0
            page_dates = []
            for row in rows:
                tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
                if len(tds) < 3:
                    continue
                sno = _clean_text(tds[0])
                if not sno or not sno[0].isdigit():
                    continue

                date_raw = _clean_text(tds[1]).strip()  # "03 Feb, 2026"
                title = _clean_text(tds[2])

                # PDF from onclick
                onclick_m = re.search(r"newwindow1\('([^']+\.pdf)'\)", row)
                pdf_url = ""
                if onclick_m:
                    pdf_path = onclick_m.group(1)
                    pdf_url = f"https://ibbi.gov.in{pdf_path}" if pdf_path.startswith("/") else pdf_path
                if not pdf_url:
                    pdf_url = url

                try:
                    dt = datetime.strptime(date_raw, "%d %b, %Y")
                    date_iso = dt.strftime("%Y-%m-%d")
                    date_text = dt.strftime("%d %b %Y")
                except Exception:
                    date_iso = ""
                    date_text = date_raw

                if date_iso:
                    page_dates.append(date_iso)

                # Dedup: skip if we've seen same title+date+pdf
                dedup_key = f"{title.lower().strip()}|{date_iso}|{pdf_url}"
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                # Use PDF hash for stable ID instead of counter
                pdf_hash = re.sub(r'[^a-zA-Z0-9]', '_', pdf_url.split('/')[-1])[:40] if pdf_url else str(len(all_docs))
                doc_id = f"ibbi_{ibbi_title[:3].lower()}_{pdf_hash}"
                all_docs.append({
                    "date": date_text, "date_iso": date_iso,
                    "title": title, "company": "",
                    "page_url": url, "pdf_url": pdf_url,
                    "type": doc_type, "id": doc_id,
                })
                page_docs += 1

            # Update cache with FILTERED data so status checks are accurate
            if from_date_iso and to_date_iso:
                filtered = [d for d in all_docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]
            else:
                filtered = list(all_docs)
            cache[doc_type].update({"pages_done": page_num, "total": len(filtered), "data": filtered})
            # Heartbeat: reset watchdog timer on each successful page
            cache[doc_type]["fetch_started_at"] = time.time()
            if page_num % 10 == 0:
                print(f"  [{doc_type}] page {page_num}: total {len(all_docs)} (filtered: {len(filtered)})")

            if page_docs == 0:
                break
            # Early termination: if all docs on this page are before our date range, stop
            if from_date_iso and page_dates:
                if all(d < from_date_iso for d in page_dates):
                    print(f"  [{doc_type}] page {page_num}: all docs before {from_date_iso}, stopping early")
                    break
            if f"page={page_num + 1}" not in html_text:
                break
            time.sleep(1.0)

        docs = all_docs
        if from_date_iso and to_date_iso:
            docs = [d for d in docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]

        cache[doc_type].update({"data": docs, "total": len(docs), "fetching": False, "error": None})
        print(f"[{doc_type}] Done — {len(docs)} IBBI NCLT {ibbi_title} orders")

    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        print(f"[{doc_type}] Error: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  EU COMMISSION — COMPETITION DECISIONS
# ════════════════════════════════════════════════════════════════════════════════

EU_COMP_BASE = "https://competition-cases.ec.europa.eu"
# CSDR Search API — config fetched from assets/env-json-config.json
_EU_COMP_SEARCH_URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
_EU_COMP_APIKEY     = "CS_PROD_ODSE_PROD"
# Attachment (decision PDF) base URL — from config modules.odse.attachmentUrl
_EU_COMP_ATTACH_BASE      = "https://ec.europa.eu/competition"
_EU_COMP_INSTRUMENT_FOLDER = {
    "M":             "mergers",
    "AT":            "antitrust",
    "SA":            "state_aid",
    "InstrumentDMA": "digital_markets_act",
    "InstrumentFS":  "foreign_subsidies",
}


def _eu_comp_search(instrument, page=1, page_size=100):
    """POST to CSDR search API; returns parsed JSON dict."""
    params = urllib.parse.urlencode({
        "apiKey":     _EU_COMP_APIKEY,
        "text":       "*",
        "pageNumber": page,
        "pageSize":   page_size,
    })
    url = f"{_EU_COMP_SEARCH_URL}?{params}"
    query = {"bool": {"must": [
        {"exists": {"field": "caseNumber"}},
        {"term":   {"caseInstrument":  instrument}},
        {"term":   {"metadataType":    "METADATA_CASE"}},
        {"exists": {"field": "caseLastDecisionDate"}},
    ]}}
    sort  = [{"field": "caseLastDecisionDate", "order": "DESC"}]
    boundary = "----EUCompBnd"
    def _part(name, data_bytes):
        return (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="blob"\r\n'
            f'Content-Type: application/json\r\n\r\n'.encode()
            + data_bytes + b"\r\n"
        )
    body = (
        _part("query", json.dumps(query).encode())
        + _part("sort",  json.dumps(sort).encode())
        + f"--{boundary}--\r\n".encode()
    )
    req = urllib.request.Request(url, data=body, headers={
        "User-Agent":   SEBI_UA,
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept":       "application/json",
        "Origin":       EU_COMP_BASE,
        "Referer":      f"{EU_COMP_BASE}/",
    }, method="POST")
    with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
        return json.loads(r.read().decode("utf-8", errors="ignore"))


def _eu_meta_first(metadata, key):
    """Return the first value of metadata[key] list, or empty string."""
    vals = metadata.get(key, [])
    return vals[0] if vals else ""


def _eu_comp_attachment_url(attachment_link, attachment_loc_type, case_instrument):
    """Build a full PDF URL from an attachment record.

    URLS locationType → link is already a full URL.
    DDOC / DOCS locationType → prepend base + instrument folder.
    """
    if not attachment_link:
        return ""
    if attachment_loc_type == "URLS" or re.match(r'^https?://', attachment_link):
        return attachment_link
    folder = _EU_COMP_INSTRUMENT_FOLDER.get(case_instrument, "")
    if folder:
        return f"{_EU_COMP_ATTACH_BASE}/{folder}/{attachment_link}"
    return ""


def _eu_comp_fetch_pdfs(case_numbers, instrument):
    """Batch-fetch METADATA_DECISION_ATTACHMENT records for the given case numbers.

    Returns a dict {caseNumber: pdf_url} (first/most recent PDF per case).
    """
    if not case_numbers:
        return {}
    q = {"bool": {"must": [
        {"terms": {"caseNumber": list(case_numbers)}},
        {"term":  {"metadataType": "METADATA_DECISION_ATTACHMENT"}},
        {"term":  {"caseInstrument": instrument}},
    ]}}
    sort = [{"field": "caseLastDecisionDate", "order": "DESC"}]
    page_size = min(len(case_numbers) * 5, 200)
    params = urllib.parse.urlencode({
        "apiKey": _EU_COMP_APIKEY, "text": "*", "pageNumber": 1,
        "pageSize": page_size,
    })
    url = f"{_EU_COMP_SEARCH_URL}?{params}"
    boundary = "----EUCompBnd"
    def _part(name, data_bytes):
        return (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="blob"\r\n'
            f'Content-Type: application/json\r\n\r\n'.encode()
            + data_bytes + b"\r\n"
        )
    body = (
        _part("query", json.dumps(q).encode())
        + _part("sort",  json.dumps(sort).encode())
        + f"--{boundary}--\r\n".encode()
    )
    req = urllib.request.Request(url, data=body, headers={
        "User-Agent":   SEBI_UA,
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept":       "application/json",
        "Origin":       EU_COMP_BASE,
        "Referer":      f"{EU_COMP_BASE}/",
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
            data = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as _pdf_exc:
        print(f"[eu_comp_fetch_pdfs] EXCEPTION fetching PDFs for {case_numbers}: {_pdf_exc}")
        return {}
    result = {}
    for row in data.get("results", []):
        meta = row.get("metadata", {})
        case_num = _eu_meta_first(meta, "caseNumber")
        if not case_num or case_num in result:
            continue   # one PDF per case — keep first (most recent)
        attachment_link = _eu_meta_first(meta, "attachmentLink")
        attachment_loc  = _eu_meta_first(meta, "attachmentLocationType")
        pdf_url = _eu_comp_attachment_url(attachment_link, attachment_loc, instrument)
        if pdf_url:
            result[case_num] = pdf_url
    return result


def scrape_eu_comp(doc_type, from_date_iso=None, to_date_iso=None):
    """Background thread — fetch EU Competition case decisions via CSDR search API.

    Uses multipart/form-data POST to api.tech.ec.europa.eu with apiKey.
    Deduplicates by case number (groupById) since the API returns one record
    per decision document, not per case.
    """
    src = SOURCES[doc_type]
    instrument  = src["eu_instrument"]
    eu_min_date = src.get("eu_min_date")   # e.g. "2004-05-01" for 2004 Merger Regulation

    # Always filter to active month when no explicit dates given (e.g. refresh without dates)
    if not from_date_iso or not to_date_iso:
        from_date_iso, to_date_iso, _, _ = _month_range(ACTIVE_MONTH['year'], ACTIVE_MONTH['month'])

    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    print(f"[{doc_type}] Fetching EU Competition decisions (instrument={instrument})")

    try:
        all_docs   = []
        seen_cases = set()     # deduplicate: groupById / caseNumber
        page_size  = 100
        stop       = False

        for page in range(1, 300):   # safety cap
            if stop:
                break

            data    = _eu_comp_search(instrument, page=page, page_size=page_size)
            results = data.get("results", [])

            if not results:
                break

            page_dates = []
            for result in results:
                meta       = result.get("metadata", {})
                case_number = _eu_meta_first(meta, "caseNumber")
                group_id    = result.get("groupById") or case_number

                # Skip duplicate case records (sorted DESC → first = most recent)
                if group_id and group_id in seen_cases:
                    continue
                if group_id:
                    seen_cases.add(group_id)

                decision_date_raw = _eu_meta_first(meta, "caseLastDecisionDate")
                if not decision_date_raw:
                    continue   # no decision yet — skip open/pending cases

                # "2026-03-08T23:00:00.000+0000" → "2026-03-08"
                date_str = str(decision_date_raw)[:10]
                try:
                    dt       = datetime.strptime(date_str, "%Y-%m-%d")
                    date_iso = dt.strftime("%Y-%m-%d")
                    date_txt = dt.strftime("%d %b %Y")
                except Exception:
                    date_iso = ""
                    date_txt  = date_str

                page_dates.append(date_iso)

                # 2004 Regulation cut-off for EU Mergers
                if eu_min_date and date_iso and date_iso < eu_min_date:
                    stop = True
                    break

                case_title    = _clean_text(_eu_meta_first(meta, "caseTitle"))
                decision_types = meta.get("decisionTypes", [])
                decision_type  = _clean_text(decision_types[0] if decision_types else "")

                parts = []
                if case_number:
                    parts.append(f"[{case_number}]")
                if case_title:
                    parts.append(case_title)
                if decision_type:
                    parts.append(f"— {decision_type}")
                title = " ".join(parts) or "EU Competition Decision"

                page_url = (f"{EU_COMP_BASE}/cases/{case_number}"
                            if case_number else EU_COMP_BASE)

                safe   = re.sub(r"[^a-zA-Z0-9_-]", "_", case_number or "")
                inst   = re.sub(r"[^a-z0-9]", "", instrument.lower())[:6]
                doc_id = f"eu_{inst}_{safe}"

                all_docs.append({
                    "date":        date_txt,
                    "date_iso":    date_iso,
                    "title":       title,
                    "company":     case_title,
                    "page_url":    page_url,
                    "pdf_url":     "",
                    "type":        doc_type,
                    "id":          doc_id,
                    "case_number": case_number,   # used for PDF lookup below
                })

            # Incremental cache update and watchdog reset
            cache[doc_type].update({"pages_done": page, "total": len(all_docs)})
            cache[doc_type]["fetch_started_at"] = time.time()

            # Last API page
            if len(results) < page_size:
                break

            # Entire page is older than our from-date window → stop early
            if from_date_iso and page_dates:
                if all(d < from_date_iso for d in page_dates if d):
                    break

            time.sleep(0.5)

        # Apply active-month date filter
        docs = all_docs
        if from_date_iso and to_date_iso:
            docs = [d for d in docs
                    if d.get("date_iso") and from_date_iso <= d["date_iso"] <= to_date_iso]

        # Fetch decision PDF URLs for the filtered cases
        if docs:
            case_nums = [d["case_number"] for d in docs if d.get("case_number")]
            pdf_map   = _eu_comp_fetch_pdfs(case_nums, instrument)
            print(f"[{doc_type}] PDF lookup: {len(case_nums)} cases → {len(pdf_map)} PDFs found: {list(pdf_map.keys())}")
            for d in docs:
                if d.get("case_number") in pdf_map:
                    d["pdf_url"] = pdf_map[d["case_number"]]

        # Remove internal-only field before caching
        for d in docs:
            d.pop("case_number", None)

        cache[doc_type].update({
            "data": docs, "total": len(docs),
            "fetching": False, "error": None,
        })
        print(f"[{doc_type}] Done — {len(docs)} EU decisions (instrument={instrument})")

    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        print(f"[{doc_type}] Error: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  EPO BOARD OF APPEAL DECISIONS
# ════════════════════════════════════════════════════════════════════════════════

_EPO_BOA_SEARCH_URL = "https://www.epo.org/boa-decisions/next/api/search"
_EPO_BOA_PDF_BASE   = "https://www.epo.org/boards-of-appeal/decisions/pdf"
_EPO_BOA_PAGE_BASE  = "https://www.epo.org/en/boards-of-appeal/decisions"

def scrape_epo_boa(doc_type, from_date_iso=None, to_date_iso=None):
    if not from_date_iso or not to_date_iso:
        from_date_iso, to_date_iso, _, _ = _month_range(ACTIVE_MONTH['year'], ACTIVE_MONTH['month'])
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    try:
        all_docs = []
        page = 1
        while True:
            payload = {
                "state": {
                    "searchTerm": "", "current": page, "resultsPerPage": 100,
                    "sortList": [{"field": "decision_dispatched.date", "direction": "desc"}],
                    "filters": [{"field": "decision_dispatched.date",
                                  "values": [{"from": from_date_iso, "to": to_date_iso}],
                                  "type": "all"}]
                },
                "queryConfig": {
                    "result_fields": {
                        "decision_title":            {"raw": {}},
                        "decision_case_number":      {"raw": {}},
                        "decision_board":            {"raw": {}},
                        "decision_date":             {"raw": {}},
                        "decision_dispatched":       {"raw": {}},
                        "url":                       {"raw": {}},
                        "decision_code_pattern":     {"raw": {}},
                        "decision_application_title":{"raw": {}},
                        "decision_euro_case_law_id": {"raw": {}},
                        "decision_keywords":         {"raw": {}},
                    },
                    "filters": []
                }
            }
            req = urllib.request.Request(
                _EPO_BOA_SEARCH_URL,
                data=json.dumps(payload).encode(),
                headers={
                    "User-Agent": SEBI_UA,
                    "Content-Type": "application/json",
                    "Eslastic-Search-Index": ".ent-search-engine-documents-boa-decisions",
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
                data = json.loads(r.read())
            results    = data.get("results", [])
            total_pages = data.get("totalPages", 1)
            for res in results:
                def _raw(field, _res=res): return (_res.get(field) or {}).get("raw", "")
                dispatched = _raw("decision_dispatched")   # "2026-03-09"
                date_str   = dispatched[:10] if dispatched else ""
                if not date_str:
                    continue
                try:
                    dt       = datetime.strptime(date_str, "%Y-%m-%d")
                    date_txt = dt.strftime("%d %b %Y")
                except Exception:
                    date_txt = date_str
                case_num  = _raw("decision_case_number")    # "T 0251/24"
                code_pat  = _raw("decision_code_pattern")   # "t240251eu1"
                app_title = _raw("decision_application_title")
                title     = f"{case_num} — {app_title}" if app_title else (case_num or _raw("decision_title"))
                page_url  = f"{_EPO_BOA_PAGE_BASE}/{code_pat}" if code_pat else ""
                pdf_url   = f"{_EPO_BOA_PDF_BASE}/{code_pat}.pdf" if code_pat else ""
                safe_id   = re.sub(r"[^a-zA-Z0-9_-]", "_", code_pat or case_num or date_str)
                all_docs.append({
                    "date":     date_txt,  "date_iso": date_str,
                    "title":    title,     "company":  app_title,
                    "page_url": page_url,  "pdf_url":  pdf_url,
                    "type":     doc_type,  "id":       f"epo_boa_{safe_id}",
                })
            cache[doc_type].update({"pages_done": page, "total": len(all_docs), "fetch_started_at": time.time()})
            if page >= total_pages:
                break
            page += 1
            time.sleep(0.5)
        cache[doc_type].update({"data": all_docs, "total": len(all_docs), "fetching": False, "error": None})
        print(f"[{doc_type}] Done — {len(all_docs)} EPO BOA decisions")
    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        print(f"[{doc_type}] Error: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  EDPB — DATA PROTECTION BOARD
# ════════════════════════════════════════════════════════════════════════════════

_EDPB_BASE = "https://www.edpb.europa.eu"
_EDPB_LOCK = threading.Lock()  # serialize all EDPB requests to avoid 403 from WAF

def _edpb_fetch(url, retries=5):
    """Fetch an EDPB page, retrying on 429/403 with exponential back-off."""
    import urllib.error as _ue
    delay = 15
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            })
            with urllib.request.urlopen(req, timeout=40, context=SSL_CTX) as r:
                return r.read().decode("utf-8", errors="ignore")
        except _ue.HTTPError as e:
            if e.code in (429, 403):
                retry_after = int(float(e.headers.get("Retry-After", delay)))
                wait = max(retry_after, delay)
                print(f"[EDPB] {e.code} on {url.split('/')[-1]}, waiting {wait}s (attempt {attempt+1}/{retries})")
                time.sleep(wait)
                delay = min(delay * 2, 120)
            else:
                raise
    raise RuntimeError(f"EDPB: still blocked after {retries} retries — {url}")


def scrape_edpb(doc_type, from_date_iso=None, to_date_iso=None):
    if not from_date_iso or not to_date_iso:
        from_date_iso, to_date_iso, _, _ = _month_range(ACTIVE_MONTH['year'], ACTIVE_MONTH['month'])
    src      = SOURCES[doc_type]
    base_url = src["edpb_url"]
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    try:
        all_docs = []
        page = 0
        with _EDPB_LOCK:  # serialize across all EDPB sources to avoid 403
            while True:
                url = base_url if page == 0 else f"{base_url}?page={page}"
                html_text = _edpb_fetch(url)
                titles = re.findall(r'<h4 class="node__title[^"]*">\s*<a href="([^"]+)"[^>]*title="([^"]+)"', html_text)
                dates  = re.findall(r'<span class="news-date[^"]*">([^<]+)</span>', html_text)
                pdfs   = re.findall(r'href="(/system/files/[^"]+\.pdf)"', html_text)
                if not titles:
                    break
                for i, (href, title) in enumerate(titles):
                    date_str_raw = dates[i].strip() if i < len(dates) else ""
                    try:
                        dt       = datetime.strptime(date_str_raw, "%d %B %Y")
                        date_iso = dt.strftime("%Y-%m-%d")
                        date_txt = dt.strftime("%d %b %Y")
                    except Exception:
                        date_iso = ""
                        date_txt = date_str_raw
                    pdf_url  = f"{_EDPB_BASE}{pdfs[i]}" if i < len(pdfs) else ""
                    page_url = f"{_EDPB_BASE}{href}"
                    safe_id  = re.sub(r"[^a-zA-Z0-9_-]", "_", href.rstrip("/").split("/")[-1])
                    all_docs.append({
                        "date":     date_txt,  "date_iso": date_iso,
                        "title":    title.strip(), "company": "",
                        "page_url": page_url,  "pdf_url":  pdf_url,
                        "type":     doc_type,  "id":       f"edpb_{safe_id}",
                    })
                cache[doc_type].update({"pages_done": page + 1, "total": len(all_docs), "fetch_started_at": time.time()})
                # Stop paginating when all entries on this page are older than our window
                page_dates = [d["date_iso"] for d in all_docs[-len(titles):] if d["date_iso"]]
                if from_date_iso and page_dates and all(d < from_date_iso for d in page_dates) and not src.get("no_month_filter"):
                    break
                page += 1
                time.sleep(3.0)   # edpb.europa.eu has aggressive rate limiting
        if src.get("no_month_filter"):
            docs = all_docs
        else:
            docs = [d for d in all_docs if d.get("date_iso") and from_date_iso <= d["date_iso"] <= to_date_iso]
        cache[doc_type].update({"data": docs, "total": len(docs), "fetching": False, "error": None})
        print(f"[{doc_type}] Done — {len(docs)} EDPB documents")
    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        print(f"[{doc_type}] Error: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  ADGM — ABU DHABI GLOBAL MARKET COURTS
# ════════════════════════════════════════════════════════════════════════════════

_ADGM_BASE       = "https://www.adgm.com"
_ADGM_API        = "https://www.adgm.com/JudgmentBlock/GetFilteredJudgmentBlockResponseDto"
_ADGM_COURT_LINK = "81205"   # CourtContentLink from the page JS; refresh if site rebuilds

def scrape_adgm(doc_type, from_date_iso=None, to_date_iso=None):
    if not from_date_iso or not to_date_iso:
        from_date_iso, to_date_iso, _, _ = _month_range(ACTIVE_MONTH['year'], ACTIVE_MONTH['month'])
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    try:
        # Try to refresh CourtContentLink dynamically from the listing page
        court_link = _ADGM_COURT_LINK
        try:
            main_req = urllib.request.Request(
                f"{_ADGM_BASE}/adgm-courts/judgments",
                headers={"User-Agent": SEBI_UA, "Accept": "text/html,*/*"}
            )
            with _urlopen_retry(main_req) as r:
                main_html = r.read().decode("utf-8", errors="ignore")
            cl_m = re.search(r'CourtContentLink\s*:\s*"(\d+)"', main_html)
            if cl_m:
                court_link = cl_m.group(1)
        except Exception:
            pass   # fall back to hardcoded value

        all_docs  = []
        page      = 1
        label_map = {
            "DateLabel": "Date", "DateWidth": 20,
            "CaseNumberLabel": "Case Number", "CaseNumberWidth": 20,
            "CaseNameLabel": "Case Name", "CaseNameWidth": 40,
            "NeutralCitationLabel": "Neutral Citation", "NeutralCitationWidth": 15,
            "JudgmentSummaryLabel": "Summary", "JudgmentSummaryWidth": 20,
        }
        while True:
            payload = json.dumps({
                "LabelAndWidth": label_map,
                "CaseType": "", "SearchQuery": "",
                "CourtContentLink": court_link,
                "ItemsPerPage": 100,
                "CurrentPage": page,
                "SortOption": "date#desc",
                "SortCourtFilter": 0,
                "FromDate": from_date_iso,
                "ToDate":   to_date_iso,
            }).encode("utf-8")
            req = urllib.request.Request(
                _ADGM_API, data=payload,
                headers={
                    "User-Agent":     SEBI_UA,
                    "Content-Type":   "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer":        f"{_ADGM_BASE}/adgm-courts/judgments",
                    "Origin":         _ADGM_BASE,
                    "Accept":         "text/html,*/*",
                },
                method="POST"
            )
            with _urlopen_retry(req) as r:
                html_chunk = r.read().decode("utf-8", errors="ignore")

            rows = re.findall(r"<adgm-table-row>(.*?)</adgm-table-row>", html_chunk, re.DOTALL)
            if not rows:
                break
            new_count = 0
            for row in rows:
                date_m = re.search(r'id="date">([^<]+)', row)
                case_m = re.search(r'id="caseNumber">([^<]+)', row)
                name_m = re.search(r'id="caseName">([^<]+)', row)
                if not date_m:
                    continue   # header row has no id="date"
                raw_date = date_m.group(1).strip()
                try:
                    dt       = datetime.strptime(raw_date, "%d %b %Y")
                    date_iso = dt.strftime("%Y-%m-%d")
                    date_txt = dt.strftime("%d %b %Y")
                except Exception:
                    date_iso = ""
                    date_txt = raw_date
                case_num = case_m.group(1).strip() if case_m else ""
                case_name = html.unescape(name_m.group(1).strip()) if name_m else ""
                title    = f"{case_num} — {case_name}" if case_name else case_num

                # Neutral citation link (e.g.  [2026] ADGMCFI 0010)
                pdf_hrefs = re.findall(r'href="(https://assets\.adgm\.com/download/assets/[^"]+)"', row)
                pdf_url   = html.unescape(pdf_hrefs[0]) if pdf_hrefs else ""

                safe_id  = re.sub(r"[^a-zA-Z0-9_-]", "_", case_num or date_iso)
                all_docs.append({
                    "date":     date_txt,   "date_iso": date_iso,
                    "title":    title,      "company":  "",
                    "page_url": f"{_ADGM_BASE}/adgm-courts/judgments",
                    "pdf_url":  pdf_url,
                    "type":     doc_type,   "id":       f"adgm_{safe_id}",
                })
                new_count += 1

            cache[doc_type].update({"pages_done": page, "total": len(all_docs), "fetch_started_at": time.time()})
            if new_count < 100:   # last page (fewer than max items)
                break
            page += 1
            time.sleep(1.0)

        docs = [d for d in all_docs if d.get("date_iso") and from_date_iso <= d["date_iso"] <= to_date_iso]
        cache[doc_type].update({"data": docs, "total": len(docs), "fetching": False, "error": None})
        print(f"[{doc_type}] Done — {len(docs)} ADGM documents")
    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        print(f"[{doc_type}] Error: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  DIFC — COURT OF APPEAL
# ════════════════════════════════════════════════════════════════════════════════

_DIFC_COA_BASE = "https://www.difccourts.ae"
_DIFC_COA_LIST = "/rules-decisions/judgments-orders/court-appeal"

_MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

def _parse_difc_date(raw):
    """Parse DIFC date like 'January 21, 2026  Court of Appeal - Orders'."""
    m = re.match(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})", raw.strip(), re.IGNORECASE)
    if not m:
        return "", raw.strip()
    month = _MONTH_NAMES[m.group(1).lower()]
    day   = int(m.group(2))
    year  = int(m.group(3))
    dt = datetime(year, month, day)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%d %b %Y")

def scrape_difc_ca(doc_type, from_date_iso=None, to_date_iso=None):
    if not from_date_iso or not to_date_iso:
        from_date_iso, to_date_iso, _, _ = _month_range(ACTIVE_MONTH['year'], ACTIVE_MONTH['month'])
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    try:
        all_docs = []
        page     = 1
        while True:
            url = f"{_DIFC_COA_BASE}{_DIFC_COA_LIST}"
            if page > 1:
                url += f"?ccm_paging_p={page}&ccm_order_by=ak_date&ccm_order_by_direction=desc"
            req = urllib.request.Request(url, headers={"User-Agent": SEBI_UA, "Accept": "text/html,*/*"})
            with _urlopen_retry(req) as r:
                page_html = r.read().decode("utf-8", errors="ignore")

            # Each case: <h4><a href="...">TITLE</a></h4>  <p class="label_small">DATE  TYPE</p>
            entries = re.findall(
                r'<h4[^>]*>\s*<a\s+href="([^"]+)"[^>]*>([^<]+)</a>\s*</h4>\s*'
                r'<p class="label_small"[^>]*>\s*([^<]+)</p>',
                page_html, re.DOTALL
            )
            if not entries:
                break

            page_oldest_iso = to_date_iso   # sentinel
            new_count = 0
            for href, title, label_text in entries:
                date_iso, date_txt = _parse_difc_date(label_text)
                if date_iso and date_iso < page_oldest_iso:
                    page_oldest_iso = date_iso
                safe_id  = re.sub(r"[^a-zA-Z0-9_-]", "_", href.rstrip("/").split("/")[-1])
                page_url = href if href.startswith("http") else f"{_DIFC_COA_BASE}{href}"
                all_docs.append({
                    "date":     date_txt,   "date_iso": date_iso,
                    "title":    title.strip(), "company":  "",
                    "page_url": page_url,   "pdf_url":  "",
                    "type":     doc_type,   "id":       f"difc_ca_{safe_id}",
                })
                new_count += 1

            cache[doc_type].update({"pages_done": page, "total": len(all_docs), "fetch_started_at": time.time()})
            # Stop when oldest date on this page is already before our window
            if page_oldest_iso < from_date_iso:
                break
            page += 1
            time.sleep(1.0)

        docs = [d for d in all_docs if d.get("date_iso") and from_date_iso <= d["date_iso"] <= to_date_iso]
        cache[doc_type].update({"data": docs, "total": len(docs), "fetching": False, "error": None})
        print(f"[{doc_type}] Done — {len(docs)} DIFC Court of Appeal documents")
    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        print(f"[{doc_type}] Error: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  MOHRE — UAE MINISTRY OF HUMAN RESOURCES & EMIRATISATION
# ════════════════════════════════════════════════════════════════════════════════

_MOHRE_BASE      = "https://www.mohre.gov.ae"
_MOHRE_LAWS_URL  = "/en/laws-and-regulations/laws"
_MOHRE_RES_URL   = "/en/laws-and-regulations/resolutions-and-circulars"
_MOHRE_API       = "/api/PublicApi/GetContentList"

# category IDs found in the hidden filter inputs on each page
_MOHRE_CAT_LAWS  = "1557"
_MOHRE_CAT_RES   = "1558"

def scrape_mohre(doc_type, from_date_iso=None, to_date_iso=None):
    """
    MOHRE Laws and Resolutions scraper.
    The site uses a client-side CMS (iCMS) that ordinarily loads content via
    JavaScript. We attempt the JSON API here; if successful we return filtered
    results, otherwise we return whatever the API provides (often empty for
    new sessions). The source is useful for all-time browsing via the source URL.
    """
    if not from_date_iso or not to_date_iso:
        from_date_iso, to_date_iso, _, _ = _month_range(ACTIVE_MONTH['year'], ACTIVE_MONTH['month'])
    src      = SOURCES[doc_type]
    page_path = src.get("mohre_path", _MOHRE_LAWS_URL)
    cat_id    = src.get("mohre_cat", _MOHRE_CAT_LAWS)
    no_filter = src.get("no_month_filter", False)

    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    try:
        # ── Set up a session cookie so the API accepts our calls ───────────────
        cj     = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=SSL_CTX),
            urllib.request.HTTPCookieProcessor(cj)
        )
        page_req = urllib.request.Request(
            f"{_MOHRE_BASE}{page_path}",
            headers={"User-Agent": SEBI_UA, "Accept": "text/html,*/*",
                     "Accept-Language": "en-US,en;q=0.9"}
        )
        csrf = ""
        try:
            with opener.open(page_req, timeout=30) as r:
                page_html = r.read().decode("utf-8", errors="ignore")
            csrf_m = re.search(
                r'<input[^>]+name=["\']__RequestVerificationToken["\'][^>]*value=["\']([^"\']+)["\']',
                page_html
            )
            csrf = csrf_m.group(1) if csrf_m else ""
        except Exception as _page_err:
            print(f"[{doc_type}] Page fetch skipped ({_page_err}), trying API without session")

        all_docs = []
        page     = 1
        while True:
            payload = json.dumps({
                "htmlTemplatePath": "ajax-templates/pages/legistlation.html",
                "loadResultAsHTML": False,
                "typeId":           25,
                "pageIndex":        page,
                "pageSize":         50,
                "languageId":       1,
                "languageCode":     "en-GB",
                "isArchived":       False,
                "imageSize":        "",
                "thumbnailSize":    "",
                "excludeItems":     [],
                "Sort": [
                    {"Key": "IsSticky", "Operator": "DESC"},
                    {"Key": "attr_year", "Operator": "DESC"},
                ],
                "FilterGroups": [{
                    "OR_AND_Operator": "AND",
                    "Filters": [
                        {"Key": "CategoriesIds", "Value": cat_id,    "Operator": "Equal",    "OR_AND_Operator": "AND"},
                        {"Key": "Status",        "Value": "Published","Operator": "Contains", "OR_AND_Operator": "AND"},
                        {"Key": "Status",        "Value": "Active",   "Operator": "Contains", "OR_AND_Operator": "AND"},
                        {"Key": "Status",        "Value": "NotArchived","Operator":"Contains","OR_AND_Operator": "AND"},
                    ],
                }],
            }).encode("utf-8")
            api_req = urllib.request.Request(
                f"{_MOHRE_BASE}{_MOHRE_API}", data=payload,
                headers={
                    "User-Agent":           SEBI_UA,
                    "Content-Type":         "application/json; charset=utf-8",
                    "Accept":               "application/json, text/javascript, */*; q=0.01",
                    "X-Requested-With":     "XMLHttpRequest",
                    "Referer":              f"{_MOHRE_BASE}{page_path}",
                    "Origin":               _MOHRE_BASE,
                    "RequestVerificationToken": csrf,
                }
            )
            with opener.open(api_req, timeout=20) as r:
                resp_raw = r.read().decode("utf-8", errors="ignore")

            obj    = json.loads(resp_raw)
            code   = obj.get("code", 500)
            if code != 200:
                break   # API not serving data (client-side rendering required)

            data_obj    = obj.get("data", {}) or {}
            contents    = data_obj.get("contents", [])
            total_pages = data_obj.get("totalPages", 1)

            for item in contents:
                title       = re.sub(r"<[^>]+>", "", item.get("title", "")).strip()
                raw_date    = (item.get("publishDate") or item.get("date") or item.get("createDate") or "")
                date_iso    = raw_date[:10] if raw_date else ""
                try:
                    dt       = datetime.fromisoformat(date_iso) if date_iso else None
                    date_txt = dt.strftime("%d %b %Y") if dt else date_iso
                except Exception:
                    date_txt = date_iso
                page_url = item.get("url") or item.get("link") or item.get("pageUrl") or f"{_MOHRE_BASE}{page_path}"
                if page_url and not page_url.startswith("http"):
                    page_url = _MOHRE_BASE + page_url
                pdf_url  = item.get("fileUrl") or item.get("pdfUrl") or ""
                safe_id  = re.sub(r"[^a-zA-Z0-9_-]", "_", (item.get("id") or title or date_iso)[:60])
                all_docs.append({
                    "date":     date_txt,   "date_iso": date_iso,
                    "title":    title,      "company":  "",
                    "page_url": page_url,   "pdf_url":  pdf_url,
                    "type":     doc_type,   "id":       f"mohre_{safe_id}",
                })

            cache[doc_type].update({"pages_done": page, "total": len(all_docs), "fetch_started_at": time.time()})
            if page >= total_pages:
                break
            page += 1
            time.sleep(1.0)

        if no_filter:
            docs = all_docs
        else:
            docs = [d for d in all_docs if not d.get("date_iso") or (from_date_iso <= d["date_iso"] <= to_date_iso)]

        cache[doc_type].update({"data": docs, "total": len(docs), "fetching": False, "error": None})
        print(f"[{doc_type}] Done — {len(docs)} MOHRE documents")
    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        print(f"[{doc_type}] Error: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  DOWNLOAD
# ════════════════════════════════════════════════════════════════════════════════

def _referer_for(pdf_url, doc_type):
    """Pick an appropriate Referer header based on the source or URL domain."""
    if "BSE" in doc_type:
        return BSE_BASE
    if "sebi.gov.in" in pdf_url:
        return SEBI_BASE
    if "rbi.org.in" in pdf_url:
        return "https://www.rbi.org.in/"
    # Extract scheme+host from the PDF URL itself
    m = re.match(r'(https?://[^/]+)', pdf_url)
    return m.group(1) if m else SEBI_BASE


def _curl_download(pdf_url, tmp_path, referer):
    """Download using system curl with HTTP/2 support.
    Used for servers (e.g. rbidocs.rbi.org.in) that reject urllib's HTTP/1.1.
    Note: rbidocs.rbi.org.in also rejects Referer headers, so we omit it.
    Returns (success: bool, error_msg: str)."""
    import subprocess
    cmd = [
        'curl', '-s', '-L', '--http2',
        '--max-time', '180',
        '--retry', '0',          # we handle retries ourselves
        '-H', f'User-Agent: {SEBI_UA}',
        '-H', 'Accept: application/pdf,*/*',
        # No Referer — rbidocs.rbi.org.in returns empty reply if Referer is set
        '--output', tmp_path,
        pdf_url,
    ]
    try:
        result = subprocess.run(cmd, timeout=190, capture_output=True)
        if result.returncode != 0:
            return False, f"curl exit {result.returncode}: {result.stderr.decode(errors='replace')[:200]}"
        if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) < 500:
            size = os.path.getsize(tmp_path) if os.path.exists(tmp_path) else 0
            return False, f"Downloaded file too small ({size} bytes)"
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "curl timeout"
    except FileNotFoundError:
        return False, "curl not found on system"
    except Exception as e:
        return False, str(e)


# Domains that require HTTP/2 (urllib doesn't support it; use curl fallback)
_HTTP2_DOMAINS = ()  # rbidocs.rbi.org.in blocked by F5 TSPD bot-protection; curl doesn't help either


def download_pdf(doc_id, pdf_url, filename, doc_type):
    folder = SOURCES[doc_type]["folder"]
    try:
        os.makedirs(folder, exist_ok=True)
    except Exception as e:
        print(f"[DL] makedirs failed for {folder!r}: {e}")

    safe = re.sub(r'[<>:"/\\|?*\0]', '', filename).strip('. ')
    safe = re.sub(r'\s+', ' ', safe)
    if not safe.lower().endswith('.pdf'):
        safe += '.pdf'
    if len(safe) > 200:
        safe = safe[:195] + '.pdf'

    # Avoid filename collisions: if file already exists, append doc_id
    filepath = os.path.join(folder, safe)
    if os.path.exists(filepath):
        base, ext = os.path.splitext(safe)
        safe = f"{base}_{doc_id}{ext}"
        filepath = os.path.join(folder, safe)

    tmp_path = filepath + '.tmp'
    # Preserve any citation metadata already stored (e.g. from queueing step)
    _meta = download_progress.get(doc_id, {})
    download_progress[doc_id] = {
        "status": "downloading", "filename": safe, "type": doc_type,
        "title":    _meta.get("title",    safe),
        "date":     _meta.get("date",     ""),
        "page_url": _meta.get("page_url", ""),
        "pdf_url":  pdf_url,
    }

    ua = BSE_UA if "BSE" in doc_type else SEBI_UA
    needs_http2 = any(d in pdf_url for d in _HTTP2_DOMAINS)
    last_dl_err = None
    MAX_ATTEMPTS = 5
    # Exponential backoff: 5, 10, 20, 40, 80 s; don't retry bot-protection pages
    for dl_attempt in range(MAX_ATTEMPTS):
        if dl_attempt > 0:
            _prev = download_progress.get(doc_id, {})
            download_progress[doc_id] = {"status": "retrying", "filename": safe, "type": doc_type,
                                          "attempt": dl_attempt + 1, "attempt_max": MAX_ATTEMPTS,
                                          "title":    _prev.get("title", safe),
                                          "date":     _prev.get("date", ""),
                                          "page_url": _prev.get("page_url", ""),
                                          "pdf_url":  pdf_url}
            wait = min(5 * (2 ** (dl_attempt - 1)), 80)  # 5,10,20,40,80
            print(f"[DL RETRY] {doc_type}/{safe} attempt {dl_attempt + 1}/{MAX_ATTEMPTS}, waiting {wait}s...")
            time.sleep(wait)
        _download_sem.acquire()
        try:
            try:
                referer = _referer_for(pdf_url, doc_type)
                if needs_http2:
                    # Server requires HTTP/2; urllib only does HTTP/1.1 → use curl
                    ok, err_msg = _curl_download(pdf_url, tmp_path, referer)
                    if not ok:
                        raise ValueError(f"curl error: {err_msg}")
                else:
                    req = urllib.request.Request(pdf_url, headers={
                        'User-Agent': ua, 'Accept': 'application/pdf,*/*',
                        'Referer': referer,
                    })
                    # Stream download in 64 KB chunks — avoids loading large PDFs into memory
                    with urllib.request.urlopen(req, timeout=180, context=SSL_CTX) as resp:
                        with open(tmp_path, 'wb') as f:
                            while True:
                                chunk = resp.read(65536)
                                if not chunk:
                                    break
                                f.write(chunk)

                file_size = os.path.getsize(tmp_path)
                if file_size < 500:
                    raise ValueError(f"File too small ({file_size} bytes) — not a valid PDF")

                # Validate: check PDF magic bytes; reject HTML error pages
                with open(tmp_path, 'rb') as f:
                    header = f.read(8)
                if not header[:5].startswith(b'%PDF'):
                    with open(tmp_path, 'rb') as f:
                        first_500 = f.read(500)
                    first_text = first_500.lower()
                    # F5 TSPD bot-protection challenge (rbidocs.rbi.org.in and others)
                    # Mark as permanent error — retrying won't help
                    if b'tspd' in first_text or b'please enable javascript' in first_text or b'bobcmn' in first_text:
                        err = ValueError(
                            "Bot-protection active on this server — click \"Open PDF\" below "
                            "to download manually in your browser."
                        )
                        err._no_retry = True
                        raise err
                    if b'<html' in first_text or b'<!doctype' in first_text:
                        raise ValueError("Server returned an HTML page instead of a PDF")

                # Atomic rename — no partial files visible in the folder
                os.replace(tmp_path, filepath)
                size_kb = file_size // 1024
                _m = download_progress.get(doc_id, {})
                download_progress[doc_id] = {
                    "status": "done", "filename": safe, "size_kb": size_kb, "type": doc_type,
                    "title":    _m.get("title",    safe),
                    "date":     _m.get("date",     ""),
                    "page_url": _m.get("page_url", ""),
                    "pdf_url":  pdf_url,
                }
                print(f"[DL OK] {doc_type}/{safe} ({size_kb} KB)")
                last_dl_err = None
                break

            except Exception as e:
                last_dl_err = e
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass
                print(f"[DL FAIL] attempt {dl_attempt + 1}/{MAX_ATTEMPTS}: {doc_type}/{safe} — {e}")
                if getattr(e, '_no_retry', False):
                    break  # Bot-protection / permanent error — don't waste retries
        finally:
            _download_sem.release()

    if last_dl_err:
        _m = download_progress.get(doc_id, {})
        download_progress[doc_id] = {
            "status": "error", "error": str(last_dl_err), "filename": safe, "type": doc_type,
            "title":    _m.get("title",    safe),
            "date":     _m.get("date",     ""),
            "page_url": _m.get("page_url", ""),
            "pdf_url":  pdf_url,
        }
        print(f"[DL ERR] {doc_type}/{safe} — all attempts failed: {last_dl_err}")


def resolve_and_download(doc_id, pdf_url, page_url, title, doc_type):
    """For SEBI docs, auto-resolve PDF URL if needed, then download."""
    _prev = download_progress.get(doc_id, {})
    _meta = {"filename": title, "type": doc_type,
             "title": _prev.get("title", title), "date": _prev.get("date", ""),
             "page_url": _prev.get("page_url", page_url), "pdf_url": _prev.get("pdf_url", pdf_url)}
    url = pdf_url
    if not url and page_url and "sebi.gov.in" in page_url:
        download_progress[doc_id] = {**_meta, "status": "resolving"}
        url = get_sebi_pdf_url(page_url)
        if url:
            _meta["pdf_url"] = url
            for d in cache.get(doc_type, {}).get("data", []):
                if d["id"] == doc_id:
                    d["pdf_url"] = url
                    break
        else:
            download_progress[doc_id] = {**_meta, "status": "error", "error": "PDF not found on page"}
            return
    if not SOURCES.get(doc_type):
        download_progress[doc_id] = {**_meta, "status": "error", "error": f"Unknown source type: {doc_type}"}
        return
    if url:
        download_pdf(doc_id, url, title, doc_type)
    else:
        download_progress[doc_id] = {**_meta, "status": "error", "error": "No PDF URL"}


# ════════════════════════════════════════════════════════════════════════════════
#  HTTP HANDLER
# ════════════════════════════════════════════════════════════════════════════════

# ── UK Tribunal scrapers ──────────────────────────────────────────────────────

_GOVUK_BASE = "https://www.gov.uk"

def scrape_govuk_finder(doc_type, from_date_iso=None, to_date_iso=None):
    """GOV.UK finder-frontend scraper (Employment Tribunal, Appeals, CMA, Tax & Chancery).
    Results are server-rendered HTML; date filters applied via URL params.
    PDF links are on individual decision detail pages."""
    if not from_date_iso or not to_date_iso:
        from_date_iso, to_date_iso, _, _ = _month_range(ACTIVE_MONTH['year'], ACTIVE_MONTH['month'])
    src         = SOURCES[doc_type]
    govuk_base  = src["govuk_base"]
    govuk_params = src.get("govuk_params", "")
    date_param  = src.get("govuk_date_param", "tribunal_decision_decision_date")
    final_only  = src.get("govuk_final_only", False)

    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    try:
        from_dt  = datetime.fromisoformat(from_date_iso)
        to_dt    = datetime.fromisoformat(to_date_iso)

        def _fetch_listing_pages(from_dd, to_dd):
            """Paginate the GOV.UK finder listing for the given date range."""
            docs = []
            page = 1
            while True:
                date_qs = f"{date_param}%5Bfrom%5D={from_dd}&{date_param}%5Bto%5D={to_dd}&page={page}"
                url = f"{_GOVUK_BASE}/{govuk_base}?{govuk_params + '&' if govuk_params else ''}{date_qs}"
                req = urllib.request.Request(url, headers={
                    "User-Agent": SEBI_UA, "Accept": "text/html,*/*",
                    "Accept-Language": "en-US,en;q=0.9",
                })
                with _urlopen_retry(req) as r:
                    body = r.read().decode("utf-8", errors="replace")

                # Each result is wrapped in <li class="gem-c-document-list__item...">
                items = re.findall(
                    r'<li[^>]+class="[^"]*gem-c-document-list__item[^"]*"[^>]*>(.*?)</li>',
                    body, re.DOTALL
                )
                if not items:
                    break

                for item_html in items:
                    title_m = re.search(r'href="(/[^"]+)"[^>]*>\s*(.*?)\s*</a>', item_html, re.DOTALL)
                    date_m  = re.search(r'<time[^>]+datetime="([^"]+)"', item_html)
                    if not title_m:
                        continue
                    href      = title_m.group(1)
                    title     = re.sub(r"<[^>]+>", "", html.unescape(title_m.group(2))).strip()
                    date_iso  = date_m.group(1)[:10] if date_m else ""
                    try:
                        date_txt = datetime.fromisoformat(date_iso).strftime("%d %b %Y") if date_iso else date_iso
                    except Exception:
                        date_txt = date_iso
                    page_url = f"{_GOVUK_BASE}{href}"
                    doc_id   = re.sub(r"[^a-zA-Z0-9_-]", "_", href.strip("/"))[-60:]
                    docs.append({
                        "date": date_txt, "date_iso": date_iso,
                        "title": title,   "company": "",
                        "page_url": page_url, "pdf_url": "",
                        "type": doc_type, "id": f"govuk_{doc_id}",
                    })

                cache[doc_type].update({"pages_done": page, "total": len(docs), "fetch_started_at": time.time()})
                # Stop if no next-page hint in the rendered HTML
                if f"page={page + 1}" not in body:
                    break
                page += 1
                time.sleep(0.5)
            return docs

        from_dd = from_dt.strftime("%d/%m/%Y")
        to_dd   = to_dt.strftime("%d/%m/%Y")
        all_docs = _fetch_listing_pages(from_dd, to_dd)

        # Fetch detail pages to resolve PDF links — parallelised for speed
        def _fetch_detail(doc):
            try:
                det_req = urllib.request.Request(doc["page_url"], headers={
                    "User-Agent": SEBI_UA, "Accept": "text/html,*/*",
                })
                with _urlopen_retry(det_req, timeout=20) as det_r:
                    det_body = det_r.read().decode("utf-8", errors="replace")

                # Collect every assets PDF URL on the page (handles both real and
                # JSON-escaped href attributes)
                all_urls = re.findall(
                    r'https://assets\.publishing\.service\.gov\.uk/[^\s"\'\\<>]+\.pdf',
                    det_body, re.I
                )

                if final_only:
                    # Score each PDF by how authoritative it is:
                    # 4 = final report  3 = full text / final decision
                    # 2 = final (other)  1 = any decision  0 = other
                    best_url, best_score = '', -1
                    for url in all_urls:
                        fname = url.split('/')[-1].lower()
                        idx   = det_body.find(url)
                        ctx   = det_body[max(0, idx - 250):idx].lower()
                        if 'final report' in ctx or 'final_report' in fname or 'final-report' in fname:
                            score = 4
                        elif 'full_text_decision' in fname or 'full text decision' in ctx or 'full-text-decision' in fname:
                            score = 3
                        elif 'final_decision' in fname or 'final decision' in ctx or 'final-decision' in fname:
                            score = 3
                        elif 'final' in fname and ('decision' in fname or 'report' in fname):
                            score = 2
                        elif 'final' in ctx and ('decision' in ctx or 'report' in ctx):
                            score = 2
                        elif 'decision' in fname or 'decision' in ctx:
                            score = 1
                        else:
                            score = 0
                        if score > best_score:
                            best_score, best_url = score, url
                    # Only keep docs that have at least some decision/final PDF
                    if best_url and best_score >= 1:
                        doc["pdf_url"] = html.unescape(best_url)
                else:
                    if all_urls:
                        doc["pdf_url"] = html.unescape(all_urls[0])
            except Exception:
                pass

        with ThreadPoolExecutor(max_workers=15) as det_pool:
            list(det_pool.map(_fetch_detail, all_docs))

        # For final-report-only sources, exclude cases that have no qualifying PDF
        if final_only:
            all_docs = [d for d in all_docs if d["pdf_url"]]

        # Fallback: if the primary date range yielded no qualifying results (empty
        # list or all items had no decision PDF), widen to govuk_fallback_months.
        # This handles months where no enforcement cases were formally closed, or
        # where only advisory/procedural referrals appeared (no decision PDFs).
        fallback_months = src.get("govuk_fallback_months", 0)
        if not all_docs and fallback_months:
            expanded_from = to_dt - timedelta(days=fallback_months * 30)
            fallback_docs = _fetch_listing_pages(
                expanded_from.strftime("%d/%m/%Y"), to_dd
            )
            with ThreadPoolExecutor(max_workers=15) as det_pool:
                list(det_pool.map(_fetch_detail, fallback_docs))
            if final_only:
                fallback_docs = [d for d in fallback_docs if d["pdf_url"]]
            all_docs = fallback_docs

        cache[doc_type].update({"data": all_docs, "total": len(all_docs), "fetching": False})
    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        traceback.print_exc()


_CAT_BASE = "https://www.catribunal.org.uk"

def scrape_uk_cat(doc_type, from_date_iso=None, to_date_iso=None):
    """UK Competition Appeal Tribunal judgments.
    PDF links appear directly on the listing page; date is parsed from the filename."""
    if not from_date_iso or not to_date_iso:
        from_date_iso, to_date_iso, _, _ = _month_range(ACTIVE_MONTH['year'], ACTIVE_MONTH['month'])

    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    try:
        from_year = int(from_date_iso[:4])
        to_year   = int(to_date_iso[:4])

        all_docs = []
        for year in range(from_year, to_year + 1):
            page = 0  # Drupal uses 0-based page index
            while True:
                url = f"{_CAT_BASE}/judgments?query=&neutral_citation_year={year}&page={page}"
                req = urllib.request.Request(url, headers={
                    "User-Agent": SEBI_UA, "Accept": "text/html,*/*",
                })
                with _urlopen_retry(req) as r:
                    body = r.read().decode("utf-8", errors="replace")

                entries = re.findall(r'/sites/cat/files/(\d{4}-\d{2})/([^"\']+\.pdf)', body)
                if not entries:
                    break

                for folder, enc_filename in entries:
                    filename = urllib.parse.unquote(enc_filename).strip()
                    # Date appears at end of filename: "DD Mon YYYY" before .pdf
                    date_m = re.search(r'(\d{1,2}\s+\w+\s+\d{4})\s*(?:_\d+)?\.pdf$', filename, re.I)
                    if not date_m:
                        date_m = re.search(r'(\d{1,2}\s+\w+\s+\d{4})', filename)
                    date_txt = date_m.group(1).strip() if date_m else folder
                    date_iso = ""
                    if date_m:
                        for fmt in ("%d %b %Y", "%d %B %Y"):
                            try:
                                date_iso = datetime.strptime(date_txt, fmt).strftime("%Y-%m-%d")
                                break
                            except Exception:
                                pass
                    if not date_iso:
                        date_iso = f"{folder}-01"

                    # Title = filename minus trailing date, suffix, and .pdf
                    title = re.sub(r'\s+\d{1,2}\s+\w+\s+\d{4}[^.]*\.pdf$', '', filename, flags=re.I).strip()
                    if title.lower().endswith('.pdf'):
                        title = title[:-4]
                    title = title.rstrip(" -_")

                    pdf_url = f"{_CAT_BASE}/sites/cat/files/{folder}/{enc_filename}"
                    doc_id  = re.sub(r"[^a-zA-Z0-9_-]", "_", f"{folder}_{filename[:40]}")
                    all_docs.append({
                        "date": date_txt, "date_iso": date_iso,
                        "title": title,   "company": "",
                        "page_url": f"{_CAT_BASE}/judgments",
                        "pdf_url": pdf_url,
                        "type": doc_type, "id": f"cat_{doc_id}",
                    })

                cache[doc_type].update({"pages_done": page + 1, "total": len(all_docs), "fetch_started_at": time.time()})
                if f"page={page + 1}" not in body:
                    break
                page += 1
                time.sleep(0.5)

        docs = [d for d in all_docs if not d["date_iso"] or (from_date_iso <= d["date_iso"] <= to_date_iso)]
        cache[doc_type].update({"data": docs, "total": len(docs), "fetching": False})
    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})


_UTIAC_BASE = "https://tribunalsdecisions.service.gov.uk"

def scrape_utiac(doc_type, from_date_iso=None, to_date_iso=None):
    """UK Immigration & Asylum Chamber (Upper Tribunal) reported decisions.
    The search requires search[query]= to be present to avoid a 500 error."""
    if not from_date_iso or not to_date_iso:
        from_date_iso, to_date_iso, _, _ = _month_range(ACTIVE_MONTH['year'], ACTIVE_MONTH['month'])

    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    try:
        cj     = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=SSL_CTX),
            urllib.request.HTTPCookieProcessor(cj),
        )
        # Initialise session cookie
        opener.open(urllib.request.Request(
            f"{_UTIAC_BASE}/utiac", headers={"User-Agent": SEBI_UA}
        ), timeout=20).close()

        all_docs = []
        page = 1
        stop = False
        while not stop:
            url = (f"{_UTIAC_BASE}/utiac?"
                   f"search%5Bquery%5D=&search%5Breported%5D=true&page={page}")
            req = urllib.request.Request(url, headers={
                "User-Agent": SEBI_UA, "Accept": "text/html,*/*",
                "Referer": f"{_UTIAC_BASE}/utiac",
            })
            with opener.open(req, timeout=20) as r:
                body = r.read().decode("utf-8", errors="replace")

            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', body, re.DOTALL)
            if len(rows) <= 1:
                break

            data_rows = rows[1:]  # skip header
            new_count = 0
            i = 0
            while i < len(data_rows):
                row1 = data_rows[i]
                row2 = data_rows[i + 1] if i + 1 < len(data_rows) else ""
                i += 2

                cells1 = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row1, re.DOTALL)
                cells1c = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', c)).strip() for c in cells1]
                if not cells1c or len(cells1c) < 3:
                    i -= 1
                    continue

                citation = cells1c[0]
                status   = cells1c[1] if len(cells1c) > 1 else ""
                date_txt = cells1c[2] if len(cells1c) > 2 else ""

                if status.lower() != "reported":
                    continue

                slug_m = re.search(r'href="(/utiac/[^"]+)"', row1)
                slug   = slug_m.group(1) if slug_m else ""

                # Parse date
                date_iso = ""
                try:
                    date_iso = datetime.strptime(date_txt, "%d %b %Y").strftime("%Y-%m-%d")
                except Exception:
                    pass

                # Stop when we go older than the requested range
                if date_iso and date_iso < from_date_iso:
                    stop = True
                    break
                if date_iso and to_date_iso and date_iso > to_date_iso:
                    continue

                # Title from row2
                cells2 = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row2, re.DOTALL) if row2 else []
                title  = citation
                for c in cells2:
                    t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', c)).strip()
                    if t.startswith("Case title:"):
                        title = t[len("Case title:"):].strip()
                        break

                page_url = f"{_UTIAC_BASE}{slug}" if slug else f"{_UTIAC_BASE}/utiac"
                doc_id   = re.sub(r"[^a-zA-Z0-9_-]", "_", slug.strip("/"))[-50:] if slug else re.sub(r"[^a-zA-Z0-9_-]", "_", citation)

                # Fetch detail page for the (signed) PDF link
                pdf_url = ""
                if slug:
                    try:
                        det_req = urllib.request.Request(page_url, headers={
                            "User-Agent": SEBI_UA, "Referer": f"{_UTIAC_BASE}/utiac",
                        })
                        with opener.open(det_req, timeout=15) as det_r:
                            det_body = det_r.read().decode("utf-8", errors="replace")
                        pdf_m = re.search(
                            r'href="(https://cloud-platform[^"]+\.pdf[^"]*)"', det_body
                        )
                        if pdf_m:
                            pdf_url = html.unescape(pdf_m.group(1))
                    except Exception:
                        pass

                all_docs.append({
                    "date": date_txt, "date_iso": date_iso,
                    "title": title,   "company": "",
                    "page_url": page_url, "pdf_url": pdf_url,
                    "type": doc_type, "id": f"utiac_{doc_id}",
                })
                new_count += 1

            cache[doc_type].update({"pages_done": page, "total": len(all_docs), "fetch_started_at": time.time()})
            if new_count == 0 or stop:
                break
            if f"page={page + 1}" not in body:
                break
            page += 1
            time.sleep(0.5)

        cache[doc_type].update({"data": all_docs, "total": len(all_docs), "fetching": False})
    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        traceback.print_exc()


_NA_BASE = "https://caselaw.nationalarchives.gov.uk"

def scrape_national_archives(doc_type, from_date_iso=None, to_date_iso=None):
    """National Archives Find Case Law — uses the public ATOM feed.
    Each feed entry contains the case title, publication date, and a direct PDF link."""
    if not from_date_iso or not to_date_iso:
        from_date_iso, to_date_iso, _, _ = _month_range(ACTIVE_MONTH['year'], ACTIVE_MONTH['month'])
    src      = SOURCES[doc_type]
    na_court = src["na_court"]   # e.g. "ukftt/tc" or "ukut/lc"

    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    try:
        court_enc = urllib.parse.quote(na_court, safe="")
        all_docs  = []
        page = 1
        while True:
            url = f"{_NA_BASE}/atom.xml?court={court_enc}&order=-date&page={page}"
            req = urllib.request.Request(url, headers={
                "User-Agent": SEBI_UA,
                "Accept": "application/atom+xml, application/xml, */*",
            })
            with _urlopen_retry(req) as r:
                body = r.read().decode("utf-8", errors="replace")

            entries = re.findall(r'<entry>(.*?)</entry>', body, re.DOTALL)
            if not entries:
                break

            oldest_on_page = None
            for entry_xml in entries:
                title_m = re.search(r'<title[^>]*>([^<]+)</title>', entry_xml)
                pub_m   = re.search(r'<published>([^<]+)</published>', entry_xml)
                # href before rel in these <link> elements
                case_m  = re.search(r'<link\s+href="([^"]+)"\s+rel="alternate"\s*/>', entry_xml)
                if not case_m:
                    case_m = re.search(r'<link[^>]+rel="alternate"[^>]+href="([^"]+)"', entry_xml)
                pdf_m   = re.search(r'<link\s+href="([^"]+)"\s+rel="alternate"\s+type="application/pdf"\s*/>', entry_xml)
                if not pdf_m:
                    pdf_m = re.search(r'<link[^>]+type="application/pdf"[^>]+href="([^"]+)"', entry_xml)
                if not pdf_m:
                    pdf_m = re.search(r'href="(https://assets\.caselaw\.[^"]+\.pdf)"', entry_xml)

                title    = html.unescape(title_m.group(1)).strip() if title_m else ""
                pub_raw  = pub_m.group(1)[:10] if pub_m else ""
                page_url = html.unescape(case_m.group(1)) if case_m else f"{_NA_BASE}/search"
                pdf_url  = html.unescape(pdf_m.group(1)) if pdf_m else ""

                date_iso = pub_raw
                try:
                    date_txt = datetime.fromisoformat(pub_raw).strftime("%d %b %Y") if pub_raw else pub_raw
                except Exception:
                    date_txt = pub_raw

                if oldest_on_page is None or (date_iso and date_iso < oldest_on_page):
                    oldest_on_page = date_iso

                doc_id = re.sub(r"[^a-zA-Z0-9_-]", "_", page_url.rstrip("/").split("/")[-1])[-50:]
                all_docs.append({
                    "date": date_txt, "date_iso": date_iso,
                    "title": title,   "company": "",
                    "page_url": page_url, "pdf_url": pdf_url,
                    "type": doc_type, "id": f"na_{doc_id}",
                })

            cache[doc_type].update({"pages_done": page, "total": len(all_docs), "fetch_started_at": time.time()})

            # Stop once all entries on this page are older than our start date
            if oldest_on_page and oldest_on_page < from_date_iso:
                break

            # Read last-page number from feed links (href comes before rel in these elements)
            last_m = re.search(r'href="[^"]*page=(\d+)"[^>]*rel="last"', body)
            if not last_m:
                last_m = re.search(r'rel="last"[^>]*href="[^"]*page=(\d+)"', body)
            last_page = int(last_m.group(1)) if last_m else page
            if page >= last_page:
                break
            page += 1
            time.sleep(0.5)

        docs = [d for d in all_docs if not d["date_iso"] or (from_date_iso <= d["date_iso"] <= to_date_iso)]
        cache[doc_type].update({"data": docs, "total": len(docs), "fetching": False})
    except Exception as e:
        cache[doc_type].update({"error": str(e), "fetching": False})
        traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  RBI — FEMA / FDI (FS_Notification.aspx pages)
# ════════════════════════════════════════════════════════════════════════════════

def scrape_rbi_fema(doc_type, from_date_iso=None, to_date_iso=None):
    """Scrape RBI FEMA notification pages (Directions / Circulars / Notifications).
    URL: https://www.rbi.org.in/scripts/FS_Notification.aspx?fn={fn}[&fnn={fnn}]
    HTML table:  <table class="tablebg">
        date-header row:  <tr><th colspan="4">Apr 22, 2025</th></tr>
        entry row:        <tr><td><a class='link2' href='...'>Title</a></td>
                              <td><a href='https://rbidocs..../...PDF'>pdf</a></td></tr>
    """
    cfg = SOURCES[doc_type]
    fn  = cfg["rbi_fema_fn"]
    fnn = cfg.get("rbi_fema_fnn")
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    label = f"FEMA fn={fn}" + (f"&fnn={fnn}" if fnn else "")
    print(f"[{doc_type}] Fetching RBI {label}")

    MAX_RETRIES = 3
    for _attempt in range(MAX_RETRIES):
      try:
        url = f"https://www.rbi.org.in/scripts/FS_Notification.aspx?fn={fn}"
        if fnn:
            url += f"&fnn={fnn}"
        html_text = fetch_simple(url, retries=4)

        # Find the tablebg table
        tbl_m = re.search(r'<table\s+class="tablebg"[^>]*>(.*?)</table>', html_text, re.S | re.I)
        if not tbl_m:
            cache[doc_type].update({"data": [], "total": 0, "fetching": False})
            print(f"[{doc_type}] No tablebg table found")
            return

        tbl_html = tbl_m.group(1)
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tbl_html, re.S | re.I)

        all_docs = []
        seen_ids = set()
        current_date_text = ""
        current_date_iso = ""

        for row in rows:
            # Date header row: <th colspan="4" ...>Apr 22, 2025</th>  (sometimes </td>)
            th_m = re.search(r'<th[^>]*>\s*((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4})\s*</', row, re.I)
            if th_m:
                current_date_text = th_m.group(1).strip()
                try:
                    current_date_iso = datetime.strptime(current_date_text, "%b %d, %Y").strftime("%Y-%m-%d")
                except Exception:
                    current_date_iso = ""
                continue

            # Entry row: has <a class='link2' ...> for title
            title_m = re.search(r"<a\s+class=['\"]link2['\"][^>]*href=(['\"]?)([^'\">\s]+)\1[^>]*>(.*?)</a>", row, re.S | re.I)
            if not title_m:
                continue

            href_raw = title_m.group(2).strip()
            title_html = title_m.group(3)
            # Clean nested <a> tags and HTML from title
            title = _clean_text(title_html)
            if not title:
                continue

            # Build page URL
            if href_raw.startswith('http'):
                page_url = href_raw
            else:
                page_url = f"https://www.rbi.org.in/scripts/{href_raw}"

            # Extract notification ID for dedup
            id_m = re.search(r'Id=(\d+)', href_raw, re.I)
            doc_id = f"rbi_fema_{id_m.group(1)}" if id_m else f"rbi_fema_{len(all_docs)}"
            if doc_id in seen_ids:
                continue
            seen_ids.add(doc_id)

            # PDF URL: look for rbidocs...PDF link
            pdf_m = re.search(r'href=["\']?(https://rbidocs\.rbi\.org\.in/[^"\'>\s]+\.PDF)["\']?', row, re.I)
            pdf_url = pdf_m.group(1) if pdf_m else ""

            all_docs.append({
                "date": _fmt_date(current_date_text) if current_date_text else "",
                "date_iso": current_date_iso,
                "title": title,
                "company": "",
                "page_url": page_url,
                "pdf_url": pdf_url,
                "type": doc_type,
                "id": doc_id,
            })

        # Filter by date range (skip for no_month_filter sources)
        if cfg.get('no_month_filter'):
            docs = all_docs
        elif from_date_iso and to_date_iso:
            docs = [d for d in all_docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]
        else:
            docs = all_docs

        cache[doc_type].update({"data": docs, "total": len(docs), "fetching": False, "pages_done": 1})
        print(f"[{doc_type}] Done — {len(docs)} docs (from {len(all_docs)} total)")
        return  # success — exit retry loop

      except Exception as e:
        if _attempt < MAX_RETRIES - 1:
            wait = 5 * (_attempt + 1)
            print(f"[{doc_type}] Attempt {_attempt+1}/{MAX_RETRIES} failed: {e} — retrying in {wait}s")
            time.sleep(wait)
        else:
            cache[doc_type].update({"error": str(e), "fetching": False})
            print(f"[{doc_type}] Error after {MAX_RETRIES} attempts: {e}")
            traceback.print_exc()


# ════════════════════════════════════════════════════════════════════════════════
#  SEBI — Regulation Pages (Related Articles tracker)
# ════════════════════════════════════════════════════════════════════════════════

def scrape_sebi_reg(doc_type, from_date_iso=None, to_date_iso=None, _resolve_ip=None):
    """Scrape a SEBI regulation page and its Related Articles.
    1. Fetches the main regulation page → extracts PDF from <iframe> + date
    2. POSTs to /sebiweb/ajax/home/getrelatedart.jsp to get related amendments
    3. Paginates through all related articles (5 per page)
    Each article links to another SEBI .html page that embeds a PDF.
    """
    cfg = SOURCES[doc_type]
    reg_url  = cfg["sebi_reg_url"]
    entry_id = cfg["sebi_entry_id"]
    cache[doc_type].update({"fetching": True, "error": None, "fetch_started_at": time.time()})
    print(f"[{doc_type}] Fetching SEBI regulation page (entry {entry_id})")

    MAX_RETRIES = 6
    for _attempt in range(MAX_RETRIES):
      cfile = tempfile.mktemp(suffix='.cookies')
      try:
        # Pin all session requests to one working SEBI backend IP
        resolve_ip = _resolve_ip
        # ── Step 1: Fetch main regulation page via curl ───────────────────
        main_html = _sebi_curl(reg_url, cookie_file=cfile, resolve_ip=resolve_ip)

        # Extract main regulation PDF from iframe
        main_pdf = ""
        iframe_m = re.search(r'file=(https?://[^\s&\'"<>]+\.pdf)', main_html, re.I)
        if iframe_m:
            main_pdf = iframe_m.group(1)
        else:
            iframe_m = re.search(r"<iframe[^>]+src=['\"]([^'\"]*\.pdf)['\"]", main_html, re.I)
            if iframe_m:
                s = iframe_m.group(1)
                main_pdf = s if s.startswith('http') else SEBI_BASE + '/' + s.lstrip('/')

        # Extract date and title from main page
        date_m = re.search(r"<div\s+class=['\"]date_value['\"]><h5>(.*?)</h5>", main_html, re.I)
        main_date_text = date_m.group(1).strip() if date_m else ""
        try:
            main_date_iso = datetime.strptime(main_date_text, "%b %d, %Y").strftime("%Y-%m-%d")
        except Exception:
            main_date_iso = ""

        title_m = re.search(r'<h1>(.*?)</h1>', main_html, re.S | re.I)
        main_title = _clean_text(title_m.group(1)) if title_m else doc_type

        all_docs = []
        seen_ids = set()

        # Add the main regulation document itself
        main_doc_id = f"sebi_reg_{entry_id}"
        all_docs.append({
            "date": _fmt_date(main_date_text) if main_date_text else "",
            "date_iso": main_date_iso,
            "title": main_title,
            "company": "",
            "page_url": reg_url,
            "pdf_url": main_pdf,
            "type": doc_type,
            "id": main_doc_id,
        })
        seen_ids.add(main_doc_id)

        # ── Step 2: Fetch Related Articles via AJAX ───────────────────────────
        ajax_url = f"{SEBI_BASE}/sebiweb/ajax/home/getrelatedart.jsp"
        curr_page = -1
        MAX_PAGES = 50  # safety cap

        for page_idx in range(MAX_PAGES):
            post_str = urllib.parse.urlencode({
                'entryId': entry_id,
                'currpage': str(curr_page),
                'keywordIds': '',
            })

            ajax_html = None
            for _ajax_try in range(3):
                try:
                    ajax_html = _sebi_curl(ajax_url, post_data=post_str, cookie_file=cfile, referer=reg_url, resolve_ip=resolve_ip)
                    break
                except Exception as e:
                    if _ajax_try < 2:
                        time.sleep(6 * (_ajax_try + 1))
                    else:
                        print(f"[{doc_type}] Related articles AJAX failed (page {page_idx}): {e}")

            if not ajax_html:
                break

            if 'Unauthorized' in ajax_html or '<li>' not in ajax_html:
                break

            # Parse related articles:
            # <li><div class='article_info'><div class='date_value'><h5>19 Nov, 2025</h5>...
            # <div><a href='https://...html'>Title</a></div></div></li>
            articles = re.findall(r"<li>(.*?)</li>", ajax_html, re.S | re.I)
            new_on_page = 0

            for art in articles:
                art_date_m = re.search(r"<h5>(.*?)</h5>", art, re.I)
                art_link_m = re.search(r"<a\s+href=['\"]([^'\"]+\.html)['\"][^>]*>(.*?)</a>", art, re.S | re.I)

                if not art_link_m:
                    continue

                art_url = art_link_m.group(1).strip()
                art_title = _clean_text(art_link_m.group(2))
                art_date_text = art_date_m.group(1).strip() if art_date_m else ""

                try:
                    art_date_iso = datetime.strptime(art_date_text, "%d %b, %Y").strftime("%Y-%m-%d")
                except Exception:
                    try:
                        art_date_iso = datetime.strptime(art_date_text, "%b %d, %Y").strftime("%Y-%m-%d")
                    except Exception:
                        art_date_iso = ""

                # Extract ID from URL
                eid_m = re.search(r'_(\d+)\.html', art_url)
                art_id = f"sebi_reg_{eid_m.group(1)}" if eid_m else f"sebi_reg_{hash(art_url) % 100000}"
                if art_id in seen_ids:
                    continue
                seen_ids.add(art_id)

                if not art_url.startswith('http'):
                    art_url = SEBI_BASE + art_url

                all_docs.append({
                    "date": _fmt_date(art_date_text) if art_date_text else "",
                    "date_iso": art_date_iso,
                    "title": art_title,
                    "company": "",
                    "page_url": art_url,
                    "pdf_url": "",  # resolve lazily
                    "type": doc_type,
                    "id": art_id,
                })
                new_on_page += 1

            print(f"[{doc_type}] Related articles page {page_idx}: +{new_on_page} articles")

            if new_on_page == 0:
                break

            # Check for "Load more" (next page)
            more_m = re.search(r"name=['\"]currpageMore['\"][^>]*value=['\"](\d+)['\"]", ajax_html, re.I)
            if more_m:
                curr_page = int(more_m.group(1))
            else:
                break

            time.sleep(1.0)

        # ── Step 3: Bulk-resolve PDF URLs for related articles ────────────────
        unresolved = [d for d in all_docs if not d.get("pdf_url") and d["page_url"]]
        if unresolved:
            print(f"[{doc_type}] Resolving {len(unresolved)} PDF URLs...")
            def _resolve(doc):
                try:
                    url = get_sebi_pdf_url(doc["page_url"])
                    if url:
                        doc["pdf_url"] = url
                except Exception:
                    pass
            with ThreadPoolExecutor(max_workers=min(3, len(unresolved))) as pool:
                list(pool.map(_resolve, unresolved))
            resolved = sum(1 for d in unresolved if d.get("pdf_url"))
            print(f"[{doc_type}] Resolved {resolved}/{len(unresolved)} PDF URLs")

        # Filter by date (skip for no_month_filter sources)
        if cfg.get('no_month_filter'):
            docs = all_docs
        elif from_date_iso and to_date_iso:
            docs = [d for d in all_docs if d["date_iso"] and from_date_iso <= d["date_iso"] <= to_date_iso]
        else:
            docs = all_docs

        cache[doc_type].update({"data": docs, "total": len(docs), "fetching": False, "pages_done": 1})
        print(f"[{doc_type}] Done — {len(docs)} docs (from {len(all_docs)} total)")
        return  # success — exit retry loop

      except Exception as e:
        if _attempt < MAX_RETRIES - 1:
            is_waf = 'rc=35' in str(e) or 'reset by peer' in str(e).lower()
            wait = (40 if is_waf else 20) * (_attempt + 1)
            print(f"[{doc_type}] Attempt {_attempt+1}/{MAX_RETRIES} failed: {e} — retrying in {wait}s")
            time.sleep(wait)
        else:
            cache[doc_type].update({"error": str(e), "fetching": False})
            print(f"[{doc_type}] Error after {MAX_RETRIES} attempts: {e}")
            traceback.print_exc()
      finally:
        try:
            os.unlink(cfile)
        except OSError:
            pass


# ── Dispatch table:  kind → (scraper_function, boot_delay_seconds) ────────────
SCRAPER_DISPATCH = {
    'sebi':          (lambda t, *a: scrape_sebi(t, *a), 0.8),
    'cci':           (lambda t, *a: scrape_cci(t, *a), 0.5),
    'cci_combo':     (lambda t, *a: scrape_cci_combo(t, *a), 0.5),
    'cci_antitrust': (lambda t, *a: scrape_cci_antitrust(t, *a), 0.5),
    'rbi':           (lambda t, *a: scrape_rbi(t, *a), 0.5),
    'irdai':         (lambda t, *a: scrape_irdai(t, *a), 0.3),
    'inx_circ':      (lambda t, *a: scrape_inx_circulars(t, *a), 0.3),
    'inx_issuer':    (lambda t, *a: scrape_inx_issuer(t, *a), 0.3),
    'rbi_md_entity': (lambda t, *a: scrape_rbi_md_entity(t, *a), 0.5),
    'tg_rera':       (lambda t, *a: scrape_tg_rera(t, *a), 0.5),
    'tg_rera_circ':  (lambda t, *a: scrape_tg_rera_circ(t, *a), 0.3),
    'tn_rera':       (lambda t, *a: scrape_tn_rera(t, *a), 0.3),
    'dtcp_ka':       (lambda t, *a: scrape_dtcp_ka(t, *a), 0.3),
    'maha_rera':     (lambda t, *a: scrape_maha_rera(t, *a), 0.3),
    'ka_reat':       (lambda t, *a: scrape_ka_reat(t, *a), 0.5),
    'ka_rera':       (lambda t, *a: scrape_ka_rera(t, *a), 0.5),
    'hr_reat':       (lambda t, *a: scrape_hr_reat(t, *a), 0.5),
    'dl_reat':       (lambda t, *a: scrape_dl_reat(t, *a), 0.5),
    'irdai_regs':    (lambda t, *a: scrape_irdai_regs(t, *a), 0.5),
    'cci_green':     (lambda t, *a: scrape_cci_green(t, *a), 0.5),
    'trai':          (lambda t, *a: scrape_trai(t, *a), 0.5),
    'cgst':          (lambda t, *a: scrape_cgst(t, *a), 0.5),
    'ibbi_nclt':     (lambda t, *a: scrape_ibbi_nclt(t, *a), 0.5),
    'eu_comp':       (lambda t, *a: scrape_eu_comp(t, *a), 1.0),
    'epo_boa':       (lambda t, *a: scrape_epo_boa(t, *a), 1.0),
    'edpb':          (lambda t, *a: scrape_edpb(t, *a),    1.0),
    'adgm':          (lambda t, *a: scrape_adgm(t, *a),    0.5),
    'difc_ca':       (lambda t, *a: scrape_difc_ca(t, *a), 0.5),
    'mohre':         (lambda t, *a: scrape_mohre(t, *a),   1.0),
    # ── UK ─────────────────────────────────────────────────────────────────────
    'govuk_finder':      (lambda t, *a: scrape_govuk_finder(t, *a),      0.5),
    'uk_cat':            (lambda t, *a: scrape_uk_cat(t, *a),            0.5),
    'uk_utiac':          (lambda t, *a: scrape_utiac(t, *a),             0.5),
    'national_archives': (lambda t, *a: scrape_national_archives(t, *a), 0.5),
    # ── FEMA / SEBI Regulations ────────────────────────────────────────────────
    'rbi_fema':          (lambda t, *a: scrape_rbi_fema(t, *a),    0.5),
    'sebi_reg':          (lambda t, *a: scrape_sebi_reg(t, *a),    0.8),
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

    def cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(200); self.cors(); self.end_headers()

    def do_GET(self):
      try:
        p = urllib.parse.urlparse(self.path)
        path, qs = p.path, urllib.parse.parse_qs(p.query)

        if path == '/':
            _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self._file(os.path.join(_base, 'frontend', 'index.html'), 'text/html')

        elif path == '/api/status':
            self._json({k: self._status(k) for k in SOURCES})

        elif path == '/api/active_month':
            y, m = ACTIVE_MONTH['year'], ACTIVE_MONTH['month']
            from_iso, to_iso, _, _ = _month_range(y, m)
            self._json({'year': y, 'month': m, 'from_iso': from_iso, 'to_iso': to_iso,
                        'range_from': ACTIVE_RANGE['from_iso'], 'range_to': ACTIVE_RANGE['to_iso'],
                        'is_custom': ACTIVE_RANGE.get('is_custom', False)})

        elif path == '/api/documents':
            dtype = qs.get('type', ['RHP'])[0].upper()
            docs  = self._filter(cache.get(dtype, {}).get('data', []), qs)
            self._json({"documents": docs, "total": len(docs)})

        elif path == '/api/unified':
            date_from = qs.get('from', [None])[0]
            date_to   = qs.get('to',   [None])[0]
            search    = qs.get('search', [''])[0].lower()
            # Use ACTIVE_RANGE as the baseline; user date params can narrow further
            base_from = ACTIVE_RANGE['from_iso']
            base_to   = ACTIVE_RANGE['to_iso']
            eff_from = date_from if date_from and date_from >= base_from else base_from
            eff_to   = date_to   if date_to   and date_to   <= base_to   else base_to
            result = {}
            for dtype in SOURCES:
                docs = list(cache.get(dtype, {}).get('data', []))
                # Exclude docs with no parseable date
                docs = [d for d in docs if d.get('date_iso')]
                docs = [d for d in docs if eff_from <= d['date_iso'] <= eff_to]
                if search:    docs = [d for d in docs if search in d.get('title','').lower() or search in d.get('company','').lower()]
                result[dtype] = docs
            self._json({"sources": result, "counts": {k: len(v) for k,v in result.items()}})

        elif path == '/api/get_pdf_url':
            page_url = qs.get('page_url', [None])[0]
            doc_id   = qs.get('id',       [None])[0]
            dtype    = qs.get('type', ['RHP'])[0].upper()
            if not page_url:
                self._json({"error": "No page_url"}, 400); return
            for d in cache.get(dtype, {}).get("data", []):
                if d["id"] == doc_id and d.get("pdf_url"):
                    self._json({"pdf_url": d["pdf_url"]}); return
            url = get_sebi_pdf_url(page_url)
            for d in cache.get(dtype, {}).get("data", []):
                if d["id"] == doc_id:
                    d["pdf_url"] = url; break
            self._json({"pdf_url": url} if url else {"error": "Not found"})

        elif path == '/api/audit':
            # Parallel HTTP HEAD verification of every cached PDF URL.
            # Returns per-source: total, ok, no_pdf, fail, failed_docs list.
            src_filter = qs.get('sources', [None])[0]
            targets    = [k for k in SOURCES
                          if src_filter is None or k in src_filter.split(',')]

            # Build flat list of (dtype, doc) for all docs across sources
            all_checks = []
            for dtype in targets:
                for doc in list(cache[dtype]['data']):
                    all_checks.append((dtype, doc))

            check_results = {}  # (dtype, doc_id) -> {status, content_type, content_length, response_time_ms, ...}

            def _head_check(dtype_doc):
                dtype_chk, doc = dtype_doc
                pdf_url = doc.get('pdf_url', '')
                if not pdf_url:
                    return (dtype_chk, doc['id'], {
                        'status': 'no_pdf', 'http_code': None,
                        'content_type': None, 'content_length': None,
                        'response_time_ms': 0, 'url_checked': '',
                    })
                t0 = time.time()
                try:
                    req = urllib.request.Request(pdf_url, headers={'User-Agent': SEBI_UA})
                    req.get_method = lambda: 'HEAD'
                    with urllib.request.urlopen(req, timeout=15, context=SSL_CTX) as resp:
                        elapsed = int((time.time() - t0) * 1000)
                        ct = resp.headers.get('Content-Type', '')
                        cl = resp.headers.get('Content-Length', '')
                        return (dtype_chk, doc['id'], {
                            'status': 'ok', 'http_code': resp.status,
                            'content_type': ct, 'content_length': cl,
                            'response_time_ms': elapsed, 'url_checked': pdf_url,
                        })
                except urllib.error.HTTPError as e:
                    elapsed = int((time.time() - t0) * 1000)
                    return (dtype_chk, doc['id'], {
                        'status': f'http_{e.code}', 'http_code': e.code,
                        'content_type': None, 'content_length': None,
                        'response_time_ms': elapsed, 'url_checked': pdf_url,
                    })
                except Exception as exc:
                    elapsed = int((time.time() - t0) * 1000)
                    return (dtype_chk, doc['id'], {
                        'status': 'err', 'http_code': None,
                        'content_type': None, 'content_length': None,
                        'response_time_ms': elapsed, 'url_checked': pdf_url,
                        'error_detail': str(exc)[:200],
                    })

            with ThreadPoolExecutor(max_workers=30) as _pool:
                for dtype_r, doc_id_r, result_r in _pool.map(
                    _head_check, all_checks, timeout=180
                ):
                    check_results[(dtype_r, doc_id_r)] = result_r

            audit_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Aggregate per source with full per-document evidence
            audit_result = {}
            for dtype in targets:
                docs = list(cache[dtype]['data'])
                ok = no_pdf = fail = 0
                failed_docs = []
                all_doc_evidence = []
                for doc in docs:
                    cr = check_results.get((dtype, doc['id']), {
                        'status': 'no_pdf', 'http_code': None,
                        'content_type': None, 'content_length': None,
                        'response_time_ms': 0, 'url_checked': '',
                    })
                    st = cr['status']
                    evidence_entry = {
                        'doc_id':      doc.get('id', ''),
                        'title':       doc.get('title', '')[:120],
                        'date':        doc.get('date', ''),
                        'date_iso':    doc.get('date_iso', ''),
                        'page_url':    doc.get('page_url', ''),
                        'pdf_url':     doc.get('pdf_url', ''),
                        'status':      st,
                        'http_code':   cr.get('http_code'),
                        'content_type':   cr.get('content_type'),
                        'content_length': cr.get('content_length'),
                        'response_time_ms': cr.get('response_time_ms', 0),
                    }
                    if cr.get('error_detail'):
                        evidence_entry['error_detail'] = cr['error_detail']
                    all_doc_evidence.append(evidence_entry)

                    if st == 'ok':
                        ok += 1
                    elif st == 'no_pdf':
                        no_pdf += 1
                    else:
                        fail += 1
                        failed_docs.append({
                            'title':   doc.get('title', '')[:120],
                            'pdf_url': doc.get('pdf_url', ''),
                            'page_url':doc.get('page_url', ''),
                            'date':    doc.get('date', ''),
                            'status':  st,
                            'http_code': cr.get('http_code'),
                            'error_detail': cr.get('error_detail', ''),
                        })
                audit_result[dtype] = {
                    'total': len(docs), 'ok': ok,
                    'no_pdf': no_pdf, 'fail': fail,
                    'accuracy_pct': round(ok / len(docs) * 100, 1) if docs else 100,
                    'failed_docs': failed_docs,
                    'evidence': all_doc_evidence,
                }
            # Wrap in envelope with metadata
            self._json({
                'audit_timestamp': audit_ts,
                'date_range': {'from': ACTIVE_RANGE['from_iso'], 'to': ACTIVE_RANGE['to_iso']},
                'sources_checked': len(targets),
                'total_docs_checked': len(all_checks),
                'results': audit_result,
            })

        elif path == '/api/download_progress':
            self._json(download_progress)

        else:
            self.send_response(404); self.end_headers()
      except Exception as e:
        try:
            self._json({"error": str(e)}, 500)
        except Exception:
            pass

    def do_POST(self):
      try:
        p = urllib.parse.urlparse(self.path)
        path = p.path
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode() if length else '{}'
        try:
            data = json.loads(body)
        except Exception:
            data = {}

        # ── Set active month ──────────────────────────────────────────────────
        if path == '/api/set_month':
            global _scrape_generation
            year  = int(data.get('year', ACTIVE_MONTH['year']))
            month = int(data.get('month', ACTIVE_MONTH['month']))
            if month < 1 or month > 12 or year < 2000 or year > 2100:
                self._json({'error': 'Invalid month'}, 400); return
            ACTIVE_MONTH['year'] = year
            ACTIVE_MONTH['month'] = month
            from_iso, to_iso, from_dd, to_dd = _month_range(year, month)
            ACTIVE_RANGE['from_iso'] = from_iso
            ACTIVE_RANGE['to_iso']   = to_iso
            ACTIVE_RANGE['is_custom'] = False
            # Clear all caches and bump generation to cancel any running scraper
            # Mark all as fetching=True so they show "loading" until the runner processes them
            for k in SOURCES:
                cache[k] = _empty_cache()
                cache[k]["fetching"] = True
            _scrape_generation += 1
            gen = _scrape_generation
            # Launch sequential runner in background
            threading.Thread(target=_run_all_scrapers, args=(from_iso, to_iso, from_dd, to_dd, gen), daemon=True).start()
            print(f"[SET_MONTH] Switching to {year}-{month:02d}, generation {gen}")
            self._json({'status': 'ok', 'year': year, 'month': month, 'from_iso': from_iso, 'to_iso': to_iso})
            return

        # ── Set custom date range (cross-month) ───────────────────────────────
        elif path == '/api/set_range':
            from_iso = data.get('from_iso', '').strip()
            to_iso   = data.get('to_iso', '').strip()
            if not from_iso or not to_iso:
                self._json({'error': 'from_iso and to_iso required'}, 400); return
            try:
                from_dt = datetime.strptime(from_iso, "%Y-%m-%d")
                to_dt   = datetime.strptime(to_iso,   "%Y-%m-%d")
            except Exception:
                self._json({'error': 'Invalid date format, use YYYY-MM-DD'}, 400); return
            if from_iso > to_iso:
                self._json({'error': 'from_iso must be <= to_iso'}, 400); return
            from_dd = from_dt.strftime("%d/%m/%Y")
            to_dd   = to_dt.strftime("%d/%m/%Y")
            ACTIVE_RANGE['from_iso']  = from_iso
            ACTIVE_RANGE['to_iso']    = to_iso
            ACTIVE_RANGE['is_custom'] = True
            # Update ACTIVE_MONTH to the start of the range so scrapers that
            # still read ACTIVE_MONTH directly use a sensible value
            ACTIVE_MONTH['year']  = from_dt.year
            ACTIVE_MONTH['month'] = from_dt.month
            # Mark all as fetching=True so they show "loading" until the runner processes them
            for k in SOURCES:
                cache[k] = _empty_cache()
                cache[k]["fetching"] = True
            _scrape_generation += 1
            gen = _scrape_generation
            threading.Thread(target=_run_all_scrapers, args=(from_iso, to_iso, from_dd, to_dd, gen), daemon=True).start()
            print(f"[SET_RANGE] Custom range {from_iso} → {to_iso}, generation {gen}")
            self._json({'status': 'ok', 'from_iso': from_iso, 'to_iso': to_iso, 'is_custom': True})
            return

        # ── Refresh ──────────────────────────────────────────────────────────
        elif path == '/api/refresh':
            dtype     = data.get('type', 'ALL').upper()
            from_date = data.get('from_date')  # DD/MM/YYYY for SEBI
            to_date   = data.get('to_date')
            from_iso  = None
            to_iso    = None
            if from_date:
                try:
                    from_iso = datetime.strptime(from_date, "%d/%m/%Y").strftime("%Y-%m-%d")
                    to_iso   = datetime.strptime(to_date,   "%d/%m/%Y").strftime("%Y-%m-%d") if to_date else None
                except Exception:
                    pass

            types_to_refresh = list(SOURCES.keys()) if dtype == 'ALL' else [dtype]
            started = []
            def _safe_refresh(fn, *args, _dtype=None):
                try:
                    fn(*args)
                except Exception as e:
                    if _dtype and cache[_dtype]["fetching"]:
                        cache[_dtype].update({"error": str(e), "fetching": False})
            for t in types_to_refresh:
                if cache[t]["fetching"]:
                    continue
                cache[t] = _empty_cache()
                kind = SOURCES[t].get('kind', '')
                # Special cases
                if kind == 'sebi':
                    threading.Thread(target=_safe_refresh, args=(scrape_sebi, t, from_date, to_date), kwargs={'_dtype': t}, daemon=True).start()
                    started.append(t)
                elif kind == 'bse':
                    if "BSE_PLACEMENT" not in started and "BSE_PRELIMINARY" not in started:
                        cache["BSE_PLACEMENT"] = _empty_cache()
                        cache["BSE_PRELIMINARY"] = _empty_cache()
                        threading.Thread(target=_safe_refresh, args=(scrape_bse_qip, from_iso, to_iso), daemon=True).start()
                        started.extend(["BSE_PLACEMENT", "BSE_PRELIMINARY"])
                # Dispatch table for all other kinds
                elif kind in SCRAPER_DISPATCH:
                    fn = SCRAPER_DISPATCH[kind][0]
                    threading.Thread(target=_safe_refresh, args=(fn, t, from_iso, to_iso), kwargs={'_dtype': t}, daemon=True).start()
                    started.append(t)
            self._json({"status": "refreshing", "types": started})

        # ── Download single ───────────────────────────────────────────────────
        elif path == '/api/download':
            doc_id   = data.get('id')
            if not doc_id:
                self._json({"status": "error", "error": "No document ID provided"}); return
            pdf_url  = data.get('pdf_url')
            title    = data.get('title', 'document')
            dtype    = data.get('type', 'RHP').upper()
            page_url = data.get('page_url')

            if download_progress.get(doc_id, {}).get('status') in ('downloading', 'queued', 'resolving', 'done'):
                self._json({"status": "already_active"}); return

            # Fetch citation metadata from cache
            _doc_meta = next((d for d in cache.get(dtype, {}).get("data", []) if d.get("id") == doc_id), {})
            download_progress[doc_id] = {
                "status": "queued", "filename": title, "type": dtype,
                "title":    _doc_meta.get("title",    title),
                "date":     _doc_meta.get("date",     ""),
                "page_url": _doc_meta.get("page_url", page_url or ""),
                "pdf_url":  pdf_url or "",
            }
            th = threading.Thread(target=resolve_and_download, args=(doc_id, pdf_url, page_url, title, dtype), daemon=True)
            th.start()
            self._json({"status": "queued", "id": doc_id})

        # ── Download all ──────────────────────────────────────────────────────
        elif path == '/api/download_all':
            documents = data.get('documents', [])  # list of {id, pdf_url, page_url, title, type, date}
            # Immediately mark all new docs as queued (no sleep here — avoids POST timeout)
            to_launch = []
            for doc in documents:
                doc_id   = doc.get('id')
                pdf_url  = doc.get('pdf_url')
                title    = doc.get('title', 'doc')
                page_url = doc.get('page_url')
                dtype    = doc.get('type', 'RHP').upper()
                date     = doc.get('date', '')

                if download_progress.get(doc_id, {}).get('status') in ('downloading', 'queued', 'resolving', 'done'):
                    continue

                download_progress[doc_id] = {
                    "status": "queued", "filename": title, "type": dtype,
                    "title":    title,
                    "date":     date,
                    "page_url": page_url or "",
                    "pdf_url":  pdf_url or "",
                }
                to_launch.append((doc_id, pdf_url, page_url, title, dtype))

            # Launch threads from a background thread so the POST returns immediately
            # Adaptive workers: sources with many docs get more concurrent slots
            def _launch_all(items):
                # Group by source so large sources run with higher parallelism
                from collections import defaultdict
                by_source = defaultdict(list)
                for item in items:
                    by_source[item[4]].append(item)  # item[4] = dtype

                def _worker_count(n):
                    if n >= 200: return 12
                    if n >= 50:  return 8
                    if n >= 20:  return 4
                    if n >= 5:   return 3
                    return 2

                def _run_source(source_items):
                    n = len(source_items)
                    sem = threading.Semaphore(_worker_count(n))
                    threads = []
                    for (did, pu, pgu, ttl, dt) in source_items:
                        sem.acquire()
                        def _task(d=did, p=pu, pg=pgu, t=ttl, dtype=dt, _s=sem):
                            try:
                                resolve_and_download(d, p, pg, t, dtype)
                            finally:
                                _s.release()
                        th = threading.Thread(target=_task, daemon=True)
                        th.start()
                        threads.append(th)
                    for th in threads:
                        th.join()

                # Launch each source's downloads in its own thread pool
                source_threads = []
                for src_items in by_source.values():
                    st = threading.Thread(target=_run_source, args=(src_items,), daemon=True)
                    st.start()
                    source_threads.append(st)

            if to_launch:
                threading.Thread(target=_launch_all, args=(to_launch,), daemon=True).start()
            self._json({"status": "queued", "count": len(to_launch)})

        # ── Manual download (save directly to correct repo folder) ─────────────
        elif path == '/api/manual_download':
            doc_id   = data.get('doc_id') or data.get('id', 'manual_' + str(int(time.time())))
            pdf_url  = data.get('pdf_url', '')
            title    = data.get('title', 'document')
            dtype    = data.get('type', 'RHP').upper()
            page_url = data.get('page_url', '')

            if not pdf_url:
                self._json({"status": "error", "error": "No pdf_url provided"}); return

            # Always re-queue (even if previous error), so user can manually retry
            download_progress[doc_id] = {
                "status": "queued", "filename": title, "type": dtype,
                "title":    title,
                "date":     data.get('date', ''),
                "page_url": page_url,
                "pdf_url":  pdf_url,
            }
            threading.Thread(
                target=resolve_and_download,
                args=(doc_id, pdf_url, page_url, title, dtype),
                daemon=True
            ).start()
            folder = SOURCES.get(dtype, {}).get('folder', '~/Desktop/Repositories/' + dtype)
            self._json({"status": "queued", "id": doc_id, "folder": folder})

        # ── Retry errors ──────────────────────────────────────────────────────
        elif path == '/api/retry_errors':
            # Use metadata already in download_progress — no cache lookup needed
            # Optional doc_id for single-doc retry; omit to retry all errors
            target_id = data.get('doc_id')  # None = retry all
            to_retry = []
            for doc_id, info in list(download_progress.items()):
                if info.get('status') != 'error':
                    continue
                if target_id and doc_id != target_id:
                    continue
                dtype    = info.get('type', 'RHP')
                pdf_url  = info.get('pdf_url', '')
                page_url = info.get('page_url', '')
                title    = info.get('title', doc_id)
                # Re-queue using already-stored citation metadata
                download_progress[doc_id] = {
                    "status": "queued", "filename": title, "type": dtype,
                    "title":    title,
                    "date":     info.get('date', ''),
                    "page_url": page_url,
                    "pdf_url":  pdf_url,
                }
                to_retry.append((doc_id, pdf_url, page_url, title, dtype))

            def _launch_retries(items):
                retry_sem = threading.Semaphore(8)  # limit concurrent retries
                def _retry_one(did, pu, pgu, ttl, dt):
                    try:
                        resolve_and_download(did, pu, pgu, ttl, dt)
                    finally:
                        retry_sem.release()
                for (did, pu, pgu, ttl, dt) in items:
                    retry_sem.acquire()
                    threading.Thread(target=_retry_one, args=(did, pu, pgu, ttl, dt), daemon=True).start()

            if to_retry:
                threading.Thread(target=_launch_retries, args=(to_retry,), daemon=True).start()
            self._json({"status": "retrying", "count": len(to_retry)})

        elif path == '/api/reset':
            # Reset everything to the current month defaults and re-scrape
            now = datetime.now()
            ACTIVE_MONTH['year'] = now.year
            ACTIVE_MONTH['month'] = now.month
            from_iso, to_iso, from_dd, to_dd = _month_range(now.year, now.month)
            ACTIVE_RANGE['from_iso'] = from_iso
            ACTIVE_RANGE['to_iso']   = to_iso
            ACTIVE_RANGE['is_custom'] = False
            for k in SOURCES:
                cache[k] = _empty_cache()
                cache[k]["fetching"] = True
            download_progress.clear()
            _scrape_generation += 1
            gen = _scrape_generation
            threading.Thread(target=_run_all_scrapers, args=(from_iso, to_iso, from_dd, to_dd, gen), daemon=True).start()
            print(f"[RESET] Reset to current month {now.year}-{now.month:02d}, generation {gen}")
            self._json({'status': 'ok', 'year': now.year, 'month': now.month, 'from_iso': from_iso, 'to_iso': to_iso})

        elif path == '/api/stop':
            for t in SOURCES:
                cache[t]["fetching"] = False
            self._json({"status": "stopped"})

        else:
            self.send_response(404); self.end_headers()
      except Exception as e:
        try:
            self._json({"error": str(e)}, 500)
        except Exception:
            pass

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _status(self, dtype):
        c = cache[dtype]
        return {"fetching": c["fetching"], "total": c["total"],
                "fetched": len(c["data"]), "pages_done": c["pages_done"], "error": c["error"],
                "fetch_started_at": c.get("fetch_started_at", 0)}

    def _filter(self, docs, qs):
        df = qs.get('from',   [None])[0]
        dt = qs.get('to',     [None])[0]
        sq = qs.get('search', [''])[0].lower()
        if df: docs = [d for d in docs if d.get('date_iso','') >= df]
        if dt: docs = [d for d in docs if d.get('date_iso','') <= dt]
        if sq: docs = [d for d in docs if sq in d.get('title','').lower()]
        return docs

    def _file(self, path, ctype):
        try:
            with open(path, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.cors(); self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404); self.end_headers()

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        ae = self.headers.get('Accept-Encoding', '') if hasattr(self, 'headers') else ''
        if 'gzip' in ae and len(body) > 1024:
            body = gzip.compress(body)
            self.send_header('Content-Encoding', 'gzip')
        self.send_header('Content-Length', str(len(body)))
        self.cors(); self.end_headers()
        self.wfile.write(body)


# ════════════════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════════════════

def main():
    global _scrape_generation
    PORT = 8765
    y, m = ACTIVE_MONTH['year'], ACTIVE_MONTH['month']
    from_iso, to_iso, from_dd, to_dd = _month_range(y, m)
    print(f"\n{'='*75}")
    print(f"  Lucio AI Briefcase  –  http://localhost:{PORT}")
    print(f"  Sources: {len(SOURCES)} total")
    print(f"  Active month: {y}-{m:02d} ({from_iso} to {to_iso})")
    print(f"{'='*75}\n")

    # Only pre-create the base Repositories folder itself; per-source folders
    # are created on demand during the first download (download_pdf calls makedirs).
    os.makedirs(BASE_DOWNLOAD_DIR, exist_ok=True)

    # Start watchdog thread
    threading.Thread(target=_watchdog, daemon=True).start()

    # Boot scrapers sequentially in a background thread
    _scrape_generation += 1
    gen = _scrape_generation
    for k in SOURCES:
        cache[k]["fetching"] = True
    threading.Thread(target=_run_all_scrapers, args=(from_iso, to_iso, from_dd, to_dd, gen), daemon=True).start()

    server = ThreadingHTTPServer(('localhost', PORT), Handler)
    import subprocess
    subprocess.Popen(['open', f'http://localhost:{PORT}'])
    print("Server ready — Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == '__main__':
    main()
