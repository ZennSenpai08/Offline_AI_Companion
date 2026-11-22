from dataclasses import astuple
import math
import unittest

from app.avatar.motion import IdleMotion, Pose, Spring
from app.core.config import ConfigError, Settings


class MotionTests(unittest.TestCase):
    def test_same_elapsed_time_at_30_and_60_fps(self):
        motions = []
        for fps in (30, 60):
            motion = IdleMotion(17)
            pose = motion.pose
            for _ in range(fps * 120):
                self.assertIs(motion.advance(1 / fps), pose)
            motions.append(motion)
        self.assertEqual(astuple(motions[0].pose), astuple(motions[1].pose))
        self.assertEqual(motions[0].blinks, motions[1].blinks)
        self.assertGreater(motions[0].weight_shifts, 0)

    def test_irregular_elapsed_steps_match_regular_time(self):
        regular, irregular = IdleMotion(9), IdleMotion(9)
        for _ in range(600): regular.advance(1 / 60)
        for _ in range(100):
            irregular.advance(.012)
            irregular.advance(.088)
        self.assertEqual(astuple(regular.pose), astuple(irregular.pose))

    def test_timing_variation_double_blinks_and_bounded_continuity(self):
        motion = IdleMotion(42)
        blink_times, periods = [], set()
        previous = astuple(motion.pose)
        previous_count = 0
        for _ in range(60 * 300):
            current = astuple(motion.advance(1 / 60))
            self.assertTrue(all(math.isfinite(v) for v in current))
            for value, before, limit in zip(current, previous, (.05, .05, .2, .3, .1, .5)):
                self.assertLess(abs(value - before), limit)
            self.assertTrue(0 <= motion.pose.eye_open <= 1)
            self.assertLessEqual(abs(motion.pose.head), 1.81)
            if motion.blinks != previous_count:
                blink_times.append(motion.time)
                previous_count = motion.blinks
            periods.add(round(motion.breath_period, 2))
            previous = current
        self.assertGreater(len(periods), 10)
        self.assertGreater(motion.double_blinks, 0)
        self.assertLess(motion.double_blinks, motion.blinks / 2)
        self.assertGreater(len({round(b - a, 1) for a, b in zip(blink_times, blink_times[1:])}), 10)

    def test_spring_has_secondary_motion_and_settles(self):
        spring = Spring(8, .55)
        spring.velocity = 5
        values = []
        for _ in range(1200):
            spring.step(0, 1 / 120)
            values.append(spring.value)
        self.assertGreater(max(values), 0)
        self.assertLess(min(values), 0)
        self.assertLess(abs(spring.value) + abs(spring.velocity), 1e-8)

    def test_reduced_motion_and_disable_transition(self):
        normal, reduced = IdleMotion(1), IdleMotion(1, reduced_motion=True)
        for _ in range(180):
            normal.advance(1 / 60); reduced.advance(1 / 60)
        for name in ('breath', 'sway', 'head', 'hair', 'weight'):
            self.assertAlmostEqual(getattr(reduced.pose, name), .15 * getattr(normal.pose, name))
        self.assertEqual(normal.pose.eye_open, reduced.pose.eye_open)
        before = normal.pose.head
        normal.configure(1, False, False)
        normal.advance(1 / 60)
        self.assertLess(abs(normal.pose.head - before), .2)
        for _ in range(180): normal.advance(1 / 60)
        self.assertTrue(normal.settled_off)
        self.assertEqual(normal.pose, Pose())

    def test_pause_gap_is_bounded_and_invalid_time_rejected(self):
        motion = IdleMotion(1)
        motion.advance(3600)
        self.assertAlmostEqual(motion.time, .25)
        for elapsed in (-1, float('nan'), float('inf')):
            with self.assertRaises(ValueError): motion.advance(elapsed)

    def test_settings_defaults_upgrade_old_files_and_validate_options(self):
        old = Settings.parse({'version': 1, 'scale': .75, 'x': 100, 'y': 150})
        self.assertEqual(old.animation_fps, 30)
        self.assertEqual(old.scale, .75)
        for values in ({'animation_fps': 25}, {'animation_fps': True}, {'animation_enabled': 1},
                       {'animation_intensity': float('nan')}, {'animation_intensity': 2}, {'reduced_motion': 'yes'}):
            with self.subTest(values=values), self.assertRaises(ConfigError): Settings.parse(values)


from PySide6.QtCore import QEvent, QPoint, QPointF, QSize, Qt
from PySide6.QtGui import QMouseEvent, QRegion, QBitmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app.avatar.placeholder import PlaceholderRenderer
from app.desktop.overlay import Overlay


class AnimatedDesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.renderer = PlaceholderRenderer()
        self.overlay = Overlay(Settings(), self.renderer)
        self.overlay.show(); self.app.processEvents()

    def tearDown(self):
        self.overlay.close(); self.overlay.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.renderer.close()

    def test_visible_animation_advances_hidden_and_closed_loops_stop(self):
        QTest.qWait(160)
        self.assertGreater(self.overlay.animation.updates, 1)
        self.overlay.hide()
        count = self.overlay.animation.updates
        QTest.qWait(80)
        self.assertEqual(self.overlay.animation.updates, count)
        self.overlay.show(); QTest.qWait(80)
        self.assertGreater(self.overlay.animation.updates, count)
        self.overlay.close()
        self.assertFalse(self.overlay.animation.timer.isActive())

    def test_live_preferences_smoothly_stop_then_resume(self):
        self.overlay.set_animation_preferences(enabled=False, fps=60, reduced_motion=True)
        QTest.qWait(1500)
        self.assertFalse(self.overlay.animation.timer.isActive())
        self.assertEqual(self.overlay.animation.motion.pose, Pose())
        self.overlay.set_animation_preferences(enabled=True, intensity=.5)
        QTest.qWait(80)
        self.assertTrue(self.overlay.animation.timer.isActive())

    def test_animation_menu_actions_update_live_settings(self):
        from PySide6.QtGui import QIcon, QPixmap
        from app.desktop.tray import DesktopControls
        controls = DesktopControls(self.overlay, QIcon(QPixmap.fromImage(self.overlay._image)))
        try:
            controls.reduced_action.trigger()
            controls.fps_actions[1].trigger()
            controls.intensity_actions[0].trigger()
            self.assertTrue(self.overlay.settings.reduced_motion)
            self.assertEqual(self.overlay.settings.animation_fps, 60)
            self.assertEqual(self.overlay.settings.animation_intensity, .5)
            self.assertAlmostEqual(self.overlay.animation.period, 1 / 60)
            controls.animation_action.trigger()
            self.assertFalse(self.overlay.settings.animation_enabled)
        finally:
            controls.close()

    def test_drag_resize_flip_while_motion_continues(self):
        self.overlay.move(100, 100)
        QTest.qWait(80)
        start = self.overlay.pos()
        local = QPointF(120, 140); origin = QPointF(self.overlay.mapToGlobal(local.toPoint()))
        for kind, offset, button, buttons in (
            (QEvent.Type.MouseButtonPress, QPointF(), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton),
            (QEvent.Type.MouseMove, QPointF(60, 35), Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton),
            (QEvent.Type.MouseButtonRelease, QPointF(60, 35), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)):
            event = QMouseEvent(kind, local, origin + offset, button, buttons, Qt.KeyboardModifier.NoModifier)
            self.app.sendEvent(self.overlay, event)
            QTest.qWait(35)
        self.assertEqual(self.overlay.pos(), start + QPoint(60, 35))
        count = self.overlay.animation.updates
        for scale in (.5, 2, 1.25, 1):
            self.overlay.set_character_scale(scale)
            self.overlay.set_flipped(not self.overlay.settings.flipped)
            QTest.qWait(40)
            self.assertLessEqual(abs(self.overlay.width() * 1.5 - self.overlay.height()), 1)
            self.assertFalse(self.overlay.hit_test(QPoint(1, 1)))
        self.assertGreater(self.overlay.animation.updates, count)

    def test_layer_alignment_foot_anchors_and_cache_reuse(self):
        pose = Pose(1.5, 1.2, 2.5, 2.5, 1, .5)
        self.renderer.render(QSize(240, 360), 1.25, pose=pose)
        cache_ids = [id(c[1]) for c in self.renderer._cache]
        transforms = dict(zip(self.renderer.info.layers, self.renderer._transforms))
        head = transforms['head']
        for part in ('eye_left', 'eye_right', 'mouth', 'brows', 'cheeks'):
            self.assertEqual(transforms[part], head)
        self.assertEqual(transforms['hair_front'], transforms['hair_pin'])
        for part in ('boot_left', 'boot_right'):
            self.assertTrue(transforms[part].isIdentity())
        self.renderer.render(QSize(240, 360), 1.25, pose=Pose(head=-2))
        self.assertEqual(cache_ids, [id(c[1]) for c in self.renderer._cache])

    def test_motion_stays_inside_envelope_and_image_at_extreme_poses(self):
        self.overlay.animation.stop()
        for scale in (.5, 1, 2):
            self.overlay.set_character_scale(scale)
            for sign in (-1, 1):
                pose = Pose(1.575, 1.275 * sign, 2.7 * sign, 3.75 * sign, 1.5 * sign, 0)
                image = self.renderer.render(self.overlay.size(), self.overlay.devicePixelRatioF(), pose=pose)
                logical = image.scaled(self.overlay.size()); logical.setDevicePixelRatio(1)
                region = QRegion(QBitmap.fromImage(logical.createAlphaMask(Qt.ImageConversionFlag.ThresholdDither)))
                self.assertTrue(region.subtracted(self.overlay.mask()).isEmpty())
                bounds = region.boundingRect()
                self.assertGreater(bounds.left(), 0); self.assertGreater(bounds.top(), 0)
                self.assertLess(bounds.right(), self.overlay.width() - 1)
                self.assertLess(bounds.bottom(), self.overlay.height() - 1)
