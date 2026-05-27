from __future__ import annotations

import unittest

from media_tools.transcribe.quota import merge_consumption_record, merge_equity_claim_record


class QuotaTests(unittest.TestCase):
    def test_merge_consumption_record_accumulates_existing_minutes(self) -> None:
        merged = merge_consumption_record(
            {"consumedMinutes": 5, "lastEquityClaimAt": "keep-me"},
            consumed_minutes=7,
            before_remaining=80,
            after_remaining=73,
            updated_at="2026-04-10T00:00:00+00:00",
        )

        self.assertEqual(merged["consumedMinutes"], 12)
        self.assertEqual(merged["lastBeforeRemaining"], 80)
        self.assertEqual(merged["lastAfterRemaining"], 73)
        self.assertEqual(merged["lastEquityClaimAt"], "keep-me")

    def test_merge_equity_claim_record_preserves_consumption_fields(self) -> None:
        merged = merge_equity_claim_record(
            {"consumedMinutes": 9},
            before_remaining=40,
            after_remaining=55,
            claimed_at="2026-04-10T00:00:00+00:00",
        )

        self.assertEqual(merged["consumedMinutes"], 9)
        self.assertEqual(merged["lastEquityBeforeRemaining"], 40)
        self.assertEqual(merged["lastEquityAfterRemaining"], 55)
        self.assertEqual(merged["lastEquityClaimAt"], "2026-04-10T00:00:00+00:00")
