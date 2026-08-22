import unittest

from app.alert_noise import reduce_alert_noise


class AlertNoiseReductionTests(unittest.TestCase):
    def test_suppresses_low_severity_and_duplicate_alerts(self):
        result = reduce_alert_noise(
            [
                {"alert_id": "a-1", "service": "checkout", "alert_name": "HighErrorRate", "severity": "warning", "timestamp": "2026-08-22T10:00:00Z"},
                {"alert_id": "a-2", "service": "checkout", "alert_name": "HighErrorRate", "severity": "warning", "timestamp": "2026-08-22T10:04:00Z"},
                {"alert_id": "a-3", "service": "checkout", "alert_name": "DebugSignal", "severity": "info", "timestamp": "2026-08-22T10:05:00Z"},
                {"alert_id": "a-4", "service": "checkout", "alert_name": "HighErrorRate", "severity": "warning", "timestamp": "2026-08-22T10:16:00Z"},
            ],
            cooldown_minutes=15,
        )

        self.assertEqual([item["alert_id"] for item in result["actionable_alerts"]], ["a-1", "a-4"])
        self.assertEqual(result["suppressed_alerts"][0]["suppression_reason"], "below_minimum_severity")
        self.assertEqual(result["suppressed_alerts"][1]["suppression_reason"], "duplicate_within_cooldown")
        self.assertEqual(result["summary"]["reduction_percent"], 50.0)


if __name__ == "__main__":
    unittest.main()
