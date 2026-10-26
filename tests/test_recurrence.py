"""Offline tests for recurrence math."""

import datetime as dt
import unittest

from home_maintenance import recurrence
from home_maintenance.recurrence import add_days, classify_due, next_due, parse_cost


class ParseDateTests(unittest.TestCase):
    def test_valid_iso(self):
        self.assertEqual(recurrence.parse_date("2026-10-26"), dt.date(2026, 10, 26))

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            recurrence.parse_date("26/10/2026")
        with self.assertRaises(ValueError):
            recurrence.parse_date("2026-13-01")
        with self.assertRaises(ValueError):
            recurrence.parse_date("2026-2-30")

    def test_rejects_non_string(self):
        with self.assertRaises(ValueError):
            recurrence.parse_date(20261026)


class NextDueTests(unittest.TestCase):
    def test_plain_interval(self):
        self.assertEqual(next_due(dt.date(2026, 10, 1), 90), dt.date(2026, 12, 30))

    def test_month_boundary_and_year_rollover(self):
        self.assertEqual(next_due(dt.date(2026, 12, 20), 30), dt.date(2027, 1, 19))

    def test_leap_year_february(self):
        self.assertEqual(next_due(dt.date(2024, 1, 31), 29), next_due(dt.date(2024, 1, 31), 29))
        self.assertEqual(next_due(dt.date(2024, 1, 31), 29), dt.date(2024, 2, 29))
        self.assertEqual(next_due(dt.date(2023, 1, 31), 29), dt.date(2023, 3, 1))

    def test_years_long_interval(self):
        self.assertEqual(next_due(dt.date(2020, 2, 29), 1461), dt.date(2024, 2, 29))

    def test_seasonal_pushes_to_first_of_allowed_month(self):
        due = next_due(dt.date(2026, 4, 10), 90, [4, 10])
        self.assertEqual(due, dt.date(2026, 10, 1))

    def test_seasonal_skips_winter(self):
        due = next_due(dt.date(2026, 9, 30), 60, [4, 10])
        self.assertEqual(due, dt.date(2027, 4, 1))

    def test_seasonal_candidate_already_in_season(self):
        due = next_due(dt.date(2026, 3, 25), 30, [4, 10])
        self.assertEqual(due, dt.date(2026, 4, 1))

    def test_season_month_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            next_due(dt.date(2026, 1, 1), 30, [13])
        with self.assertRaises(ValueError):
            recurrence.normalize_season_months("december")

    def test_invalid_interval_rejected(self):
        with self.assertRaises(ValueError):
            next_due(dt.date(2026, 1, 1), 0)


class ClassifyDueTests(unittest.TestCase):
    def setUp(self):
        self.as_of = dt.date(2026, 10, 26)

    def test_overdue_when_past(self):
        self.assertEqual(classify_due(self.as_of, self.as_of), "overdue")
        self.assertEqual(classify_due(add_days(self.as_of, -5), self.as_of), "overdue")

    def test_due_soon_within_horizon(self):
        self.assertEqual(classify_due(add_days(self.as_of, 3), self.as_of), "due_soon")
        self.assertEqual(classify_due(add_days(self.as_of, 14), self.as_of), "due_soon")

    def test_ok_beyond_horizon(self):
        self.assertEqual(classify_due(add_days(self.as_of, 15), self.as_of), "ok")
        self.assertEqual(classify_due(add_days(self.as_of, 200), self.as_of, 14), "ok")

    def test_custom_horizon(self):
        self.assertEqual(classify_due(add_days(self.as_of, 40), self.as_of, 40), "due_soon")


class CostTests(unittest.TestCase):
    def test_accepts_numbers(self):
        self.assertEqual(parse_cost(189), 189.0)
        self.assertEqual(parse_cost(12.345), 12.35)
        self.assertEqual(parse_cost(None), None)

    def test_rejects_negative_and_bogus(self):
        for bad in (-1, -0.01, "free", True, [5], float("inf")):
            with self.assertRaises(ValueError):
                parse_cost(bad)


if __name__ == "__main__":
    unittest.main()
