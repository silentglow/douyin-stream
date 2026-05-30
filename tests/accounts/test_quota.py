from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, Mock, patch

from media_tools.accounts.quota import merge_consumption_record, merge_equity_claim_record, trigger_equity_claim_via_api


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


class TriggerEquityClaimTests(unittest.IsolatedAsyncioTestCase):
    async def test_trigger_equity_claim_calls_center_list_then_reward_notice(self) -> None:
        context = Mock()
        context.dispose = AsyncMock()

        api_json = AsyncMock(side_effect=[{"success": True, "data": ["center"]}, {"success": True, "data": ["reward"]}])

        with (
            patch("media_tools.accounts.quota.RequestsApiContext", return_value=context) as context_factory,
            patch("media_tools.accounts.quota.api_json", api_json),
        ):
            result = await trigger_equity_claim_via_api(cookie_string="cookie=value")

        context_factory.assert_called_once_with(cookie_string="cookie=value")
        self.assertEqual(
            [call.args[1] for call in api_json.await_args_list],
            [
                "https://api.qianwen.com/growth/user/task/benefit/center/list",
                "https://api.qianwen.com/growth/user/task/reward/notice",
            ],
        )
        self.assertEqual(result["center_list"], {"success": True, "data": ["center"]})
        self.assertEqual(result["reward_notice"], {"success": True, "data": ["reward"]})
        context.dispose.assert_awaited_once()
