"""
rule_checker.py
NetSage AI — Deterministic Rule-Based Network Config Checker

Runs before AI diagnosis to catch common misconfigurations using
pattern matching on show command outputs from cases.csv.
"""

import csv
import re
import json
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.parent
CASES_FILE = BASE_DIR / "data" / "cases.csv"
OUT_FILE   = BASE_DIR / "outputs" / "rule_checker_results.json"

# ─── Rule Definitions ─────────────────────────────────────────────────────────

def check_interface_down(show_output: str) -> dict | None:
    """Flag if any interface shows 'line protocol is down'."""
    if re.search(r"line protocol is down", show_output, re.IGNORECASE):
        match = re.search(r"([\w/\.]+).*line protocol is down", show_output, re.IGNORECASE)
        iface = match.group(1) if match else "unknown interface"
        return {
            "rule": "INTERFACE_DOWN",
            "severity": "High",
            "detail": f"Interface '{iface}' has line protocol down — check cable, shutdown, or encapsulation.",
            "fix_hint": f"R1(config)# interface {iface}\nR1(config-if)# no shutdown"
        }
    return None


def check_missing_helper_address(show_output: str, symptom: str) -> dict | None:
    """Flag if DHCP relay (ip helper-address) is missing and symptom mentions DHCP."""
    dhcp_symptom = re.search(r"dhcp|apipa|169\.254", symptom, re.IGNORECASE)
    no_helper    = re.search(r"helper.address.*missing|no helper|helper-address not", show_output, re.IGNORECASE)
    if dhcp_symptom and no_helper:
        return {
            "rule": "MISSING_HELPER_ADDRESS",
            "severity": "High",
            "detail": "DHCP symptom detected but ip helper-address appears missing in show output.",
            "fix_hint": "R1(config)# interface <LAN-facing interface>\nR1(config-if)# ip helper-address <DHCP-server-IP>"
        }
    return None


def check_vlan_not_in_trunk(show_output: str) -> dict | None:
    """Flag if show interfaces trunk output says a VLAN is NOT in the allowed list."""
    if re.search(r"NOT in allowed list|not in allowed", show_output, re.IGNORECASE):
        # Try to extract the VLAN number
        match = re.search(r"VLAN\s*(\d+)\s*(?:NOT|not) in allowed", show_output, re.IGNORECASE)
        vlan  = match.group(1) if match else "?"
        return {
            "rule": "VLAN_NOT_IN_TRUNK",
            "severity": "High",
            "detail": f"VLAN {vlan} is not in the trunk allowed VLAN list — traffic for this VLAN will be dropped.",
            "fix_hint": f"SW1(config)# interface <trunk-port>\nSW1(config-if)# switchport trunk allowed vlan add {vlan}"
        }
    return None


def check_nat_outside_missing(show_output: str) -> dict | None:
    """Flag if ip nat outside is not configured on WAN interface."""
    if re.search(r"nat outside.*NOT configured|no nat outside|nat outside not", show_output, re.IGNORECASE):
        return {
            "rule": "NAT_OUTSIDE_MISSING",
            "severity": "High",
            "detail": "ip nat outside not configured on the WAN-facing interface — NAT translations will not occur.",
            "fix_hint": "R1(config)# interface <WAN-interface>\nR1(config-if)# ip nat outside"
        }
    return None


def check_acl_implicit_deny(show_output: str, symptom: str) -> dict | None:
    """
    Flag if ACL appears to have a deny but no final permit ip any any,
    and symptom mentions blocking unexpected traffic.
    """
    has_deny   = re.search(r"deny (tcp|udp|ip|icmp)", show_output, re.IGNORECASE)
    no_permit  = not re.search(r"permit ip any any", show_output, re.IGNORECASE)
    bad_block  = re.search(r"block|drop|cannot|ospf|routing.*drop", symptom, re.IGNORECASE)
    if has_deny and no_permit and bad_block:
        return {
            "rule": "ACL_MISSING_PERMIT_ANY",
            "severity": "Critical",
            "detail": "ACL contains deny statements but no 'permit ip any any'. Implicit deny at end will block all unmatched traffic including routing protocols.",
            "fix_hint": "R1(config)# ip access-list extended <ACL-NAME>\nR1(config-ext-nacl)# permit ip any any"
        }
    return None


def check_ospf_area_mismatch(show_output: str) -> dict | None:
    """Flag if show output reveals two different area IDs on the same link."""
    areas = re.findall(r"area\s+(\d+)", show_output, re.IGNORECASE)
    unique_areas = set(areas)
    if len(unique_areas) > 1:
        return {
            "rule": "OSPF_AREA_MISMATCH",
            "severity": "High",
            "detail": f"Multiple OSPF area IDs detected: {unique_areas}. Routers on the same link must share the same area ID.",
            "fix_hint": "R2(config)# router ospf 1\nR2(config-router)# no network <subnet> <wildcard> area <wrong-area>\nR2(config-router)# network <subnet> <wildcard> area <correct-area>"
        }
    return None


def check_dhcp_no_dns(show_output: str, symptom: str) -> dict | None:
    """Flag if DHCP pool has no dns-server and symptom mentions DNS failure."""
    dns_symptom = re.search(r"dns|cannot browse|name resolution|domain", symptom, re.IGNORECASE)
    no_dns      = re.search(r"dns-server.*empty|dns-server not|no dns-server|dns-server 0\.0\.0\.0", show_output, re.IGNORECASE)
    if dns_symptom and no_dns:
        return {
            "rule": "DHCP_NO_DNS_SERVER",
            "severity": "Medium",
            "detail": "DHCP pool has no dns-server configured. Clients will not be able to resolve domain names.",
            "fix_hint": "R1(config)# ip dhcp pool <POOL-NAME>\nR1(dhcp-config)# dns-server 8.8.8.8"
        }
    return None


def check_stp_wrong_root(show_output: str, symptom: str) -> dict | None:
    """Flag if STP show output shows an unexpected switch elected as root."""
    if re.search(r"new switch.*root|elected as Root|wrong.*root bridge", show_output, re.IGNORECASE):
        return {
            "rule": "STP_WRONG_ROOT",
            "severity": "High",
            "detail": "An unintended switch has been elected as the STP Root Bridge. This can cause all traffic to flow through suboptimal paths.",
            "fix_hint": "SW-DIST(config)# spanning-tree vlan <vlan-id> root primary\n(Or manually set lower priority: spanning-tree vlan <id> priority 4096)"
        }
    return None


def check_ip_conflict(show_output: str) -> dict | None:
    """Flag if show ip dhcp conflict shows an entry."""
    if re.search(r"dhcp conflict|duplicate.*ip|same ip|conflict detected", show_output, re.IGNORECASE):
        match = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}).*conflict|conflict.*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", show_output, re.IGNORECASE)
        ip = match.group(1) or match.group(2) if match else "unknown"
        return {
            "rule": "IP_ADDRESS_CONFLICT",
            "severity": "High",
            "detail": f"IP address conflict detected for {ip}. Two devices are using the same IP, causing intermittent connectivity for both.",
            "fix_hint": f"R1(config)# ip dhcp excluded-address {ip}\nThen reassign the static device to a different IP outside the DHCP pool range."
        }
    return None


def check_hsrp_no_preempt(show_output: str, symptom: str) -> dict | None:
    """Flag if HSRP symptom and no preempt visible in show output."""
    hsrp_symptom = re.search(r"hsrp|standby|active router|gateway fail", symptom, re.IGNORECASE)
    no_preempt   = re.search(r"preempt.*not|no preempt", show_output, re.IGNORECASE)
    if hsrp_symptom and no_preempt:
        return {
            "rule": "HSRP_NO_PREEMPT",
            "severity": "Medium",
            "detail": "HSRP primary router does not have 'preempt' configured. After recovery, it will remain in Standby state instead of reclaiming the Active role.",
            "fix_hint": "R1(config)# interface <interface>\nR1(config-if)# standby 1 preempt"
        }
    return None


# ─── Rule Runner ──────────────────────────────────────────────────────────────

ALL_RULES = [
    check_interface_down,
    check_vlan_not_in_trunk,
    check_nat_outside_missing,
    check_ospf_area_mismatch,
    check_ip_conflict,
]

# Rules that also need the symptom text
SYMPTOM_RULES = [
    check_missing_helper_address,
    check_acl_implicit_deny,
    check_dhcp_no_dns,
    check_hsrp_no_preempt,
]


def run_all_rules(case: dict) -> list[dict]:
    """Run all deterministic rules against a single case. Returns list of findings."""
    show_output = case.get("show_output", "")
    symptom     = case.get("symptom", "")
    findings    = []

    for rule_fn in ALL_RULES:
        result = rule_fn(show_output)
        if result:
            findings.append(result)

    for rule_fn in SYMPTOM_RULES:
        result = rule_fn(show_output, symptom)
        if result:
            findings.append(result)

    return findings


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not CASES_FILE.exists():
        print(f"[ERROR] cases.csv not found at {CASES_FILE}")
        return

    results = []
    with open(CASES_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for case in reader:
            findings = run_all_rules(case)
            results.append({
                "case_id":          case["case_id"],
                "symptom":          case["symptom"],
                "expected_fault":   case["expected_fault"],
                "rule_findings":    findings,
                "rules_triggered":  len(findings),
                "pre_check_status": "FLAGGED" if findings else "CLEAN"
            })

    # Save results
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Print summary to console
    total   = len(results)
    flagged = sum(1 for r in results if r["pre_check_status"] == "FLAGGED")
    clean   = total - flagged

    print("\n" + "="*60)
    print("  NetSage AI — Rule Checker Results")
    print("="*60)
    print(f"  Total cases checked : {total}")
    print(f"  Flagged by rules    : {flagged}")
    print(f"  Passed (clean)      : {clean}")
    print("="*60)

    for r in results:
        status_icon = "⚠" if r["pre_check_status"] == "FLAGGED" else "✓"
        print(f"\n  {status_icon} [{r['case_id']}] {r['symptom'][:60]}...")
        if r["rule_findings"]:
            for finding in r["rule_findings"]:
                sev = finding["severity"].upper()
                print(f"      └─ [{sev}] {finding['rule']}: {finding['detail'][:70]}")
                print(f"         Fix: {finding['fix_hint'].splitlines()[0]}")

    print(f"\n  Full results saved to: {OUT_FILE}\n")


if __name__ == "__main__":
    main()
