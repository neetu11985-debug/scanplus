"""Synthetic offline decisions, not evidence of live monitoring or delivery."""
import copy
import json
import unittest

from storage_usage import evaluate_usage

SCOPE = {"provider": "fixture", "project": "synthetic-db", "environment": "test",
         "console_url": "https://console.example.test/project/synthetic-db"}


class StorageUsageTests(unittest.TestCase):
    def check(self, used, quota=100, now=100, state=None, **kwargs):
        metric = {"used_bytes": used, "quota_bytes": quota, "observed_at": now}
        return evaluate_usage(SCOPE, metric, now=now, state=state, **kwargs)

    def test_exact_thresholds_and_jumps(self):
        for used, threshold in ((0, None), (69, None), (70, 70), (84, 70),
                                (85, 85), (94, 85), (95, 95), (120, 95)):
            result = self.check(used)
            self.assertEqual([e["threshold_percent"] for e in result["events"]],
                             [] if threshold is None else [threshold])

    def test_repeats_escalation_and_strict_rearm(self):
        state = None
        for now, (used, expected) in enumerate(((70, 70), (70, None), (85, 85),
                (95, 95), (80, None), (95, None), (60, None), (70, None),
                (59, None), (70, 70)), 100):
            result = self.check(used, now=now, state=state)
            state = result["state"]
            self.assertEqual([e["threshold_percent"] for e in result["events"]],
                             [] if expected is None else [expected])

    def test_quota_change_is_not_automatic_rearm(self):
        state = self.check(85)["state"]
        result = self.check(85, quota=90, now=200, state=state)
        self.assertEqual(result["events"], [])
        result = self.check(85, quota=80, now=300, state=result["state"])
        event = result["events"][0]
        self.assertEqual(event["threshold_percent"], 95)
        self.assertTrue(event["quota_changed"])
        self.assertIsNone(event["growth_bytes_per_hour"])
        result = self.check(85, quota=200, now=400, state=result["state"])
        self.assertEqual(result["state"]["highest_alert"], 0)

    def test_invalid_metrics_fail_without_leaking_values(self):
        for value in (-1, 1.5, float("inf"), float("nan"), True, "secret", None, 2**63):
            for field in ("used_bytes", "quota_bytes", "observed_at"):
                metric = {"used_bytes": 70, "quota_bytes": 100, "observed_at": 100}
                metric[field] = value
                result = evaluate_usage(SCOPE, metric, now=100, failure_threshold=1)
                self.assertEqual(result["status"], "invalid_metric")
                self.assertEqual(result["events"][0]["reason"], "invalid_metric")
                self.assertNotIn("secret", json.dumps(result, allow_nan=False))
        self.assertEqual(self.check(1, quota=0)["status"], "invalid_metric")
        self.assertEqual(evaluate_usage(SCOPE, {"secret": "private"}, now=100)["status"], "invalid_metric")

    def test_stale_future_conflicting_and_out_of_order(self):
        state = self.check(70)["state"]
        for observed, used, reason in ((101, 70, "future_metric"),
                (0, 70, "stale_metric"), (99, 70, "out_of_order_metric"),
                (100, 71, "conflicting_metric")):
            now = 101 if observed != 101 else 100
            # Avoid same-check deduplication for future test.
            if reason == "future_metric":
                observed, now = 103, 102
            result = evaluate_usage(SCOPE, {"used_bytes": used, "quota_bytes": 100,
                "observed_at": observed}, now=now, state=state, max_age_seconds=10)
            self.assertEqual(result["status"], reason)
            self.assertEqual(result["state"]["last_sample"], state["last_sample"])
            self.assertEqual(result["state"]["highest_alert"], 70)

    def test_repeated_failures_report_once_and_recover(self):
        state = None
        for now in range(100, 105):
            result = evaluate_usage(SCOPE, None, now=now, state=state)
            self.assertEqual(len(result["events"]), int(now == 102))
            state = result["state"]
        result = self.check(0, now=105, state=state)
        self.assertEqual(result["state"]["consecutive_failures"], 0)
        state = result["state"]
        for now in range(106, 109):
            result = evaluate_usage(SCOPE, None, now=now, state=state)
            state = result["state"]
        self.assertEqual(len(result["events"]), 1)

    def test_duplicate_samples_do_not_claim_recovery(self):
        state = self.check(70)["state"]
        state = evaluate_usage(SCOPE, None, now=101, state=state)["state"]
        metric = {"used_bytes": 70, "quota_bytes": 100, "observed_at": 100}
        result = evaluate_usage(SCOPE, metric, now=102, state=state)
        self.assertEqual(result["status"], "duplicate_sample")
        self.assertEqual(result["state"]["consecutive_failures"], 1)
        result = evaluate_usage(SCOPE, metric, now=103, state=result["state"], max_age_seconds=2)
        self.assertEqual(result["status"], "stale_metric")

    def test_state_json_roundtrip_purity_dedup_and_clock(self):
        state = self.check(70)["state"]
        snapshot = copy.deepcopy(state)
        result = self.check(85, now=200, state=json.loads(json.dumps(state)))
        self.assertEqual(state, snapshot)
        self.assertEqual(result["events"][0]["growth_bytes_per_hour"], 540)
        self.assertEqual(self.check(95, now=200, state=result["state"])["status"], "duplicate_check")
        with self.assertRaises(ValueError):
            self.check(95, now=199, state=result["state"])
        json.dumps(result, allow_nan=False)

    def test_invalid_configuration_and_state_fail_closed(self):
        for kwargs in ({"max_age_seconds": 0}, {"failure_threshold": True}, {"now": float("nan")}):
            with self.assertRaises(ValueError):
                self.check(70, **kwargs)
        state = self.check(70)["state"]
        for field, value in (("version", 2), ("highest_alert", 71),
                             ("failure_reported", "yes"), ("last_checked_at", 1)):
            broken = dict(state, **{field: value})
            with self.assertRaises(ValueError):
                self.check(70, now=200, state=broken)
        for field, value in (("project", "other-db"), ("console_url", "http://example.test"),
                ("console_url", "https://user:secret@example.test"),
                ("console_url", "https://example.test?token=secret"),
                ("console_url", "https://example.test/#secret")):
            scope = dict(SCOPE, **{field: value})
            with self.assertRaises(ValueError):
                evaluate_usage(scope, None, now=200, state=state)

    def test_staleness_boundary_and_large_integer_metrics(self):
        metric = {"used_bytes": 70, "quota_bytes": 100, "observed_at": 100}
        self.assertEqual(evaluate_usage(SCOPE, metric, now=110, max_age_seconds=10)["status"], "ok")
        result = self.check(2**63-1, quota=2**63-1)
        self.assertEqual(result["events"][0]["usage_percent"], 100)


if __name__ == "__main__":
    unittest.main()
