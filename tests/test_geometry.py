import unittest

from app.core.geometry import Monitor, Rect, choose_monitor, clamp_position, fitted_size, remap_position


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.primary = Monitor("main", Rect(0, 0, 1920, 1040))
        self.left = Monitor("left", Rect(-1600, -200, 1600, 860))

    def test_negative_monitor_overlap(self):
        self.assertEqual(choose_monitor(Rect(-500, 100, 240, 360), [self.primary, self.left]), self.left)

    def test_gap_chooses_nearest_not_origin(self):
        far = Monitor("far", Rect(3000, 0, 1920, 1040))
        self.assertEqual(choose_monitor(Rect(2800, 0, 100, 200), [self.primary, far]), far)

    def test_removed_monitor_clamps_to_available_work_area(self):
        chosen = choose_monitor(Rect(-1500, -200, 240, 360), [self.primary], "left")
        self.assertEqual(chosen, self.primary)
        self.assertEqual(clamp_position(-1500, -200, (240, 360), chosen.area), (0, 0))

    def test_preferred_monitor_survives_origin_change(self):
        moved = Monitor("left", Rect(1920, 0, 1600, 860))
        self.assertEqual(choose_monitor(Rect(-500, 0, 240, 360), [self.primary, moved], "left"), moved)

    def test_remap_preserves_bottom_right_when_work_area_changes(self):
        self.assertEqual(remap_position(1680, 680, (240, 360), self.primary.area, Rect(-1280, 0, 1280, 720)), (-240, 360))

    def test_fit_preserves_aspect_and_is_bounded(self):
        for scale in (0.5, 0.75, 1, 1.25, 1.5, 2):
            for area in (Rect(0, 0, 1920, 1040), Rect(-200, -100, 130, 190)):
                with self.subTest(scale=scale, area=area):
                    width, height = fitted_size((240, 360), scale, area)
                    self.assertLessEqual(width, area.width)
                    self.assertLessEqual(height, area.height)
                    self.assertLessEqual(abs(width * 1.5 - height), 1)

    def test_clamps_all_edges(self):
        self.assertEqual(clamp_position(-9999, -9999, (240, 360), self.left.area), (-1600, -200))
        self.assertEqual(clamp_position(9999, 9999, (240, 360), self.left.area), (-240, 300))

    def test_no_monitors_is_explicit_failure(self):
        with self.assertRaises(ValueError): choose_monitor(Rect(0, 0, 240, 360), [])


if __name__ == "__main__": unittest.main()
