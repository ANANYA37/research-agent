"""Regression tests for saved-report cache freshness rules."""

import unittest

from freshness import is_freshness_sensitive, should_use_cache


class FreshnessDetectionTests(unittest.TestCase):
    def test_time_sensitive_topics_bypass_history_cache(self):
        topics = (
            "latest AI regulation news",
            "weather in Mumbai today",
            "live score for the India match",
            "current stock price for NVIDIA",
            "election results this week",
        )

        for topic in topics:
            with self.subTest(topic=topic):
                self.assertTrue(is_freshness_sensitive(topic))
                self.assertFalse(should_use_cache(topic))

    def test_stable_topics_can_reuse_history_cache(self):
        topics = (
            "history of the Silk Road",
            "how transformer neural networks work",
            "impact of AI on healthcare",
        )

        for topic in topics:
            with self.subTest(topic=topic):
                self.assertFalse(is_freshness_sensitive(topic))
                self.assertTrue(should_use_cache(topic))

    def test_force_fresh_always_bypasses_history_cache(self):
        self.assertFalse(should_use_cache("history of the Silk Road", force_fresh=True))


if __name__ == "__main__":
    unittest.main()
