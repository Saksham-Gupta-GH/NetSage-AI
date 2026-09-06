# NetSage AI
## AI-Assisted Network Troubleshooting with Human Review

**PROJECT 2: Applied AI + Network Troubleshooting**  
**Team:** Saksham Gupta (230911186) · IT-D · MIT Manipal · 2026-27  

---

## What This Does

NetSage AI is a network fault diagnosis assistant for CCNA-level Packet Tracer lab scenarios.
It reads a symptom and `show` command output, runs deterministic rule checks, queries the Gemini AI for a root-cause diagnosis, and presents the result to a human reviewer who can accept, edit, or reject the AI's answer.

---

## Project Structure

```
NetSage-AI/
├── data/
│   ├── cases.csv                  ← 33 troubleshooting cases
│   └── responsible_ai_log.csv     ← Human correction log (auto-created)
├── prompts/
│   └── diagnose_prompt.md         ← Structured AI prompts with few-shot examples
├── src/
│   ├── rule_checker.py            ← Deterministic config validation (runs first)
│   ├── ai_diagnose.py             ← Gemini API diagnosis engine
│   ├── human_review.py            ← CLI human review console
│   └── dashboard.py               ← Generates charts and HTML report
├── outputs/
│   ├── ai_responses/              ← Per-case AI JSON responses
│   ├── rule_checker_results.json  ← Rule checker output
│   ├── chart_issue_types.png      ← Bar chart: cases by type
│   ├── chart_agreement.png        ← Pie chart: AI agreement rate
│   └── dashboard_report.html      ← Full HTML dashboard
└── README.md
```

---

## Setup

### 1. Install dependencies

```bash
pip install google-generativeai matplotlib
```

### 2. Set your Gemini API key

```bash
export GEMINI_API_KEY="your-api-key-here"
```

---

## Usage (Run in This Order)

### Step 1 — Run the Rule Checker
Runs deterministic checks on all 33 cases **before** AI diagnosis.

```bash
cd NetSage-AI
python src/rule_checker.py
```

Output: `outputs/rule_checker_results.json` + console summary

---

### Step 2 — Run AI Diagnosis
Feeds each case to Gemini and saves structured JSON responses.

```bash
python src/ai_diagnose.py
```

Output: `outputs/ai_responses/C001.json` ... `C033.json` + `ai_diagnosis_summary.json`

> **Note:** Already-processed cases are skipped (cached). Re-run safely.

---

### Step 3 — Human Review
Review each AI diagnosis and Accept / Edit / Reject.

```bash
python src/human_review.py
```

Corrections are saved to `data/responsible_ai_log.csv`.

---

### Step 4 — Generate Dashboard
Produces charts and the full HTML report.

```bash
python src/dashboard.py
```

Then open `outputs/dashboard_report.html` in your browser.

---

## Case Coverage (33 Cases)

| Concept | Cases |
|---|---|
| VLAN / Trunking | C001, C005, C011, C018, C022, C023, C026, C031, C032 |
| DHCP | C002, C004, C014, C019, C020, C030 |
| ACL | C003, C012, C013, C017, C021 |
| NAT / PAT | C003, C016, C024, C029 |
| OSPF | C010, C015, C021, C025, C028 |
| Routing / Interface | C009, C027 |
| HSRP | C006 |
| EtherChannel | C008 |
| SSH / Security | C007 |
| VPN / GRE | C033 |
| DNS | C004, C019, C030 |

---

## Responsible AI Principles

1. **No auto-fix:** The system never applies a fix automatically. A human must review every diagnosis.
2. **Evidence-based:** AI responses must quote specific `show` command output as evidence.
3. **Confidence scoring:** AI returns `high / medium / low` confidence so reviewers know when to probe further.
4. **Correction logging:** Every edited or rejected diagnosis is logged with the correct answer and the reason.
5. **Deterministic pre-check:** Rule-based checks catch obvious misconfigs before the AI even runs.

---

## Deliverables Submitted

| File | Description |
|---|---|
| `data/cases.csv` | 33 cases with symptom, show output, OSI layer, severity |
| `prompts/diagnose_prompt.md` | System prompt + 3 few-shot examples + schema |
| `src/rule_checker.py` | 10 deterministic rules |
| `data/responsible_ai_log.csv` | Human correction log (5+ corrected cases) |
| `outputs/dashboard_report.html` | Issue type chart + agreement rate + corrections table |
