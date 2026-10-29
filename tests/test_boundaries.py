import sys, unittest
from pathlib import Path
from fractions import Fraction
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from analyze import confusion, run_bounds, quantile, ratio
from retrieve import parse_line


class WeatherBoundaries(unittest.TestCase):
    def test_threshold_equality_is_not_positive(self):
        self.assertEqual(confusion([300, 301, 299], 30)["positive_slots"], 1)

    def test_mean_equality_can_hide_positive_sample(self):
        r = confusion([200, 400], 30)
        self.assertEqual((r["tp"], r["fp"], r["fn"], r["tn"]), (0, 0, 1, 1))

    def test_above_threshold_mean_creates_false_positive(self):
        r = confusion([290, 330], 30)
        self.assertEqual((r["tp"], r["fp"], r["fn"], r["tn"]), (1, 1, 0, 0))

    def test_missing_is_unknown_not_cold(self):
        r = confusion([-9999, 400], 30)
        self.assertEqual(
            (
                r["observed_slots"],
                r["unknown_slots"],
                r["positive_lower"],
                r["positive_upper"],
            ),
            (1, 1, 1, 2),
        )

    def test_empty_month_retains_undefined_mean(self):
        self.assertEqual(confusion([-9999], 30)["mean_classification"], "UNDEFINED")
        self.assertIsNone(ratio(0, 0))

    def test_unknown_breaks_confirmed_but_bridges_possible_run(self):
        self.assertEqual(run_bounds([400, 400, -9999, 400, 200, 400], 30), (2, 4))

    def test_all_unknown_run_bounds(self):
        self.assertEqual(run_bounds([-9999] * 3, 30), (0, 3))

    def test_leap_year_hour_count(self):
        self.assertEqual(
            int((datetime(2021, 1, 1) - datetime(2020, 1, 1)).total_seconds() / 3600),
            8784,
        )

    def test_nearest_rank_quantile(self):
        self.assertEqual(quantile(list(range(100)), 95), 94)
        self.assertEqual(quantile([10, 20], 99), 20)
        self.assertEqual(quantile([], 95), "NA")

    def test_exact_mean_comparison(self):
        self.assertEqual(ratio(1, 3), Fraction(1, 3))
        self.assertEqual(
            confusion([299, 300, 301], 30)["mean_classification"], "NONPOSITIVE"
        )

    def test_raw_missing_sentinel_and_calendar(self):
        line = "2020 02 29 23" + "".join(
            f"{v:6d}" for v in [-9999, 0, 0, 0, 0, 0, 0, 0]
        )
        stamp, t = parse_line(line, 2020)
        self.assertEqual((stamp, t), (datetime(2020, 2, 29, 23), -9999))

    def test_invalid_source_year_rejected(self):
        line = "2020 02 29 23" + "".join(f"{v:6d}" for v in [200, 0, 0, 0, 0, 0, 0, 0])
        with self.assertRaises(AssertionError):
            parse_line(line, 2021)


if __name__ == "__main__":
    unittest.main()
