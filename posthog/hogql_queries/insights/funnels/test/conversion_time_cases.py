from datetime import datetime
from typing import cast

from posthog.constants import INSIGHT_FUNNELS, FunnelOrderType
from posthog.hogql_queries.insights.funnels.funnels_query_runner import FunnelsQueryRunner
from posthog.hogql_queries.legacy_compatibility.filter_to_query import filter_to_query
from posthog.models.filters import Filter
from posthog.schema import FunnelsQuery
from posthog.test.base import APIBaseTest
from posthog.test.test_journeys import journeys_for


def funnel_conversion_time_test_factory(funnel_order_type: FunnelOrderType, FunnelPerson):
    class TestFunnelConversionTime(APIBaseTest):
        def _get_actor_ids_at_step(self, filter, funnel_step, breakdown_value=None):
            filter = Filter(data=filter, team=self.team)
            person_filter = filter.shallow_clone({"funnel_step": funnel_step, "funnel_step_breakdown": breakdown_value})
            _, serialized_result, _ = FunnelPerson(person_filter, self.team).get_actors()

            return [val["id"] for val in serialized_result]

        def test_funnel_with_multiple_incomplete_tries(self):
            filters = {
                "insight": INSIGHT_FUNNELS,
                "funnel_order_type": funnel_order_type,
                "events": [
                    {"id": "user signed up", "type": "events", "order": 0},
                    {"id": "$pageview", "type": "events", "order": 1},
                    {"id": "something else", "type": "events", "order": 2},
                ],
                "funnel_window_days": 1,
                "date_from": "2021-05-01 00:00:00",
                "date_to": "2021-05-14 00:00:00",
            }

            people = journeys_for(
                {
                    "person1": [
                        # person1 completed funnel on 2021-05-01
                        {
                            "event": "user signed up",
                            "timestamp": datetime(2021, 5, 1, 1),
                        },
                        {"event": "$pageview", "timestamp": datetime(2021, 5, 1, 2)},
                        {
                            "event": "something else",
                            "timestamp": datetime(2021, 5, 1, 3),
                        },
                        # person1 completed part of funnel on 2021-05-03 and took 2 hours to convert
                        {
                            "event": "user signed up",
                            "timestamp": datetime(2021, 5, 3, 4),
                        },
                        {"event": "$pageview", "timestamp": datetime(2021, 5, 3, 5)},
                        # person1 completed part of funnel on 2021-05-04 and took 3 hours to convert
                        {
                            "event": "user signed up",
                            "timestamp": datetime(2021, 5, 4, 7),
                        },
                        {"event": "$pageview", "timestamp": datetime(2021, 5, 4, 10)},
                    ]
                },
                self.team,
            )

            query = cast(FunnelsQuery, filter_to_query(filters))
            results = FunnelsQueryRunner(query=query, team=self.team).calculate().results

            self.assertEqual(results[0]["count"], 1)
            self.assertEqual(
                results[1]["average_conversion_time"], 3600
            )  # one hour to convert, disregard the incomplete tries
            self.assertEqual(results[1]["median_conversion_time"], 3600)

            # check ordering of people in every step
            self.assertCountEqual(self._get_actor_ids_at_step(filters, 1), [people["person1"].uuid])

        def test_funnel_step_conversion_times(self):
            filters = {
                "insight": INSIGHT_FUNNELS,
                "funnel_order_type": funnel_order_type,
                "events": [
                    {"id": "sign up", "order": 0},
                    {"id": "play movie", "order": 1},
                    {"id": "buy", "order": 2},
                ],
                "date_from": "2020-01-01",
                "date_to": "2020-01-08",
                "funnel_window_days": 7,
            }

            journeys_for(
                {
                    "person1": [
                        {"event": "sign up", "timestamp": datetime(2020, 1, 1, 12)},
                        {"event": "play movie", "timestamp": datetime(2020, 1, 1, 13)},
                        {"event": "buy", "timestamp": datetime(2020, 1, 1, 15)},
                    ],
                    "person2": [
                        {"event": "sign up", "timestamp": datetime(2020, 1, 2, 14)},
                        {"event": "play movie", "timestamp": datetime(2020, 1, 2, 16)},
                    ],
                    "person3": [
                        {"event": "sign up", "timestamp": datetime(2020, 1, 2, 14)},
                        {"event": "play movie", "timestamp": datetime(2020, 1, 2, 16)},
                        {"event": "buy", "timestamp": datetime(2020, 1, 2, 17)},
                    ],
                },
                self.team,
            )

            query = cast(FunnelsQuery, filter_to_query(filters))
            results = FunnelsQueryRunner(query=query, team=self.team).calculate().results

            self.assertEqual(results[0]["average_conversion_time"], None)
            self.assertEqual(results[1]["average_conversion_time"], 6000)
            self.assertEqual(results[2]["average_conversion_time"], 5400)

            self.assertEqual(results[0]["median_conversion_time"], None)
            self.assertEqual(results[1]["median_conversion_time"], 7200)
            self.assertEqual(results[2]["median_conversion_time"], 5400)

        def test_funnel_times_with_different_conversion_windows(self):
            filters = {
                "insight": INSIGHT_FUNNELS,
                "funnel_order_type": funnel_order_type,
                "events": [
                    {"id": "user signed up", "type": "events", "order": 0},
                    {"id": "pageview", "type": "events", "order": 1},
                ],
                "funnel_window_interval": 14,
                "funnel_window_interval_unit": "day",
                "date_from": "2020-01-01",
                "date_to": "2020-01-14",
            }

            # event
            people = journeys_for(
                {
                    "stopped_after_signup1": [
                        {
                            "event": "user signed up",
                            "timestamp": datetime(2020, 1, 2, 14),
                        },
                        {"event": "pageview", "timestamp": datetime(2020, 1, 2, 14, 5)},
                    ],
                    "stopped_after_signup2": [
                        {
                            "event": "user signed up",
                            "timestamp": datetime(2020, 1, 2, 14, 3),
                        }
                    ],
                    "stopped_after_signup3": [
                        {
                            "event": "user signed up",
                            "timestamp": datetime(2020, 1, 2, 12),
                        },
                        {
                            "event": "pageview",
                            "timestamp": datetime(2020, 1, 2, 12, 15),
                        },
                    ],
                },
                self.team,
            )

            query = cast(FunnelsQuery, filter_to_query(filters))
            results = FunnelsQueryRunner(query=query, team=self.team).calculate().results

            self.assertEqual(results[0]["count"], 3)
            self.assertEqual(results[1]["count"], 2)
            self.assertEqual(results[1]["average_conversion_time"], 600)

            self.assertCountEqual(
                self._get_actor_ids_at_step(filters, 1),
                [
                    people["stopped_after_signup1"].uuid,
                    people["stopped_after_signup2"].uuid,
                    people["stopped_after_signup3"].uuid,
                ],
            )

            self.assertCountEqual(
                self._get_actor_ids_at_step(filters, 2),
                [
                    people["stopped_after_signup1"].uuid,
                    people["stopped_after_signup3"].uuid,
                ],
            )

            filters = {**filters, "funnel_window_interval": 5, "funnel_window_interval_unit": "minute"}

            query = cast(FunnelsQuery, filter_to_query(filters))
            result4 = FunnelsQueryRunner(query=query, team=self.team).calculate().results

            self.assertNotEqual(results, result4)
            self.assertEqual(result4[0]["count"], 3)
            self.assertEqual(result4[1]["count"], 1)
            self.assertEqual(result4[1]["average_conversion_time"], 300)

            self.assertCountEqual(
                self._get_actor_ids_at_step(filters, 1),
                [
                    people["stopped_after_signup1"].uuid,
                    people["stopped_after_signup2"].uuid,
                    people["stopped_after_signup3"].uuid,
                ],
            )

            self.assertCountEqual(
                self._get_actor_ids_at_step(filters, 2),
                [people["stopped_after_signup1"].uuid],
            )

    return TestFunnelConversionTime
