# Phase 2 — Desktop Overlay Foundation

Status: **accepted by the user; Phase 3 authorized**. After the single-instance fix, the user confirmed manual acceptance of transparency, dragging, always-on-top, click-through, tray controls, hotkey recovery, position persistence and resizing. The report below preserves the Phase 2 implementation/test history. Physical multi-monitor and mixed-DPI configurations remain unverified where unavailable; no additional hardware verification is inferred from acceptance. No AI models, speech recognition, LLM or TTS were added in Phase 2.

Validation date: 2026-11-21 local. The approved PySide6 Widgets / QPainter / replaceable original layered renderer architecture is preserved.

## Single-instance correction — latest validation

The user's reported error was reproduced: the agent's prior manual-review companion was still running as **PID 51080**, holding `C:\Users\Romcill\Desktop\Local_AI_Companion\offline-ai-companion\.runtime\manual\application.lock`. Qt returned **LockFailedError**; the ambiguous old message incorrectly mixed this with possible permission failures. No default-user-data lock existed. The verified companion was closed through its normal WM_CLOSE handler. Its lock disappeared and existing settings remained byte-for-byte unchanged.

Added `app/core/instance.py`: a scoped `QLockFile` owner with separate diagnostics for a live process, permission denial, read-only stale locks, filesystem errors and unverified ownership. Messages include the absolute lock path, with PID/host/application where available. `setStaleLockTime(0)` still prevents age-based eviction; Qt's dead-process recovery remains enabled. The application never force-removes a lock or kills a process. `app/main.py` now holds the context through logging setup and all shutdown/error paths, and logs the full lock path at startup.

Added **16 regressions** in `tests/test_instance.py`: separate-process simultaneous launches, live-owner preservation, genuine crash recovery, real Windows read-only stale-lock failure, clean release/relaunch, exception release, corrupt metadata, injected permission/I/O errors, startup failures, duplicate application dialogs, event-loop restart and tray-action shutdown. Real read-only tests modify only temporary test files; directory ACL permission failures are injected, not performed against user folders.

Latest command: `.\scripts\validate.ps1`. **44 tests passed in 15.291 seconds; zero failures, errors or skips.** Dependency consistency and compilation passed. Existing native tray-recovery, hotkey registration/message dispatch, window style and DPI tests passed. A three-second native smoke run using `.runtime/manual` returned **0**, reported **tray=True, recovery_hotkey=True**, and released its lock. This short smoke run is functional evidence, not a replacement for the earlier performance baseline.

Created: `app/core/instance.py`, `tests/test_instance.py`, `docs/single-instance.md`. Modified: `app/main.py`, README, this report, validation instructions and architecture/dependency/roadmap status summaries. No new dependency or architectural service was introduced. Full diagnosis, limitations and relaunch instructions: [single-instance ownership and recovery](single-instance.md).

No companion is intentionally left running after this fix. Resume manual acceptance with the existing data:

```powershell
cd C:\Users\Romcill\Desktop\Local_AI_Companion\offline-ai-companion
.\.venv\Scripts\python.exe -m app --data-dir .runtime\manual
```

That acceptance and authorization have now been provided by the user, as recorded at the top. The earlier measurements and 28-test baseline below remain historical evidence.

## Implementation delivered

- Transparent, frameless, shaped desktop window; drag from visible character regions, proportional 50–200% scaling and mirroring.
- Always-on-top, context/tray controls, click-through with tray recovery and Ctrl+Alt+Shift+R recovery. Click-through is refused without recovery and starts OFF after restart.
- Atomic validated settings, position/monitor persistence, display-change handling, DPI redraw, instance lock and orderly shutdown.
- Original temporary static layered character; image rendered and visually inspected. Future animation/Live2D can use the renderer boundary; no future gesture is claimed implemented.
- Opt-in performance probe and an external normal-idle measurement script. No periodic render or profiler timer runs during ordinary static idle.

## Files and structure

Created:

| Paths | Purpose |
| --- | --- |
| `app/__init__.py`, `app/__main__.py`, `app/main.py` | Entry point, lifecycle, settings orchestration and single-instance lock |
| `app/core/__init__.py`, `app/core/config.py`, `app/core/geometry.py` | Configuration and monitor geometry |
| `app/avatar/__init__.py`, `app/avatar/renderer.py`, `app/avatar/placeholder.py` | Replaceable renderer and original layer drawing |
| `app/desktop/__init__.py`, `app/desktop/overlay.py`, `app/desktop/tray.py`, `app/desktop/hotkey.py` | Desktop window and controls |
| `app/performance/__init__.py`, `app/performance/probe.py` | Opt-in measurements |
| `tests/test_config.py`, `tests/test_geometry.py`, `tests/test_desktop.py`, `tests/test_lifecycle.py` | Regression tests |
| `scripts/setup.ps1`, `scripts/validate.ps1` | Isolated setup and validation |
| `assets/characters/placeholder/README.md` | Original temporary asset provenance and capability limits |
| `requirements.txt`, `.gitignore` | Pinned Phase 2 dependencies and generated-file exclusions |
| `docs/phase-2-validation.md`, `docs/phase-2-report.md` | Manual/automatic verification instructions and this report |

Updated: `README.md`, `docs/architecture.md`, `docs/dependencies.md`, `docs/roadmap.md`, `docs/memory-budget.md`. Phase 1's completion report and research evidence remain historical records. AGENTS.md was not changed.

This validation continuation created `tests/test_windows.py` (native styles, recovery-message dispatch and current-monitor DPI region checks) and `scripts/measure_idle.py` (external measurement and owned-process shutdown). It modified `tests/test_desktop.py`, `app/performance/probe.py`, `scripts/validate.ps1`, this report, the validation guide, README and the four status documents listed above. The validation script now explicitly selects Windows or offscreen, preserving/restoring the caller's environment.

## Environment and dependency validation

Project interpreter: `.venv/Scripts/python.exe`, **CPython 3.10.11 x64**. Imported PySide6/Qt **6.10.2**, matching shiboken6 **6.10.2**, and psutil **7.2.2**. `pip check`: **No broken requirements found**. The user installed the pinned dependencies; the prior missing-Qt blocker is resolved. Python 3.12 remains the recommended baseline but is not installed/tested here; 3.10 is the documented compatibility fallback.

Windows reports build **26200** (Python's platform label is `Windows-10-10.0.26200-SP0`, not a claim this is Windows 10). The machine reports 12 logical CPUs, 15.309 GiB physical RAM and one display, `DISPLAY1`, at DPR **1.25**, logical work area **1536 × 816**.

## Actual tests and fixes

Commands run from the project directory:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\scripts\validate.ps1
.\scripts\validate.ps1 -Offscreen
```

The first dependency-enabled run discovered 25 tests: 23 passed and two drag tests failed. Investigation isolated both failures to the test harness:

1. `QPoint(0, 0)` is QtTest's default-position sentinel, so the empty-corner test pressed the character's center. It now checks and uses transparent `(1, 1)`.
2. Preconstructing all mouse events changed shared pointing-device state before dispatch. Constructing and dispatching each event sequentially produces the expected 60 × 35 logical-pixel drag. The production drag handler was unchanged.

Reference for QtTest's default center position: [official Qt documentation](https://doc.qt.io/qt-6/qtest.html#mousePress).

After these fixes, the original **25/25 passed**, including all **11 previously blocked Qt tests** (native run 0.692 seconds; offscreen run 0.359 seconds). Three Windows checks were then added. **Final native result: 28 tests passed in 0.943 seconds, zero failures/errors/skips.** Dependency checks and compilation of `app`, `tests` and `scripts` passed. The validation PowerShell script parsed with zero errors. The latest offscreen run passed its 25 applicable tests in 0.323 seconds, with the Windows-only class deliberately skipped; this is not a substitute for the native run.

Verified automatically:

- Config corruption/range/type/size handling, atomic-save failure recovery and preference round trips.
- Synthetic visible-region dragging and transparent-corner rejection; image alpha, silhouette masks, proportional scaling, mirroring and renderer DPR 1/1.25/1.5/2.
- Monitor geometry including negative origins, nearest/overlapping selection, removed-monitor fallback and work-area remapping (simulated geometry).
- Menu action dispatch, click-through guard/recovery, persistence, idempotent shutdown and controller recreation.
- Windows native layered/tool/topmost/transparent-input styles, including topmost removal/reapplication and tray recovery action.
- Native Windows silhouette region and physical window dimensions at the available monitor's 125% DPI, including exclusion of transparent corners and inclusion of the character's head.
- Successful global-hotkey registration and recovery through a posted WM_HOTKEY message to the test's own GUI thread. This does **not** prove physical keyboard delivery.

The real application launched on the `windows` platform, reported `tray=True, recovery_hotkey=True`, painted the character, wrote snapshots/reports and exited cleanly. The PNG inspection confirms intact proportions and no clipping; it is a renderer image, not a desktop screenshot.

## Performance and process accounting

The initial probe run uncovered two measurement defects, fixed in `app/performance/probe.py`:

- Enumerating descendants every 100 ms cost about **31.7 ms per call** on this machine and inflated instrumented CPU to **32.71% of one core**. Discovery now runs every five seconds while inexpensive memory/CPU sampling remains at 100 ms. CPU averages now weight elapsed sample duration.
- Windows' venv `python.exe` remains as a waiting launcher parent. The probe now includes that verified matching parent plus descendants. Earlier schema-1 reports omitted it and are **diagnostic evidence only, not accepted total-app measurements**.

A separate external harness samples the ordinary app once per second; sampler CPU/RAM is excluded. Both application processes are included. No inference workers, web servers or other companion-owned background services were observed.

Accepted instrumented run (`.runtime/phase-2-benchmark-2.json`, schema 2, 60.685 seconds):

| Metric | Actual result |
| --- | ---: |
| Median private commit, both processes | 28.629 MiB |
| Median resident working set, both processes | 59.945 MiB |
| Sampled peak private commit / working set | 28.742 / 60.160 MiB |
| GUI process OS lifetime peak commit / working set | 28.816 / 56.949 MiB |
| Idle CPU, one-core / whole 12-thread machine | 2.133% / 0.178% |
| Entry to first paint | 637.576 ms |
| GUI process creation to first paint | 736.945 ms |
| 16 ms event-loop timer lateness, p95 / maximum | 0.702 / 51.903 ms |
| Observed application processes / read failures | 2 / 0 |

The two lifetime peaks are for the GUI process only; they must not be confused with aggregate peaks. Private commit is not physical resident RAM. Startup was measured with warm filesystem caches; first paint is not human-confirmed desktop composition. Event-loop lateness is not pointer-to-pixel latency or animation FPS. Instrumented idle includes profiling overhead.

Normal startup without the in-app probe, measured externally for **300 seconds**:

| Metric (both owned processes) | Actual result |
| --- | ---: |
| Median private commit | **25.922 MiB** |
| Median resident working set | **55.926 MiB** |
| Sampled peak private commit | **26.191 MiB** |
| Sampled peak resident working set | **56.027 MiB** |
| Idle CPU, one-core / whole machine | **0.000% / 0.000% measured** |
| Early / final 30-second private-memory median | 26.191 / 25.922 MiB |
| Change between those windows | **−0.270 MiB** |
| Owned processes / survivors after close | **2 / 0** |
| Exit status | **0** |

The CPU counters recorded no additional application CPU time after the two-second warm-up; this is bounded by OS counter resolution and does not mean an absolute guarantee of zero CPU use. Private memory did not grow during this five-minute idle sample. The external harness posted WM_CLOSE to the owned overlay and verified that the GUI interpreter and venv launcher both terminated. No unnecessary application worker was found. This supplements the controller shutdown/restart test and repeated successful benchmark launches; user-driven tray exit is still a manual acceptance item.

Durable raw evidence: [instrumented run](measurements/phase-2-benchmark-2.json), [repeat instrumented run](measurements/phase-2-benchmark-3.json) and [five-minute normal idle](measurements/phase-2-normal-idle.json), including samples, process identities and limitations. These files were added during validation; the renderer PNG remains at `.runtime/placeholder.png`.

The second accepted instrumented run lasted **60.649 seconds** and exited 0: median private/working set **28.852 / 59.875 MiB**, sampled peaks **28.973 / 60.145 MiB**, one-core CPU **1.813%**, process-creation-to-first-paint **707.572 ms**, entry-to-first-paint **613.631 ms**, event-loop lateness p95/max **0.825 / 52.230 ms**, two observed processes and zero read failures. Thus the two accepted warm startup measurements span **0.708–0.737 seconds** from GUI process creation. The highest sampled resident total across accepted runs was **60.160 MiB**. This repeat also exercised clean exit/relaunch with the same saved settings directory.

Raw local evidence is under `.runtime/`. Sub-sample peaks/short-lived processes may be missed; GPU/DWM memory is not included. This static desktop subset is far below the **1.5 GiB** future total-application target, but no integrated-AI memory claim is made. A five-minute idle test cannot rule out long-duration or interaction-dependent leaks.

## Installation and launch

Existing environment is ready; no reinstall is needed. For a new environment:

```powershell
cd C:\Users\Romcill\Desktop\Local_AI_Companion\offline-ai-companion
.\scripts\setup.ps1 -Python 'C:\Users\Romcill\AppData\Local\Programs\Python\Python310\python.exe'
```

Launch:

```powershell
.\.venv\Scripts\python.exe -m app --data-dir .runtime\desktop
```

Right-click the character or tray for size, orientation, topmost, click-through, recovery and Exit. Recovery hotkey: **Ctrl+Alt+Shift+R**. Use the same data directory to restore preferences. See [README](../README.md) for normal user-data paths and [the validation guide](phase-2-validation.md) for repeatable measurement commands.

## Remaining manual verification and phase gate

Native computer interaction/capture is unavailable to this agent. Automated Qt/Win32 checks do not establish human GUI acceptance. The [manual matrix](phase-2-validation.md) contains precise actions and expected observations; the user-confirmed core results are now recorded in that guide; other rows remain unverified.

A normal interactive instance was originally left running with `--data-dir .runtime/manual` for review. That caused the duplicate-launch incident documented above; the instance has now been closed normally. Start it once for manual review, then exit through its tray before relaunching or running the native suite.

Outstanding: visual desktop transparency over light/dark applications; smooth physical dragging/capture; clicks through transparent pixels and click-through mode into another process; visible tray/overflow access; actual z-order against other applications; physical recovery hotkey; context/tray-driven exit/restart; monitor disconnect/reconnect and mixed-DPI movement; resolution/taskbar changes. Only one monitor at 125% is available, so other physical layouts cannot be validated here. Pure geometry/DPR tests do not remove this limitation. Longer soak and repeated real interactions also remain future validation work.

No observed automated-test or launch blocker remains. **Phase 2 is accepted by the user for the confirmed core desktop checks.** Unavailable monitor configurations remain documented limitations. Phase 3 was subsequently authorized explicitly.
