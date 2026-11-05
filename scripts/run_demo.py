"""Reproduce the contract comparison without a model, paid API, or network."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from decision_memory import Ledger, Principal, pack
from decision_memory.ledger import envelope


def naive_recent(ledger, case):
    # Intentionally incomplete baseline: latest observed records and a byte cap.
    # Its missing controls are the subject of the comparison, not an ECC benchmark.
    candidates = sorted((r for r in ledger.records.values()
                         if r["tenant"] == case["tenant"] and r["observed_at"] <= case["as_of"]),
                        key=lambda r: (-r["observed_at"], r["id"]))
    selected, seen = [], set()
    for record in candidates:
        if record["key"] in seen:
            continue
        if len(envelope(case["tenant"], case["as_of"], selected + [record])) <= case["budget_bytes"]:
            selected.append(record)
            seen.add(record["key"])
    return "ready", {r["id"] for r in selected}, envelope(case["tenant"], case["as_of"], selected)


def validity_recent(ledger, principal, case):
    """Stronger ablation: keep integrity gates, remove required-fact reservation."""
    try:
        valid, _ = ledger.resolve(principal, case["tenant"], case["as_of"])
    except PermissionError:
        return "denied", set(), b""
    if any(k not in valid for k in case["required_keys"]):
        return "refused", set(), b""
    minimum = [valid[k] for k in case["required_keys"]]
    if len(envelope(case["tenant"], case["as_of"], minimum)) > case["budget_bytes"]:
        return "refused", set(), b""
    selected = []
    for record in sorted(valid.values(), key=lambda r: (-r["observed_at"], r["id"])):
        if len(envelope(case["tenant"], case["as_of"], selected + [record])) <= case["budget_bytes"]:
            selected.append(record)
    return "ready", {r["id"] for r in selected}, envelope(case["tenant"], case["as_of"], selected)


def contract_pass(case, status, ids, payload, ledger):
    if status != case["expected_status"]:
        return False
    if status != "ready":
        return not payload
    if not set(case["expected_required_ids"]).issubset(ids):
        return False
    if len(payload) > case["budget_bytes"]:
        return False
    valid, _ = ledger.resolve(Principal("fixture-host", frozenset({"grocer-a"})),
                              case["tenant"], case["as_of"])
    return ids.issubset({r["id"] for r in valid.values()})


def run(destination=ROOT / "results"):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    ledger = Ledger.load(ROOT / "data/ledger.json")
    cases = json.loads((ROOT / "data/cases.json").read_text())
    principal = Principal("fixture-host", frozenset({"grocer-a"}))
    rows = []
    for case in cases:
        baseline_status, baseline_ids, baseline_payload = naive_recent(ledger, case)
        valid_status, valid_ids, valid_payload = validity_recent(ledger, principal, case)
        try:
            result = pack(ledger, principal, case["tenant"], case["as_of"],
                          case["required_keys"], case["query"], case["budget_bytes"])
            status, ids, payload, reason = result.status, set(result.selected), result.payload, result.reason
            diagnostics = result.diagnostics
        except PermissionError:
            status, ids, payload, reason, diagnostics = "denied", set(), b"", "tenant_not_authorized", {}
        rows.append({"case": case["id"], "expected_status": case["expected_status"],
                     "baseline": {"status": baseline_status, "ids": sorted(baseline_ids),
                                  "bytes": len(baseline_payload), "pass": contract_pass(
                                      case, baseline_status, baseline_ids, baseline_payload, ledger)},
                     "validity_recent": {"status": valid_status, "ids": sorted(valid_ids),
                                         "bytes": len(valid_payload), "pass": contract_pass(
                                             case, valid_status, valid_ids, valid_payload, ledger)},
                     "guarded": {"status": status, "reason": reason, "ids": sorted(ids),
                                 "bytes": len(payload), "pass": contract_pass(case, status, ids, payload, ledger),
                                 "diagnostics": diagnostics}})
        if case["id"] == "mandatory-low-recency":
            (destination / "example-context.json").write_bytes(payload + b"\n")
    metrics = {"cases": len(rows), "baseline_passes": sum(r["baseline"]["pass"] for r in rows),
               "validity_recent_passes": sum(r["validity_recent"]["pass"] for r in rows),
               "guarded_passes": sum(r["guarded"]["pass"] for r in rows),
               "ready": sum(r["guarded"]["status"] == "ready" for r in rows),
               "refused": sum(r["guarded"]["status"] == "refused" for r in rows),
               "denied": sum(r["guarded"]["status"] == "denied" for r in rows),
               "dataset_sha256": hashlib.sha256((ROOT / "data/ledger.json").read_bytes()).hexdigest(),
               "cases_sha256": hashlib.sha256((ROOT / "data/cases.json").read_bytes()).hexdigest(),
               "interpretation": "Authored protocol contracts, not LLM answer quality or an adversarial security assessment."}
    (destination / "metrics.json").write_bytes((json.dumps(metrics, indent=2) + "\n").encode())
    (destination / "case-results.json").write_bytes((json.dumps(rows, indent=2) + "\n").encode())
    lines = ["# Contract experiment", "", "All inputs are fictional. No model or external API was called.", "",
             f"The guarded packer met {metrics['guarded_passes']}/{metrics['cases']} authored contracts; "
             f"the deliberately incomplete recent-first baseline met {metrics['baseline_passes']}/{metrics['cases']}, "
             f"and validity-aware recent-first packing met {metrics['validity_recent_passes']}/{metrics['cases']}.", "",
             "| Case | Expected | Recent-first | Validity + recent-first | Guarded |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['case']} | {r['expected_status']} | {'pass' if r['baseline']['pass'] else 'fail'} | {'pass' if r['validity_recent']['pass'] else 'fail'} | {'pass' if r['guarded']['pass'] else 'fail'} |")
    lines += ["", "These cases target known failure boundaries. They are not a representative distribution of agent tasks,",
              "and passing them does not establish prompt-injection resistance, correct model answers, or production authorization.", ""]
    (destination / "report.md").write_bytes("\n".join(lines).encode())
    print(json.dumps(metrics, indent=2))
    return metrics


if __name__ == "__main__":
    run()
