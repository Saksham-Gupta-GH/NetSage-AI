"""
human_review.py
NetSage AI — Human Review CLI

Presents each AI diagnosis to a human reviewer who can
Accept, Edit, or Reject the AI's answer. Logs all decisions
(including corrections) to the Responsible AI log.
"""

import csv
import json
import os
from datetime import datetime
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).parent.parent
RESPONSES_DIR  = BASE_DIR / "outputs" / "ai_responses"
SUMMARY_FILE   = BASE_DIR / "outputs" / "ai_diagnosis_summary.json"
RAI_LOG_FILE   = BASE_DIR / "data" / "responsible_ai_log.csv"

# ─── Colours ──────────────────────────────────────────────────────────────────
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    BLUE   = "\033[94m"
    GREY   = "\033[90m"


def print_header():
    print(f"\n{C.CYAN}{C.BOLD}")
    print("╔══════════════════════════════════════════════════════╗")
    print("║          NetSage AI — Human Review Console          ║")
    print("╚══════════════════════════════════════════════════════╝")
    print(C.RESET)


def print_case(case_data: dict, idx: int, total: int):
    ai  = case_data.get("ai_response", {})
    acc = case_data.get("accuracy", "?")

    acc_colour = C.GREEN if acc == "CORRECT" else (C.YELLOW if acc == "PARTIAL" else C.RED)

    print(f"\n{C.BOLD}{'─'*60}{C.RESET}")
    print(f"{C.BOLD}  Case {idx}/{total}: {case_data['case_id']}{C.RESET}")
    print(f"{'─'*60}")
    print(f"{C.CYAN}  Symptom:{C.RESET}")
    print(f"    {case_data['symptom']}")
    print(f"\n{C.CYAN}  Expected Fault:{C.RESET}")
    print(f"    {case_data['expected_fault']}")
    print(f"\n{C.CYAN}  ── AI Diagnosis ──{C.RESET}")

    if "error" in ai:
        print(f"  {C.RED}[AI ERROR] {ai['error']}{C.RESET}")
        return

    conf_colour = C.GREEN if ai.get("confidence") == "high" else (C.YELLOW if ai.get("confidence") == "medium" else C.RED)

    print(f"  Root Cause  : {ai.get('root_cause', 'N/A')}")
    print(f"  OSI Layer   : {ai.get('osi_layer', 'N/A')}")
    print(f"  Confidence  : {conf_colour}{ai.get('confidence', '?').upper()}{C.RESET}")
    print(f"  Evidence    : {C.GREY}{ai.get('evidence', 'N/A')}{C.RESET}")
    print(f"  Next Cmd    : {C.YELLOW}{ai.get('next_command', 'N/A')}{C.RESET}")
    print(f"\n  Fix Steps:")
    for step in ai.get("fix_steps", []):
        print(f"    {C.GREEN}→{C.RESET} {step}")
    print(f"\n  Auto-Accuracy: {acc_colour}[{acc}]{C.RESET}")


def get_reviewer_decision() -> tuple[str, str, str]:
    """Prompt reviewer for Accept / Edit / Reject and return (decision, correction, reason)."""
    print(f"\n  {C.BOLD}Your decision:{C.RESET}")
    print(f"    {C.GREEN}[A]{C.RESET} Accept  — AI is correct")
    print(f"    {C.YELLOW}[E]{C.RESET} Edit    — AI is mostly right but needs correction")
    print(f"    {C.RED}[R]{C.RESET} Reject  — AI is wrong")
    print(f"    {C.GREY}[S]{C.RESET} Skip    — Come back to this later")

    while True:
        choice = input(f"\n  Enter choice [A/E/R/S]: ").strip().upper()
        if choice in ("A", "E", "R", "S"):
            break
        print("  Invalid input. Please enter A, E, R, or S.")

    correction = ""
    reason     = ""

    if choice == "E":
        print(f"\n  {C.YELLOW}Enter the corrected root cause:{C.RESET}")
        correction = input("  > ").strip()
        print(f"\n  {C.YELLOW}Why did you correct it?{C.RESET}")
        reason = input("  > ").strip()

    elif choice == "R":
        print(f"\n  {C.RED}Enter the correct root cause:{C.RESET}")
        correction = input("  > ").strip()
        print(f"\n  {C.RED}Why is the AI wrong?{C.RESET}")
        reason = input("  > ").strip()

    decision_map = {"A": "ACCEPTED", "E": "EDITED", "R": "REJECTED", "S": "SKIPPED"}
    return decision_map[choice], correction, reason


def init_rai_log():
    """Create the Responsible AI log CSV with headers if it doesn't exist."""
    if not RAI_LOG_FILE.exists():
        with open(RAI_LOG_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "case_id", "symptom", "expected_fault",
                "ai_root_cause", "ai_confidence", "auto_accuracy",
                "review_decision", "reviewer_correction", "reviewer_reason",
                "reviewed_at"
            ])


def append_rai_log(case_data: dict, decision: str, correction: str, reason: str):
    ai = case_data.get("ai_response", {})
    with open(RAI_LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            case_data["case_id"],
            case_data["symptom"],
            case_data["expected_fault"],
            ai.get("root_cause", "N/A"),
            ai.get("confidence", "N/A"),
            case_data.get("accuracy", "N/A"),
            decision,
            correction,
            reason,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ])


def update_response_file(case_file: Path, decision: str):
    """Update the review_status field in the individual response file."""
    with open(case_file, encoding="utf-8") as f:
        data = json.load(f)
    data["review_status"] = decision
    with open(case_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print_header()
    init_rai_log()

    # Gather all response files
    response_files = sorted(RESPONSES_DIR.glob("*.json"))
    if not response_files:
        print(f"[ERROR] No AI response files found in {RESPONSES_DIR}")
        print("  Run ai_diagnose.py first to generate responses.")
        return

    # Filter to only PENDING cases
    pending = []
    for rf in response_files:
        with open(rf, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("review_status", "PENDING") == "PENDING":
            pending.append((rf, data))

    if not pending:
        print(f"\n  {C.GREEN}All cases have been reviewed! Check the dashboard.{C.RESET}")
        return

    total = len(pending)
    print(f"\n  {total} case(s) pending review.")
    print(f"  Reviewer log: {RAI_LOG_FILE}\n")

    accepted = edited = rejected = skipped = 0

    for idx, (rf, case_data) in enumerate(pending, 1):
        print_case(case_data, idx, total)
        decision, correction, reason = get_reviewer_decision()

        if decision == "SKIPPED":
            skipped += 1
            print(f"  {C.GREY}Skipped.{C.RESET}")
            continue

        append_rai_log(case_data, decision, correction, reason)
        update_response_file(rf, decision)

        if decision == "ACCEPTED":
            accepted += 1
            print(f"  {C.GREEN}✓ Accepted and logged.{C.RESET}")
        elif decision == "EDITED":
            edited += 1
            print(f"  {C.YELLOW}✎ Correction logged.{C.RESET}")
        elif decision == "REJECTED":
            rejected += 1
            print(f"  {C.RED}✗ Rejection logged.{C.RESET}")

    # Session summary
    print(f"\n{'='*60}")
    print(f"  Review Session Complete")
    print(f"{'='*60}")
    print(f"  ✓ Accepted : {accepted}")
    print(f"  ✎ Edited   : {edited}")
    print(f"  ✗ Rejected : {rejected}")
    print(f"  ○ Skipped  : {skipped}")
    print(f"\n  RAI log saved to: {RAI_LOG_FILE}")
    print(f"  Run dashboard.py to see the full report.\n")


if __name__ == "__main__":
    main()
