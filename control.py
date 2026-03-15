#!/usr/bin/env python3
"""
control.py — Command channel for the Lucio Briefcase live website.

Send instructions to your GitHub Pages site from your terminal.
Uses the GitHub CLI (gh) to dispatch workflows and manage the site.

Commands:
  python3 control.py scrape                  # Force re-scrape all 93 sources
  python3 control.py scrape RHP,DRHP,CCI_GREEN   # Scrape specific sources only
  python3 control.py notice "Site maintenance at 5pm"  # Post a notice banner
  python3 control.py notice "New sources added!" --type success
  python3 control.py clear                   # Clear the notice banner
  python3 control.py month 2026-02           # Scrape a different month
  python3 control.py status                  # Check latest workflow run status
  python3 control.py logs                    # View latest scrape logs
  python3 control.py sources                 # List all valid source keys
"""

import subprocess, sys, json, os

REPO = "mohitlucio/LucioBriefcase"
WORKFLOW = "scrape.yml"

# Try to find gh binary
GH = None
for candidate in ["gh", "/tmp/gh_install/gh_2.63.2_macOS_arm64/bin/gh", "/usr/local/bin/gh", "/opt/homebrew/bin/gh"]:
    try:
        subprocess.run([candidate, "--version"], capture_output=True, check=True)
        GH = candidate
        break
    except (FileNotFoundError, subprocess.CalledProcessError):
        continue

if not GH:
    print("ERROR: GitHub CLI (gh) not found. Install it: https://cli.github.com")
    sys.exit(1)

# All valid source keys (from server.py)
ALL_SOURCES = [
    "RHP","DRHP","RIGHTS_LOF","INVIT_RI_FINAL","INVIT_RI_DRAFT","INVIT_PUB_FINAL",
    "INVIT_PUB_DRAFT","INVIT_PVT_FINAL","INVIT_PVT_DRAFT","REIT_FINAL","REIT_DRAFT",
    "SEBI_INFORMAL","SEBI_CONSULT","SEBI_CIRCULARS","SEBI_FINAL_OFFER","SEBI_LODR",
    "SEBI_ICDR","SEBI_TAKEOVER","SEBI_AIF","BSE_PLACEMENT","BSE_PRELIMINARY",
    "CCI_FORM1","CCI_FORM2","CCI_FORM3","CCI_GUN_JUMPING","CCI_APPROVED_MOD",
    "CCI_ANTI_S26_1","CCI_ANTI_S26_2","CCI_ANTI_S26_6","CCI_ANTI_S26_7",
    "CCI_ANTI_S27","CCI_ANTI_S33","CCI_ANTI_OTHER","CCI_GREEN",
    "RBI_MD","RBI_MC","RBI_MD_COMM","RBI_MD_SFB","RBI_MD_PAY","RBI_MD_LAB",
    "RBI_MD_RRB","RBI_MD_UCB","RBI_MD_RCB","RBI_MD_AIFI","RBI_MD_NBFC",
    "RBI_FEMA_DIR","RBI_FEMA_CIRC","RBI_FEMA_NOTIF",
    "IRDAI_CIRC","IRDAI_REGS","INX_CIRC","INX_ISSUER",
    "TG_RERA_ADJ","TG_RERA_AUTH","TG_RERA_SUO","TG_RERA_CIRC","TN_RERA",
    "DTCP_KA","MAHA_RERA","KA_REAT","KA_RERA","HR_REAT","DL_REAT",
    "TRAI_DIR","TRAI_REG","TRAI_REC","TRAI_CON","CGST_CIRC",
    "IBBI_RES","IBBI_ADM",
    "EU_MERGER","EU_ANTITRUST","EU_DMA","EU_FS",
    "EPO_BOA","EDPB_GUIDELINES","EDPB_BINDING","EDPB_OPINIONS",
    "ADGM_ORDERS","DIFC_CA_ORDERS","MOHRE_LAWS","MOHRE_RESOLUTIONS",
    "UK_ET_ENG","UK_AAC","UK_CAT","UK_CMA_MERGERS","UK_CMA_NONMERGER",
    "UK_EAT","UK_ET_SCOT","UK_UTIAC","UK_LAND","UK_TAX_CHANCERY","UK_TAX_FTT",
]


def gh(*args):
    """Run a gh CLI command and return stdout."""
    cmd = [GH] + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"Error: {r.stderr.strip()}")
        sys.exit(1)
    return r.stdout.strip()


def cmd_scrape(sources=None):
    """Trigger a scrape — all sources or specific ones."""
    if sources:
        keys = [k.strip().upper() for k in sources.split(",")]
        invalid = [k for k in keys if k not in ALL_SOURCES]
        if invalid:
            print(f"Invalid source keys: {', '.join(invalid)}")
            print(f"Run: python3 control.py sources")
            sys.exit(1)
        source_str = ",".join(keys)
        print(f"Dispatching scrape for {len(keys)} sources: {source_str}")
        gh("workflow", "run", WORKFLOW, "--repo", REPO,
           "-f", "action=scrape_sources", "-f", f"sources={source_str}")
    else:
        print("Dispatching full scrape of all 93 sources...")
        gh("workflow", "run", WORKFLOW, "--repo", REPO,
           "-f", "action=scrape_all")
    print("Workflow dispatched! Run 'python3 control.py status' to monitor.")


def cmd_notice(message, notice_type="info"):
    """Post a notice banner on the live website."""
    if notice_type not in ("info", "warning", "success"):
        print(f"Invalid notice type: {notice_type}. Use: info, warning, success")
        sys.exit(1)
    print(f"Posting {notice_type} notice: {message}")
    gh("workflow", "run", WORKFLOW, "--repo", REPO,
       "-f", "action=post_notice", "-f", f"message={message}", "-f", f"notice_type={notice_type}")
    print("Notice will appear on the site within ~1 minute.")


def cmd_clear():
    """Clear the notice banner from the website."""
    print("Clearing notice from website...")
    gh("workflow", "run", WORKFLOW, "--repo", REPO, "-f", "action=clear_notice")
    print("Notice will be cleared within ~1 minute.")


def cmd_month(month_str):
    """Scrape a specific month (YYYY-MM format)."""
    try:
        parts = month_str.split("-")
        y, m = int(parts[0]), int(parts[1])
        if not (2020 <= y <= 2099 and 1 <= m <= 12):
            raise ValueError
    except (ValueError, IndexError):
        print(f"Invalid month format: {month_str}. Use YYYY-MM (e.g. 2026-02)")
        sys.exit(1)
    print(f"Dispatching scrape for {y}-{m:02d}...")
    gh("workflow", "run", WORKFLOW, "--repo", REPO,
       "-f", "action=set_month", "-f", f"message={month_str}")
    print("Workflow dispatched! Data will update within ~15 minutes.")


def cmd_status():
    """Show recent workflow runs."""
    print("Recent workflow runs:")
    print("-" * 80)
    out = gh("run", "list", "--repo", REPO, "--limit", "5", "--workflow", WORKFLOW)
    if out:
        print(out)
    else:
        print("No runs found.")
    print()
    # Also show latest run detail
    out2 = gh("run", "list", "--repo", REPO, "--limit", "1", "--workflow", WORKFLOW, "--json", "status,conclusion,updatedAt,displayTitle")
    if out2:
        runs = json.loads(out2)
        if runs:
            r = runs[0]
            status = r.get("conclusion") or r.get("status", "unknown")
            print(f"Latest: {r.get('displayTitle', '?')} — {status} (updated {r.get('updatedAt', '?')})")


def cmd_logs():
    """View logs from the latest workflow run."""
    print("Fetching latest run logs...")
    out = gh("run", "list", "--repo", REPO, "--limit", "1", "--workflow", WORKFLOW, "--json", "databaseId")
    runs = json.loads(out)
    if not runs:
        print("No runs found.")
        return
    run_id = str(runs[0]["databaseId"])
    print(f"Run ID: {run_id}")
    print("-" * 80)
    log_out = gh("run", "view", run_id, "--repo", REPO, "--log")
    # Print last 60 lines (most relevant)
    lines = log_out.split("\n")
    if len(lines) > 60:
        print(f"... ({len(lines) - 60} lines truncated, showing last 60)")
        lines = lines[-60:]
    print("\n".join(lines))


def cmd_sources():
    """List all valid source keys grouped by category."""
    categories = {
        "SEBI": [], "BSE": [], "CCI": [], "RBI": [], "IRDAI": [], "INX": [],
        "RERA": [], "TRAI": [], "GST": [], "IBBI": [],
        "EU": [], "EPO": [], "EDPB": [], "UAE": [], "UK": [],
    }
    for k in ALL_SOURCES:
        placed = False
        for cat in categories:
            if k.startswith(cat) or (cat == "RERA" and any(x in k for x in ["RERA", "REAT", "DTCP"])) \
                    or (cat == "EU" and k.startswith("EU_")) \
                    or (cat == "UAE" and k in ("ADGM_ORDERS", "DIFC_CA_ORDERS", "MOHRE_LAWS", "MOHRE_RESOLUTIONS")):
                categories[cat].append(k)
                placed = True
                break
        if not placed:
            categories.setdefault("Other", []).append(k)

    print(f"All {len(ALL_SOURCES)} source keys:\n")
    for cat, keys in categories.items():
        if keys:
            print(f"  {cat} ({len(keys)}):")
            for k in keys:
                print(f"    {k}")
            print()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    command = sys.argv[1].lower()

    if command == "scrape":
        sources = sys.argv[2] if len(sys.argv) > 2 else None
        cmd_scrape(sources)
    elif command == "notice":
        if len(sys.argv) < 3:
            print("Usage: python3 control.py notice \"Your message\" [--type info|warning|success]")
            sys.exit(1)
        msg = sys.argv[2]
        ntype = "info"
        if "--type" in sys.argv:
            idx = sys.argv.index("--type")
            if idx + 1 < len(sys.argv):
                ntype = sys.argv[idx + 1]
        cmd_notice(msg, ntype)
    elif command == "clear":
        cmd_clear()
    elif command == "month":
        if len(sys.argv) < 3:
            print("Usage: python3 control.py month 2026-02")
            sys.exit(1)
        cmd_month(sys.argv[2])
    elif command == "status":
        cmd_status()
    elif command == "logs":
        cmd_logs()
    elif command == "sources":
        cmd_sources()
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
