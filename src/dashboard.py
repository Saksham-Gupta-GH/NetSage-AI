"""
dashboard.py
NetSage AI — Summary Dashboard

Reads cases.csv and the Responsible AI log to generate:
  1. A bar chart of issue counts by concept tag
  2. A pie/bar chart of AI agreement rate (Accepted/Edited/Rejected)
  3. A detailed HTML report with a corrected-cases table
  4. A console summary
"""

import csv
import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")   # Non-interactive backend for file output
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent.parent
CASES_FILE    = BASE_DIR / "data" / "cases.csv"
RAI_LOG_FILE  = BASE_DIR / "data" / "responsible_ai_log.csv"
RESPONSES_DIR = BASE_DIR / "outputs" / "ai_responses"
REPORT_DIR    = BASE_DIR / "outputs"
REPORT_HTML   = REPORT_DIR / "dashboard_report.html"
CHART_ISSUES  = REPORT_DIR / "chart_issue_types.png"
CHART_AGREE   = REPORT_DIR / "chart_agreement.png"

COLOURS = {
    "ACCEPTED": "#6CC04A",  # Cisco Green
    "EDITED":   "#FDB813",  # Cisco Yellow
    "REJECTED": "#E2231A",  # Cisco Red
    "PENDING":  "#94A3B8"   # Slate gray
}

# ─── Load Data ────────────────────────────────────────────────────────────────

def load_cases() -> list[dict]:
    if not CASES_FILE.exists():
        return []
    with open(CASES_FILE, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_rai_log() -> list[dict]:
    if not RAI_LOG_FILE.exists():
        return []
    with open(RAI_LOG_FILE, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_ai_responses() -> list[dict]:
    results = []
    for rf in sorted(RESPONSES_DIR.glob("*.json")):
        with open(rf, encoding="utf-8") as f:
            results.append(json.load(f))
    return results


# ─── Chart 1: Issue Types Bar Chart ───────────────────────────────────────────

def chart_issue_types(cases: list[dict]):
    tags = [c["concept_tag"].split()[0] for c in cases]   # Use first word as short label
    counts = Counter(tags)
    labels  = list(counts.keys())
    values  = list(counts.values())

    # Sort by count
    sorted_pairs = sorted(zip(values, labels), reverse=True)
    values, labels = zip(*sorted_pairs)

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.set_facecolor("#F8FAFC")
    bars = ax.barh(labels, values, color="#00BCEB", edgecolor="white", height=0.6)

    # Add value labels on bars
    for bar, val in zip(bars, values):
        ax.text(bar.get_width() + 0.05, bar.get_y() + bar.get_height() / 2,
                str(val), va="center", ha="left", fontsize=11, fontweight="bold")

    ax.set_xlabel("Number of Cases", fontsize=12)
    ax.set_title("NetSage AI — Cases by Issue Type", fontsize=14, fontweight="bold", pad=15)
    ax.set_xlim(0, max(values) + 2)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    plt.tight_layout()
    fig.savefig(CHART_ISSUES, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [SAVED] Issue types chart → {CHART_ISSUES}")


# ─── Chart 2: AI Agreement Rate ───────────────────────────────────────────────

def chart_agreement(rai_log: list[dict], responses: list[dict]):
    # Count decisions from RAI log
    decisions = Counter(r["review_decision"] for r in rai_log)

    # Count PENDING (not yet reviewed)
    reviewed_ids = {r["case_id"] for r in rai_log}
    pending_count = sum(1 for r in responses if r["case_id"] not in reviewed_ids)
    if pending_count > 0:
        decisions["PENDING"] = pending_count

    fig, ax = plt.subplots(figsize=(7, 7))

    # Handle empty state — no reviews yet
    if not decisions or sum(decisions.values()) == 0:
        ax.text(0.5, 0.5, "No reviews yet.\nRun human_review.py\nto review AI diagnoses.",
                ha="center", va="center", fontsize=14, color="#999",
                transform=ax.transAxes,
                bbox=dict(boxstyle="round,pad=0.5", facecolor="#f5f5f5", edgecolor="#ddd"))
        ax.set_title("AI Diagnosis Agreement Rate\n(Pending reviews)", fontsize=14, fontweight="bold")
        ax.axis("off")
        plt.tight_layout()
        fig.savefig(CHART_AGREE, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  [SAVED] Agreement chart   → {CHART_AGREE} (no reviews yet)")
        return

    labels  = list(decisions.keys())
    values  = list(decisions.values())
    colours = [COLOURS.get(l, "#607D8B") for l in labels]

    wedges, texts, autotexts = ax.pie(
        values,
        labels=None,
        colors=colours,
        autopct="%1.0f%%",
        startangle=140,
        pctdistance=0.75,
        wedgeprops=dict(edgecolor="white", linewidth=2)
    )
    for t in autotexts:
        t.set_fontsize(13)
        t.set_fontweight("bold")

    legend_patches = [
        mpatches.Patch(color=COLOURS.get(l, "#607D8B"), label=f"{l}: {v}")
        for l, v in zip(labels, values)
    ]
    ax.legend(handles=legend_patches, loc="lower center",
              bbox_to_anchor=(0.5, -0.1), ncol=2, fontsize=11)

    total = sum(values)
    ax.set_title(f"AI Diagnosis Agreement Rate\n({total} cases total)", fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(CHART_AGREE, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [SAVED] Agreement chart   → {CHART_AGREE}")



# ─── HTML Report ──────────────────────────────────────────────────────────────

def generate_html(cases: list[dict], rai_log: list[dict], responses: list[dict]):
    total      = len(cases)
    reviewed   = len(rai_log)
    accepted   = sum(1 for r in rai_log if r["review_decision"] == "ACCEPTED")
    edited     = sum(1 for r in rai_log if r["review_decision"] == "EDITED")
    rejected   = sum(1 for r in rai_log if r["review_decision"] == "REJECTED")
    agree_rate = f"{(accepted / reviewed * 100):.0f}%" if reviewed else "N/A"

    # Build corrected cases table rows
    corrected = [r for r in rai_log if r["review_decision"] in ("EDITED", "REJECTED")]
    corrected_rows = ""
    for r in corrected:
        badge_colour = "#FDB813" if r["review_decision"] == "EDITED" else "#E2231A"
        corrected_rows += f"""
        <tr>
          <td style="font-family: monospace;"><strong>{r['case_id']}</strong></td>
          <td>{r['symptom'][:80]}...</td>
          <td>{r['ai_root_cause'][:80]}...</td>
          <td>{r['reviewer_correction'] or '—'}</td>
          <td>{r['reviewer_reason'] or '—'}</td>
          <td><span style="background:{badge_colour};color:white;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:bold;letter-spacing:0.5px;">{r['review_decision']}</span></td>
        </tr>"""

    # Severity breakdown
    sev_counts = Counter(c["severity"] for c in cases)
    sev_html   = "".join(
        f'<span style="background:{"#E2231A" if s=="Critical" else "#FDB813" if s=="High" else "#6CC04A"};'
        f'color:white;padding:4px 12px;border-radius:4px;margin:4px;display:inline-block;font-weight:bold;">{s}: {n}</span>'
        for s, n in sorted(sev_counts.items())
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NetSage AI — Dashboard Report</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'CiscoSans', 'Segoe UI', Arial, sans-serif; background: #F2F4F7; color: #1E293B; }}
  .header {{ background: #051024; color: #FFFFFF; padding: 40px; text-align: center; border-bottom: 4px solid #00BCEB; }}
  .header h1 {{ font-size: 2.2em; margin-bottom: 8px; font-weight: 300; letter-spacing: -0.5px; }}
  .header p  {{ color: #94A3B8; font-size: 1.1em; }}
  .container {{ max-width: 1200px; margin: 30px auto; padding: 0 20px; }}
  .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 20px; margin: 30px 0; }}
  .stat-card  {{ background: white; border-radius: 4px; padding: 24px; text-align: center;
                 border: 1px solid #E2E8F0; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }}
  .stat-card .num {{ font-size: 2.8em; font-weight: 300; color: #00BCEB; }}
  .stat-card .label {{ color: #64748B; font-size: 0.95em; margin-top: 6px; text-transform: uppercase; letter-spacing: 1px; font-weight: 600; }}
  .section {{ background: white; border-radius: 4px; padding: 28px; margin: 24px 0;
              border: 1px solid #E2E8F0; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }}
  .section h2 {{ font-size: 1.4em; margin-bottom: 20px; color: #051024; border-bottom: 2px solid #E2E8F0; padding-bottom: 10px; font-weight: 600; }}
  .charts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
  .charts img {{ width: 100%; border-radius: 4px; border: 1px solid #E2E8F0; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.9em; }}
  th {{ background: #F8FAFC; color: #475569; padding: 12px 14px; text-align: left; text-transform: uppercase; font-size: 0.85em; letter-spacing: 0.5px; border-bottom: 2px solid #E2E8F0; }}
  td {{ padding: 12px 14px; border-bottom: 1px solid #F1F5F9; vertical-align: top; color: #334155; }}
  tr:hover td {{ background: #F8FAFC; }}
  .footer {{ text-align: center; padding: 30px; color: #94A3B8; font-size: 0.9em; }}
</style>
</head>
<body>

<div class="header">
  <h1>🔍 NetSage AI — Dashboard Report</h1>
  <p>PROJECT 2: Applied AI + Network Troubleshooting | CCNA ITR 2026-27</p>
</div>

<div class="container">

  <div class="stats-grid">
    <div class="stat-card"><div class="num">{total}</div><div class="label">Total Cases</div></div>
    <div class="stat-card"><div class="num">{reviewed}</div><div class="label">Cases Reviewed</div></div>
    <div class="stat-card"><div class="num" style="color:#6CC04A">{accepted}</div><div class="label">AI Accepted</div></div>
    <div class="stat-card"><div class="num" style="color:#FDB813">{edited}</div><div class="label">AI Edited</div></div>
    <div class="stat-card"><div class="num" style="color:#E2231A">{rejected}</div><div class="label">AI Rejected</div></div>
    <div class="stat-card"><div class="num">{agree_rate}</div><div class="label">Agreement Rate</div></div>
  </div>

  <div class="section">
    <h2>Severity Breakdown</h2>
    <div>{sev_html}</div>
  </div>

  <div class="section">
    <h2>Charts</h2>
    <div class="charts">
      <div>
        <h3 style="margin-bottom:12px;color:#555">Issues by Type</h3>
        <img src="chart_issue_types.png" alt="Issue Types Chart">
      </div>
      <div>
        <h3 style="margin-bottom:12px;color:#555">AI Agreement Rate</h3>
        <img src="chart_agreement.png" alt="Agreement Chart">
      </div>
    </div>
  </div>

  <div class="section">
    <h2>Responsible AI Log — Corrected Cases ({len(corrected)})</h2>
    {"<p style='color:#999'>No corrections logged yet. Run human_review.py to review cases.</p>" if not corrected else f"""
    <table>
      <thead><tr>
        <th>Case ID</th><th>Symptom</th><th>AI Said</th>
        <th>Correction</th><th>Reason</th><th>Decision</th>
      </tr></thead>
      <tbody>{corrected_rows}</tbody>
    </table>"""}
  </div>

</div>

<div class="footer">
  Generated by NetSage AI · Saksham Gupta 230911186 · MIT Manipal IT-D · 2026-27
</div>

</body>
</html>"""

    with open(REPORT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  [SAVED] HTML report       → {REPORT_HTML}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "="*60)
    print("  NetSage AI — Generating Dashboard")
    print("="*60)

    cases     = load_cases()
    rai_log   = load_rai_log()
    responses = load_ai_responses()

    if not cases:
        print("[ERROR] No cases found. Check cases.csv exists.")
        return

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    chart_issue_types(cases)
    chart_agreement(rai_log, responses)
    generate_html(cases, rai_log, responses)

    # Console summary
    total    = len(cases)
    reviewed = len(rai_log)
    accepted = sum(1 for r in rai_log if r["review_decision"] == "ACCEPTED")
    edited   = sum(1 for r in rai_log if r["review_decision"] == "EDITED")
    rejected = sum(1 for r in rai_log if r["review_decision"] == "REJECTED")

    print("\n" + "="*60)
    print(f"  Total Cases    : {total}")
    print(f"  Reviewed       : {reviewed}/{total}")
    print(f"  ✓ Accepted     : {accepted}")
    print(f"  ✎ Edited       : {edited}")
    print(f"  ✗ Rejected     : {rejected}")
    if reviewed:
        print(f"  Agreement Rate : {accepted/reviewed*100:.0f}%")
    print("="*60)
    print(f"\n  Open the report: {REPORT_HTML}\n")


if __name__ == "__main__":
    main()
