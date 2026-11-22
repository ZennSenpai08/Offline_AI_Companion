import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.core.config import ConfigError, Settings, SettingsStore


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SettingsStore(Path(self.temp.name))

    def test_missing_file_defaults_without_writing(self):
        self.assertEqual(self.store.load(), Settings())
        self.assertFalse(self.store.path.exists())

    def test_round_trip_negative_monitor_position_and_preferences(self):
        expected = Settings(x=-1400, y=120, screen_name="Second", work_area=[-1920, 0, 1920, 1040], scale=1.5, always_on_top=False, flipped=True,
                            animation_enabled=False, animation_fps=60, animation_intensity=.5, reduced_motion=True)
        self.store.save(expected)
        self.assertEqual(self.store.load(), expected)
        self.assertNotIn("click_through", json.loads(self.store.path.read_text()))

    def test_invalid_config_preserved(self):
        self.store.path.write_text('{"scale": NaN}', encoding="utf-8")
        original = self.store.path.read_bytes()
        with self.assertRaises(ConfigError): self.store.load()
        self.assertEqual(original, self.store.path.read_bytes())

    def test_invalid_types_ranges_and_future_schema(self):
        for data in ({"scale": True}, {"scale": 0}, {"scale": float("inf")}, {"scale": "large"}, {"x": 1}, {"x": False, "y": 1}, {"version": 2}, {"version": True}, {"always_on_top": 1}, {"flipped": "yes"}, {"work_area": [0, 0, 0, 1]}, {"screen_name": 1}, {"unexpected": 1}):
            with self.subTest(data=data), self.assertRaises(ConfigError): Settings.parse(data)

    def test_atomic_replace_failure_keeps_previous_file_and_removes_temp(self):
        self.store.save(Settings(scale=0.75))
        original = self.store.path.read_bytes()
        with patch("app.core.config.os.replace", side_effect=OSError("simulated disk error")):
            with self.assertRaises(OSError): self.store.save(Settings(scale=2))
        self.assertEqual(self.store.path.read_bytes(), original)
        self.assertEqual(list(self.store.directory.glob("*.tmp")), [])

    def test_oversized_file_rejected(self):
        self.store.path.write_text(" " * 65537)
        with self.assertRaises(ConfigError): self.store.load()


if __name__ == "__main__": unittest.main()
