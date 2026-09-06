"""
ai_diagnose.py
NetSage AI — AI Diagnosis Engine using Gemini API

Reads cases from cases.csv, builds structured prompts,
calls the Gemini API, saves JSON responses, and compares
AI output against expected_fault for accuracy tracking.
"""

import csv
import json
import os
import re
import time
from pathlib import Path

import google.genai as genai
from google.genai import types

# ─── Configuration ────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")
GEMINI_MODEL   = "gemini-3.6-flash"      # Fast and cost-effective

BASE_DIR       = Path(__file__).parent.parent
CASES_FILE     = BASE_DIR / "data" / "cases.csv"
PROMPT_FILE    = BASE_DIR / "prompts" / "diagnose_prompt.md"
RESPONSES_DIR  = BASE_DIR / "outputs" / "ai_responses"
SUMMARY_FILE   = BASE_DIR / "outputs" / "ai_diagnosis_summary.json"

# ─── Load Prompt Template ─────────────────────────────────────────────────────

def load_prompt_template() -> str:
    if not PROMPT_FILE.exists():
        raise FileNotFoundError(f"Prompt file not found: {PROMPT_FILE}")
    return PROMPT_FILE.read_text(encoding="utf-8")


def build_prompt(case: dict, prompt_template: str) -> str:
    """Fill in the prompt template with case-specific data."""
    return f"""{prompt_template}

---

## NOW DIAGNOSE THIS CASE

Symptom: {case['symptom']}
Topology Note: {case['topology_note']}
Show Command Output: {case['show_output']}

Return ONLY valid JSON following the schema above. No extra text.
"""


# ─── Gemini API Call ──────────────────────────────────────────────────────────

def call_gemini(prompt: str, retries: int = 4) -> str:
    """Send prompt to Gemini with exponential backoff retry on 503 errors."""
    import warnings
    warnings.filterwarnings("ignore")   # Suppress AFC warnings

    client = genai.Client(api_key=GEMINI_API_KEY)
    delay  = 5  # seconds — doubles on each retry

    for attempt in range(1, retries + 1):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=1024,
                )
            )
            return response.text.strip()

        except Exception as e:
            err_str = str(e)
            is_503  = "503" in err_str or "UNAVAILABLE" in err_str
            is_last = attempt == retries

            if is_503 and not is_last:
                print(f"    [RETRY {attempt}/{retries}] 503 overloaded — waiting {delay}s...")
                time.sleep(delay)
                delay *= 2   # Exponential backoff: 5s → 10s → 20s → 40s
            else:
                raise   # Not a 503, or last attempt — re-raise to caller




def extract_json(raw_text: str) -> dict:
    """Extract JSON from raw AI response (handles markdown code blocks)."""
    # Strip markdown fences if present
    cleaned = re.sub(r"```(?:json)?", "", raw_text).strip().rstrip("`").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON within the text
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {"error": "Could not parse JSON", "raw": raw_text}


# ─── Accuracy Check ───────────────────────────────────────────────────────────

def check_accuracy(ai_response: dict, expected_fault: str) -> str:
    """
    Simple string similarity check between AI root_cause and expected_fault.
    Returns: CORRECT | PARTIAL | INCORRECT
    """
    if "error" in ai_response:
        return "PARSE_ERROR"

    root_cause = ai_response.get("root_cause", "").lower()
    expected   = expected_fault.lower()

    # Extract key terms from expected fault (words > 4 chars)
    key_terms = [w for w in re.findall(r"\b\w+\b", expected) if len(w) > 4]
    matches   = sum(1 for term in key_terms if term in root_cause)
    ratio     = matches / len(key_terms) if key_terms else 0

    if ratio >= 0.6:
        return "CORRECT"
    elif ratio >= 0.3:
        return "PARTIAL"
    else:
        return "INCORRECT"


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        print("[ERROR] Please set your GEMINI_API_KEY environment variable:")
        print("  export GEMINI_API_KEY='your-key-here'")
        return

    RESPONSES_DIR.mkdir(parents=True, exist_ok=True)

    if not CASES_FILE.exists():
        print(f"[ERROR] cases.csv not found at {CASES_FILE}")
        return

    prompt_template = load_prompt_template()
    print(f"\n[INFO] Loaded prompt template ({len(prompt_template)} chars)")

    # Read cases
    with open(CASES_FILE, newline="", encoding="utf-8") as f:
        cases = list(csv.DictReader(f))

    print(f"[INFO] Processing {len(cases)} cases with Gemini {GEMINI_MODEL}...")
    print("="*60)

    summary = []

    for i, case in enumerate(cases):
        case_id = case["case_id"]
        print(f"\n[{i+1}/{len(cases)}] Diagnosing {case_id}...")
        print(f"  Symptom: {case['symptom'][:70]}...")

        # Check if already processed
        response_file = RESPONSES_DIR / f"{case_id}.json"
        if response_file.exists():
            print(f"  [SKIP] Already processed. Loading cached response.")
            with open(response_file, encoding="utf-8") as f:
                saved = json.load(f)
            ai_response = saved.get("ai_response", {})
            accuracy    = saved.get("accuracy", "UNKNOWN")
        else:
            # Build prompt and call AI
            prompt = build_prompt(case, prompt_template)
            try:
                raw_response = call_gemini(prompt)
                ai_response  = extract_json(raw_response)
                accuracy     = check_accuracy(ai_response, case["expected_fault"])

                # Only save if no error — so failed cases are retried on next run
                if "error" not in ai_response:
                    output = {
                        "case_id":        case_id,
                        "symptom":        case["symptom"],
                        "expected_fault": case["expected_fault"],
                        "ai_response":    ai_response,
                        "accuracy":       accuracy,
                        "review_status":  "PENDING"
                    }
                    with open(response_file, "w", encoding="utf-8") as f:
                        json.dump(output, f, indent=2)
                else:
                    accuracy = "PARSE_ERROR"

                # Rate limiting — avoid hitting API too fast
                time.sleep(1)

            except Exception as e:
                print(f"  [ERROR] API call failed: {e}")
                ai_response = {"error": str(e)}
                accuracy    = "API_ERROR"

        # Print quick result
        confidence = ai_response.get("confidence", "?")
        root_cause = ai_response.get("root_cause", "N/A")[:80]
        print(f"  AI says: {root_cause}...")
        print(f"  Confidence: {confidence} | Accuracy: {accuracy}")

        summary.append({
            "case_id":        case_id,
            "concept_tag":    case["concept_tag"],
            "severity":       case["severity"],
            "accuracy":       accuracy,
            "confidence":     confidence,
            "review_status":  "PENDING"
        })

    # Save summary
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # Print final stats
    total    = len(summary)
    correct  = sum(1 for r in summary if r["accuracy"] == "CORRECT")
    partial  = sum(1 for r in summary if r["accuracy"] == "PARTIAL")
    wrong    = sum(1 for r in summary if r["accuracy"] == "INCORRECT")

    print("\n" + "="*60)
    print("  NetSage AI — Diagnosis Complete")
    print("="*60)
    print(f"  Total cases    : {total}")
    print(f"  ✓ Correct      : {correct} ({correct/total*100:.0f}%)")
    print(f"  ~ Partial      : {partial} ({partial/total*100:.0f}%)")
    print(f"  ✗ Incorrect    : {wrong} ({wrong/total*100:.0f}%)")
    print(f"\n  Responses saved to : {RESPONSES_DIR}")
    print(f"  Summary saved to   : {SUMMARY_FILE}")
    print("\n  Run human_review.py next to review and log AI decisions.\n")


if __name__ == "__main__":
    main()
