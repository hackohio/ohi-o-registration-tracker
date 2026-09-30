import unittest
from unittest.mock import patch

from matplotlib.axes import Axes

from ohi_o_reg_tracker.charts import make_chart


class ChartTests(unittest.TestCase):
    def test_current_annotation_uses_export_timeline_endpoint(self):
        labels = []
        original_annotate = Axes.annotate

        def record_annotation(axis, text, *args, **kwargs):
            labels.append(text)
            return original_annotate(axis, text, *args, **kwargs)

        with patch.object(Axes, "annotate", record_annotation):
            png = make_chart(
                {1: 80, 0: 92},
                None,
                {1: (70, 5), 0: (75, 6)},
                today_days_before=0,
            )

        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertIn("current: 92", labels)


if __name__ == "__main__":
    unittest.main()
