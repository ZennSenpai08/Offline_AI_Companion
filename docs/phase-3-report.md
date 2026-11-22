# Phase 3 — Natural Character Animation

**Status: Phase 3 implementation, automated validation and benchmark deliverables accepted by the user; live visual review remains recommended.** Phase 2 core manual acceptance and Phase 3 authorization were explicitly provided before implementation. The user subsequently authorized Phase 4; see its [separate report](phase-4-report.md). No AI/STT/TTS models, audio capture or inference functionality were installed or implemented **during Phase 3**. The remainder preserves that phase's historical results.

## Delivered behavior

- Time-based breathing with varying cycles; irregular blinks and occasional double blinks.
- Gentle sway, damped head targets, spring-driven hair and occasional weight shifts with planted feet.
- Smooth changes to enabled state, intensity and reduced motion; independent 30/60 FPS rendering.
- One pose compositor owns all channels, with a replaceable renderer boundary for future gesture/expression/Live2D integration. No future gestures or lip sync are claimed implemented.
- Current-DPI layer caches, nine composite draw groups, retained transforms and no full-frame image allocation during ordinary painting.
- Animated dragging, proportional resize/mirroring, bounded native mask, tray controls, hotkey recovery, settings persistence and timer shutdown.
- An [18-second APNG demonstration](media/phase-3-animation.png), generated from the actual engine. It is a development artifact and is not loaded by the desktop application.

The original asset's 19 layers and joint overlap were inspected before implementing transforms. Rendered samples including a closed-eye pose were visually inspected for alignment/clipping. Details, parameter ranges, ownership, configuration and live validation steps are in [the animation design](phase-3-animation.md).

## Files created and modified

Created:

- `app/avatar/motion.py` — reusable pose, damped springs and deterministic idle compositor.
- `app/avatar/animation_controller.py` — bounded monotonic scheduling, visibility and shutdown handling.
- `tests/test_animation.py` — timing, continuity, layer alignment, live controls and interaction regressions.
- `scripts/benchmark_animation_load.py`, `scripts/check_animation_cache.py`, `scripts/render_animation_preview.py`.
- `docs/phase-3-animation.md`, `docs/phase-3-report.md`, `docs/media/phase-3-animation.png` and Phase 3 JSON evidence under `docs/measurements/`.

Modified: `app/__init__.py`, `app/main.py`, `app/core/config.py`, `app/avatar/renderer.py`, `app/avatar/placeholder.py`, `app/desktop/overlay.py`, `app/desktop/tray.py`, `app/performance/probe.py`, `scripts/measure_idle.py`, `scripts/validate.ps1`, `tests/test_config.py`, asset provenance, README, architecture/dependency/roadmap/memory documentation and the Phase 2 acceptance record. `AGENTS.md`, pinned dependencies and the single-instance protection remain unchanged by this phase.

## Tests and demonstrated limits

Final command: `.\scripts\validate.ps1`. **57 tests passed in 18.552 seconds**, with **zero failures, errors or skips**. This includes the animation-menu regression and non-default animation-settings round trip. `pip check` reported no broken requirements; compilation of `app`, `tests` and `scripts` passed. The preceding integrated 56-test run also passed. No GUI result is inferred solely from a dependency import or skipped test.

Coverage includes:

- Identical seeded simulation results after 120 seconds at 30 and 60 FPS; irregular elapsed intervals produce the same state as regular intervals.
- Five minutes of simulated timing: varied breathing/blink intervals, occasional doubles, finite/bounded output and continuous changes; stable spring settling.
- Resume-gap cap, invalid elapsed values, reduced motion, smooth disable/neutral state, enable/resume and hidden/closed timer stopping.
- Current head/eye/mouth alignment, hair-pin parenting, planted feet, reused raster objects, extreme motion within the native envelope and image bounds.
- Synthetic dragging, resizing and flipping while the animation timer advances; menu controls and configuration validation/persistence.
- All earlier desktop, geometry, config, native style/DPI, tray/hotkey, single-instance race/crash/permission and lifecycle regressions.
- APNG chunk CRCs, animation sequence ordering and decoding of **all 540 frames** passed.

Qt/native tests and rendered stills do not constitute human observation of every animated Windows interaction. Phase 2's confirmed desktop checks predate the new motion envelope. Live animation smoothness, moving-transparent-pixel routing and physical drag/capture should be reviewed using the guide. Mixed-DPI/monitor hot-plug hardware remains unavailable. No actual AI inference was run; CPU-worker testing demonstrates separation under representative CPU contention only.

## Actual 30/60 FPS measurements

Environment: Windows build 26200, Python **3.10.11 x64**, Qt **6.10.2**, psutil **7.2.2**, 12 logical CPUs and 15.309 GiB system RAM. One display at **125% DPI**, logical work area 1536 × 816. Default character size/intensity, normal motion, no microphone/models. Each accepted instrumented run lasted approximately 60 seconds, excluding the first two seconds from idle metrics. Both the GUI interpreter and Windows venv launcher are counted.

| Metric | 30 FPS requested | 60 FPS requested |
| --- | ---: | ---: |
| Measured QWidget paint FPS | **29.984** | **59.796** |
| Frame interval p95 | 34.912 ms | 18.229 ms |
| Longest sampled paint interval | 81.646 ms | 65.242 ms |
| Paint duration p95 | 3.862 ms | 3.779 ms |
| CPU, percent of one logical core | **18.371%** | **35.617%** |
| CPU, percent of whole 12-thread machine | **1.531%** | **2.968%** |
| Median private commit | **31.301 MiB** | **31.410 MiB** |
| Median resident working set | **61.137 MiB** | **61.297 MiB** |
| Sampled peak private commit | 31.813 MiB | 31.938 MiB |
| Sampled peak resident working set | 61.453 MiB | 61.742 MiB |

**Selected default: 30 FPS**, the lower of the two tested configurations. It maintains essentially 30 paint events per second with the same motion timing and roughly half the measured CPU of 60 FPS. 60 FPS remains available. This is a measured engineering choice; subjective naturalness is still open to user review. No claim is made that 30 is the lowest possible usable FPS below the tested range.

Evidence: [30 FPS](measurements/phase3-final-30.json), [60 FPS](measurements/phase3-final-60.json). Instrumentation adds sampling, frame timestamps, a heartbeat and five-second process discovery. Discovery itself can delay a UI callback on this machine; worst intervals include that overhead and ordinary workstation activity. Paint FPS measures completed QWidget paints, not physical monitor/DWM presentation. Private commit is distinct from resident RAM; shared resident pages can be counted twice. Sub-sample transient peaks, very short-lived descendants and compositor/GPU memory are not fully captured.

## CPU-load responsiveness

Four owned synthetic CPU workers ran alongside the real overlay for 60 seconds. **29.932 paint FPS**, **34.827 ms frame interval p95**, and **75.973 ms maximum interval** were measured at a 30 FPS target. Combined application-plus-worker CPU was **411.338% of one core / 34.278% of the machine**. Median private/resident totals were **65.574 / 118.117 MiB** across six observed processes; sampled peaks were **66.012 / 118.473 MiB**. All four workers exited with code **0**.

This test models CPU contention using separate processes; it does not demonstrate specific LLM/STT/TTS latency or concurrent GPU load. The renderer and animation update loop contain no inference calls or waits. [Raw load report](measurements/phase3-load.json).

## Memory stability investigation

The initial 312 resize/flip pairs showed a small private-memory increase, so the check was extended to **984 pairs** with Python allocation tracing. Each checkpoint returned to 100% scale/orientation before sampling. Cached objects stayed at **19 layers / 9 groups**, individual layer-image storage stayed **717,352 bytes**, and GUI handle count stayed **347–348**. Traced Python allocations moved from **0.609 to 0.685 MiB**, with much smaller changes at the end.

GUI private memory increased from **29.543 to 34.750 MiB**, fluctuating rather than rising monotonically (for example, 33.945 → 32.012 → 34.750 MiB in later checkpoints). This is consistent with retained native allocator/cache capacity, but that cause is an inference, not a proof. No growing layer cache or handle leak was observed. The report does **not** claim perfectly flat interaction memory or rule out slower native leaks. The stress check counts only the GUI process and includes tracing overhead; use the full-process benchmark totals for the application budget. [Raw interaction evidence](measurements/phase3-interactions.json).

Normal animation at 30 FPS, measured externally for **300 seconds**, excludes the sampler process and runs without the in-app performance probe:

| Metric, GUI plus Windows venv launcher | Actual result |
| --- | ---: |
| Median private commit | **27.777 MiB** |
| Median resident RAM | **57.805 MiB** |
| Sampled peak private / resident | **28.043 / 57.926 MiB** |
| CPU, one-core / whole 12-thread machine | **16.580% / 1.382%** |
| First / last 30-second private-memory medians | **28.027 / 27.777 MiB** |
| Private-memory change | **−0.250 MiB** |
| Observed owned processes / survivors after close | **2 / 0** |
| Exit code | **0** |

No private-memory growth was observed during this five-minute normal-animation sample. This is separate from retained memory after repeated resizing. The sampler closed only its owned overlay through WM_CLOSE and verified both processes ended. [Raw normal-animation evidence](measurements/phase3-soak.json).

The measured desktop subset remains far below the future **1.5 GiB total-application RAM** target. Future models/workers have not been integrated, so that full-system target remains unproven. Longer-duration soak testing belongs to continuing QA; no short test proves the absence of all leaks.

## Launch and controls

No new dependency installation is needed for the existing environment. For a clean environment use the setup instructions in [README](../README.md).

```powershell
cd C:\Users\Romcill\Desktop\Local_AI_Companion\offline-ai-companion
.\.venv\Scripts\python.exe -m app --data-dir .runtime\manual --animation-fps 30
```

Launch once; exit the existing tray before a fresh launch. Right-click → **Animation** for enable/disable, reduced motion, FPS and intensity. Existing Phase 2 geometry/preferences are retained; animation defaults are added on save. Ctrl+Alt+Shift+R remains the recovery hotkey when registered.

All benchmark instances were closed after validation; no review instance is intentionally left running. The user was invited to observe the five-minute animation run, but no Phase 3 visual acceptance is inferred without their response. The preview and launch command support that remaining review.

After reporting Phase 3, stop and request authorization before Phase 4. Phase 4 will address microphone consent/device management, local VAD and offline speech recognition; none of that work is included here.
