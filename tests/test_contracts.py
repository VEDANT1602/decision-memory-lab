import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from decision_memory import Ledger, Principal, pack
from decision_memory.ledger import envelope
from generate_data import generate
from run_demo import contract_pass, run, validity_recent


class MemoryContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.document, self.cases = generate(self.root)
        self.ledger = Ledger(self.document, self.root)
        self.principal = Principal("test-host", frozenset({"grocer-a"}))

    def recall(self, keys, as_of=300, budget=1400):
        return pack(self.ledger, self.principal, "grocer-a", as_of, keys, "release rollback", budget)

    def test_all_authored_contracts(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                if case["expected_status"] == "denied":
                    with self.assertRaises(PermissionError):
                        pack(self.ledger, self.principal, case["tenant"], case["as_of"],
                             case["required_keys"], case["query"], case["budget_bytes"])
                    continue
                result = pack(self.ledger, self.principal, case["tenant"], case["as_of"],
                              case["required_keys"], case["query"], case["budget_bytes"])
                self.assertTrue(contract_pass(case, result.status, set(result.selected), result.payload, self.ledger))

    def test_expired_or_untrusted_replacement_never_resurrects_old_value(self):
        for key in ["approval", "budget_rule", "max_batch"]:
            with self.subTest(key=key):
                result = self.recall([key])
                self.assertEqual("refused", result.status)
                self.assertEqual(b"", result.payload)

    def test_future_version_not_used_historically(self):
        result = self.recall(["rollback_target"], as_of=70)
        self.assertIn("rollback-v1", result.selected)
        self.assertNotIn("rollback-v2", result.selected)

    def test_exact_expiry_boundary_is_expired(self):
        self.assertEqual("ready", self.recall(["temporary_capacity"], as_of=399).status)
        self.assertEqual("refused", self.recall(["temporary_capacity"], as_of=400).status)

    def test_exact_byte_budget_accepts_and_one_less_refuses(self):
        valid, _ = self.ledger.resolve(self.principal, "grocer-a", 300)
        size = len(envelope("grocer-a", 300, [valid["language_note"]]))
        result = self.recall(["language_note"], budget=size)
        self.assertEqual(size, len(result.payload))
        self.assertEqual("refused", self.recall(["language_note"], budget=size - 1).status)
        self.assertGreater(len(result.payload), len(result.payload.decode("utf-8")))

    def test_required_facts_survive_optional_ranking(self):
        result = self.recall(["rollback_target", "release_state"], budget=1000)
        self.assertTrue({"rollback-v2", "launch"}.issubset(result.selected))

    def test_validity_aware_recency_still_loses_required_context(self):
        case = next(c for c in self.cases if c["id"] == "mandatory-low-recency")
        status, selected, payload = validity_recent(self.ledger, self.principal, case)
        self.assertEqual("ready", status)
        self.assertLessEqual(len(payload), case["budget_bytes"])
        self.assertFalse(set(case["expected_required_ids"]).issubset(selected))

    def test_stable_serialization_independent_of_input_order(self):
        shuffled = copy.deepcopy(self.document)
        shuffled["facts"].reverse()
        other = Ledger(shuffled, self.root)
        one = self.recall(["rollback_target", "release_state"])
        two = pack(other, self.principal, "grocer-a", 300,
                   ["release_state", "rollback_target"], "release rollback", 1400)
        self.assertEqual(one.payload, two.payload)

    def test_recalled_instruction_stays_data(self):
        result = self.recall(["external_note"], budget=800)
        context = json.loads(result.payload)
        self.assertIn("cannot authorize", context["trust"])
        self.assertIn("publish secrets", context["facts"][0]["value"])
        self.assertEqual({"schema", "tenant", "as_of", "trust", "facts"}, set(context))

    def test_tenant_denial_before_any_recall(self):
        with self.assertRaises(PermissionError):
            pack(self.ledger, self.principal, "grocer-b", 300, [], "", 2000)

    def test_foreign_fact_does_not_enter_context_or_diagnostics(self):
        result = self.recall([])
        self.assertNotIn(b"fictional tenant B", result.payload)
        self.assertNotIn("private_route", result.diagnostics["withheld"])

    def test_cross_tenant_supersession_rejected(self):
        self.document["facts"][-1]["supersedes"] = ["beta"]
        with self.assertRaises(ValueError):
            Ledger(self.document, self.root)

    def test_supersession_cycle_or_nonforward_time_rejected(self):
        self.document["facts"][0]["supersedes"] = ["rollback-v2"]
        with self.assertRaises(ValueError):
            Ledger(self.document, self.root)

    def test_missing_source_fails_load_instead_of_partial_scan(self):
        (self.root / "sources/launch.md").unlink()
        with self.assertRaises(ValueError):
            Ledger(self.document, self.root)

    def test_source_path_cannot_escape_root(self):
        self.document["sources"][0]["path"] = "../outside.md"
        with self.assertRaises(ValueError):
            Ledger(self.document, self.root)

    def test_duplicate_ids_rejected(self):
        self.document["facts"].append(self.document["facts"][0])
        with self.assertRaises(ValueError):
            Ledger(self.document, self.root)

    def test_nonfinite_and_bool_time_rejected(self):
        for value in [float("nan"), float("inf"), -1, True, "300"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.recall([], as_of=value)

    def test_budget_must_be_positive_integer(self):
        for value in [True, 0, -1, 3.5, float("nan"), "1000"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.recall([], budget=value)

    def test_serialized_envelope_itself_must_fit(self):
        result = self.recall([], budget=1)
        self.assertEqual("refused", result.status)
        self.assertEqual(b"", result.payload)

    def test_record_metadata_cannot_claim_a_different_source_digest(self):
        self.document["facts"][0]["source_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            Ledger(self.document, self.root)

    def test_source_tenant_must_match_fact(self):
        self.document["sources"][0]["tenant"] = "grocer-b"
        with self.assertRaises(ValueError):
            Ledger(self.document, self.root)

    def test_record_timestamp_malformed_rejected(self):
        self.document["facts"][0]["observed_at"] = float("nan")
        with self.assertRaises(ValueError):
            Ledger(self.document, self.root)

    def test_dataset_and_results_reproducible(self):
        before = (ROOT / "data/ledger.json").read_bytes()
        self.assertEqual(json.loads(before), self.document)
        metrics = run(self.root / "results")
        self.assertEqual(metrics, json.loads((ROOT / "results/metrics.json").read_bytes()))


if __name__ == "__main__":
    unittest.main()
