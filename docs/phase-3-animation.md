# Phase 3 animation design and validation

Phase 2 manual acceptance was explicitly confirmed by the user before implementation. Phase 3 keeps native PySide6 Widgets, the original layered character and a replaceable renderer. No AI/audio model, service, browser engine or new dependency was introduced.

## Motion and ownership

`app/avatar/motion.py` is a Qt-free deterministic simulation. It reuses one `Pose` containing breathing amount, body sway, head angle, hair angle, weight shift and eye openness. The animation controller is the only writer; renderers consume this pose without modifying it. Future expressions/gestures must be composed in this same ownership boundary with explicit priorities, rather than allowing independent timers to overwrite fields. No conversational gesture or expression classifier is implemented in Phase 3.

Elapsed monotonic time drives a 120 Hz integration step, independent of 30/60 FPS drawing. A delayed callback advances multiple bounded simulation steps; a resume gap is capped at 250 ms to avoid a catch-up spiral. Changing display FPS does not change animation speed. The scheduler uses absolute deadlines and a precise single-shot Qt timer, skipping missed draw deadlines. Qt timers are not real-time guarantees; see [Qt timer accuracy](https://doc.qt.io/qt-6/qtimer.html#accuracy-and-timer-resolution).

| Channel | Current behavior |
| --- | --- |
| Breathing | Smooth cosine cycle, randomized 3.6–5.2 s duration and amplitude per cycle; zero slope at the cycle boundary |
| Blinking | 90 ms close, 35 ms hold, 140 ms reopen; 2.4–6.5 s normal gaps; 16% probability of one additional blink after 150–240 ms; never an unbounded chain |
| Sway | Two low-amplitude oscillations with different frequencies, combined with occasional weight shifts |
| Head | Random targets within ±1.8 degrees, 3–7 s between targets, critically damped transition |
| Hair | Underdamped spring driven by head/sway velocity, different back/front amplitudes; bounded angle, accessory follows front hair |
| Weight | Gentle lateral/rotational upper-body shift, 9–18 s rest and 4–7 s hold, damped return; feet remain planted |
| State transition | Exponential blending of intensity/reduced-motion gains; disabling smoothly returns to neutral then stops the timer |

Numbers above are implementation parameters, not performance measurements. At maximum intensity (1.5), motion remains within the tested envelope. Reduced motion scales non-blink movement to 15%; blinks remain natural. Intensity zero or disabled animation settles to neutral and stops periodic updates. Hiding the window stops the timer; showing it resets elapsed-time accounting and resumes without simulating hidden wall time. Shutdown permanently closes the controller before releasing renderer resources.

## Asset inspection and rendering

The original asset has 19 separately defined layers. Before motion integration, its head/face/hair/accessory relationships and joint overlap were inspected. Neck, hip and hair pivots were aligned with the actual drawing. Legs/boots stay fixed; shoulders, scarf and head inherit breathing/upper-body motion. Eyelids were added as original curved paths, blended with vertically compressed eye layers. This placeholder uses rigid transforms, not deformable mesh or individual hair strands. See [asset provenance and segmentation](../assets/characters/placeholder/README.md).

The renderer contract now accepts a pose and exposes direct painting plus current-pose hit testing. An alternative renderer can map these channels to its own rig without depending on the motion clock or future inference backend.

Raster layers are cached at the current scale and device pixel ratio. Contiguous layers sharing a transform are composed into nine draw groups. Cache replacement on resizing releases previous groups; it is not an atlas that accumulates every scale. Paths, brushes/pens for rasterization, transforms and the pose are reused where practical. Ordinary frames do not allocate full-window QImages. Snapshot/APNG export explicitly allocates images outside the normal rendering path. Qt paint events and Python float calculations still create small temporary objects; this is not an allocation-free claim.

The shaped native window uses an 18-base-pixel motion envelope around the neutral silhouette, cached on scale/orientation/DPI changes. The envelope prevents clipping during motion; the widget checks current transformed alpha when starting a drag or opening its context menu. The envelope adds small transparent margins, not a full-screen rectangle. Windows cross-application alpha routing should be rechecked during live animation because Phase 2 manual acceptance predates this changed envelope. No per-frame native region construction is performed.

The Windows Qt backing store clears alpha in the dirty region before painting, so the application does not add a redundant full-window clear. This was checked against the pinned [Qt 6.10.2 Windows backing-store implementation](https://raw.githubusercontent.com/qt/qtbase/v6.10.2/src/plugins/platforms/windows/qwindowsbackingstore.cpp); live visual inspection is still needed to judge the complete compositor result.

## Configuration and controls

Right-click the character or tray → **Animation**:

- Enable animation.
- Reduced motion.
- 30 or 60 FPS.
- Motion intensity: Subtle (0.5), Normal (1.0), Expressive (1.5).

Saved JSON fields:

```json
{
  "animation_enabled": true,
  "animation_fps": 30,
  "animation_intensity": 1.0,
  "reduced_motion": false
}
```

These are additive validated fields in the existing version-1 settings schema. Old Phase 2 files load with the defaults above and retain geometry/preferences. The next successful save adds the animation fields. Older Phase 2 binaries reject unfamiliar keys, so do not assume backward downgrade compatibility. Invalid types, non-finite intensity and unsupported FPS are rejected without overwriting the source settings.

`--animation-fps 30` or `--animation-fps 60` sets and persists the frame rate for that data directory. Other controls can be changed live through the menu. Changes do not write settings every animation frame.

## Reproduce validation

Close other companion instances before native tests so their recovery hotkeys do not conflict.

```powershell
.\scripts\validate.ps1
.\.venv\Scripts\python.exe -m app --data-dir .runtime\phase3-30 --animation-fps 30 --benchmark-seconds 60 --report .runtime\phase3-30.json
.\.venv\Scripts\python.exe -m app --data-dir .runtime\phase3-60 --animation-fps 60 --benchmark-seconds 60 --report .runtime\phase3-60.json
.\.venv\Scripts\python.exe scripts/benchmark_animation_load.py --fps 30 --seconds 60 --workers 4 --data-dir .runtime\phase3-load --report .runtime\phase3-load.json
.\.venv\Scripts\python.exe scripts/measure_idle.py --seconds 300 --animation-fps 30 --data-dir .runtime\phase3-soak --report .runtime\phase3-soak.json
.\.venv\Scripts\python.exe scripts/check_animation_cache.py
.\.venv\Scripts\python.exe scripts/render_animation_preview.py --output docs\media\phase-3-animation.png
```

Run benchmarks sequentially. The load harness creates four owned CPU workers and joins them on exit; it tests CPU contention and process separation, not actual model inference. The external sampler measures ordinary animation and excludes its own CPU/RAM. The resize check records GUI-only allocation/handle changes and is not a whole-application memory benchmark. Full benchmark totals include the venv launcher and all observed application descendants. Paint FPS counts completed QWidget paint events, not DWM/monitor presentation.

The [18-second APNG](media/phase-3-animation.png) uses frames from the actual renderer/engine, plays once, and has no audio. A viewer without APNG support may show only its first frame. The companion itself is the interactive demonstration. Export framing follows the [W3C PNG specification](https://www.w3.org/TR/png-3/); all 540 frames were decoded and chunk CRC/sequence checks passed.

## Live visual checks

1. Watch for at least one minute at 30 FPS: varied breathing and blinks, occasional double blink, small head/weight changes and hair settling. Confirm motion looks natural rather than repetitive or exaggerated.
2. Switch to 60 FPS and compare; switch reduced motion on/off and change intensity. Disable animation: it should settle smoothly, remain interactive and resume correctly.
3. Drag the head/torso during blinking and head motion, move the pointer outside the window before releasing, and resize/mirror repeatedly. Parts must stay joined, feet stable and mouse capture reliable.
4. Recheck empty-pixel and click-through clicks into another application while moving. Recover through tray and hotkey.
5. Exit through the tray during animation. Restart the same data directory and verify animation settings and position; the old process and lock must be gone.
6. Where available, cross monitors with different DPI and disconnect a display. The rig should remain aligned and unclipped. These hardware configurations were unavailable in the development session.

Actual outcomes, limitations and measured performance belong in the [Phase 3 report](phase-3-report.md). Phase 4 requires separate authorization.
