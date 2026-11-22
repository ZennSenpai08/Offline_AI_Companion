# Phase 2 validation and measurement guide

Current status: all 44 tests passed on the native Windows Qt backend; the original 25 also passed offscreen (the native test class is intentionally skipped there). The dependency blocker is resolved and application performance has been measured; see [actual results](phase-2-report.md). The user subsequently confirmed transparency, dragging, always-on-top, click-through, tray controls, hotkey recovery, position persistence and resizing, and authorized Phase 3. Other rows are not implied to have passed. Close other companion instances before native tests so the recovery hotkey is available.

## Environment and automated checks

From the project directory, install dependencies with `scripts/setup.ps1` as described in the README. Use the `.venv` interpreter for all commands. Keep test state in `.runtime` so it does not overwrite normal preferences.

```powershell
.\.venv\Scripts\python.exe -m pip check
.\scripts\validate.ps1 -Offscreen
.\scripts\validate.ps1
```

The validation script requires real Qt imports before running tests. Missing Qt must not be considered a passing skipped suite. Offscreen results check the render image, masks, flags, synthetic drag events, scale/orientation, persistence, menu actions and lifecycle. Native runs additionally exercise Windows plugin creation, but neither automatically proves cross-process mouse routing or that the tray is visually accessible.

## Manual Windows acceptance matrix

Start a normal run:

```powershell
.\.venv\Scripts\python.exe -m app --data-dir .runtime\manual
```

Record Windows build, monitor layout/resolution/work areas, each monitor's scaling, Qt/Python versions, and results below. Mark PASS only after observing the specified behavior. The core desktop checks named above are user-confirmed. Other configurations and edge cases remain unverified unless separately recorded.

| Test | Exact action | Required observation |
| --- | --- | --- |
| Transparent/frameless | Place the character over a light window, then a dark window | Only character pixels appear; no opaque rectangular background, caption or border |
| Empty-pixel clicks | Position an underlying Notepad window so its text area extends beneath an empty upper corner and between the character's feet; click those empty regions | Notepad receives focus/caret; companion does not drag. Compare with clicking opaque torso pixels |
| Visible-region drag | Drag head, torso and arm across the desktop; release near each work-area edge | Character follows pointer smoothly, releases reliably, remains inside one monitor work area after release |
| Drag capture | Press on the torso, move beyond the window before releasing | Drag continues and stops on release; no stuck closed-hand cursor |
| Always-on-top | Enable topmost, activate/move ordinary Notepad over character; then disable topmost and repeat | Enabled floats above ordinary apps; disabled follows normal z-order. Secure desktop/exclusive fullscreen is outside the guarantee |
| Context menu | Right-click head and choose each size, orientation and topmost action | Menu opens at pointer; items reflect state; selected action changes real window behavior |
| Proportional resizing | Select 50, 75, 100, 125, 150 and 200% | Character proportions remain constant, corners remain transparent, silhouette interaction matches size |
| Tray | Find icon (including overflow area), right-click, resize, toggle topmost, left/double click | Menu works independently of the character; left/double click restores character to primary work area |
| Click-through | Enable click-through while over Notepad; click on the character's opaque torso | Underlying Notepad receives input; companion does not move or open its menu |
| Tray recovery | While click-through is enabled, select tray **Recover character / Disable click-through** | Character becomes draggable and returns to the primary monitor |
| Hotkey recovery | Check log says `recovery_hotkey=True`; enable click-through and press Ctrl+Alt+Shift+R | Character becomes interactive. If registration failed, record that limitation and verify tray recovery instead |
| Preference persistence | Move to a non-default location; set 125%, flipped and topmost OFF; exit through tray; restart same command | Position/size/direction/topmost restored; click-through is OFF |
| Multi-monitor | Move to each monitor, including one left/above primary; restart | Saved monitor is used; negative coordinates work; proportions remain intact |
| Monitor removal | Place character on secondary, disconnect/disable that display, then reconnect | Character moves into a remaining work area without being lost; no crash or hot loop |
| DPI transition | Use monitors at 100/125/150/200% where available; drag between them | Crisp redraw at new pixel ratio, no double scaling, input region tracks character. Record unavailable configurations as untested |
| Resolution/taskbar | While running, change resolution/work area; expand/move taskbar where Windows permits | Character fits the new available area; requested size remains a preference even if temporarily fitted smaller |
| Exit/restart | Exit via tray and context menu, then repeat ten launches | Tray icon disappears, process terminates, saved settings remain valid, no orphan application process |
| Duplicate launch | Start a second instance with the same data directory | Dialog identifies the existing owner PID and exact lock path without suggesting a permission failure; after acknowledgement the second launch exits and the original still works |
| Abnormal termination | With test data only, end the companion process in Task Manager; relaunch | Dead-process lock recovers; last saved JSON remains readable; click-through starts OFF |
| Invalid config | Exit; back up test settings; edit `scale` to `"invalid"`; relaunch | Actionable startup error; corrupt file preserved. Rename it and restart to recover defaults |
| No internet | After installation, disconnect internet; launch, drag, resize, recover and exit | All Phase 2 behavior still works; no download prompt/network service |

Click-through means input passes to **other applications**. A successful `hit_test()` unit test or a transparent screenshot alone is insufficient evidence. Windows `HTTRANSPARENT` alone also has cross-thread limitations; this implementation uses a Qt-shaped window and `WindowTransparentForInput`, whose actual behavior must pass the above test.

## Repeatable performance run

Close other companion instances. Keep the character visible at 100%, with no context menu open. Run three separate sessions; record the first as the first launch of this series rather than pretending the OS file cache was cold:

```powershell
1..3 | ForEach-Object {
    .\.venv\Scripts\python.exe -m app --data-dir .runtime\bench --benchmark-seconds 60 --report ".runtime\bench-$_.json"
    if ($LASTEXITCODE -ne 0) { throw 'Benchmark application failed.' }
}
```

For a longer idle sample use 600 seconds. Do not interact during an idle run. For an interaction run use a separately named report and perform the same resize/drag/topmost sequence; record the actions and duration. Do not mix interaction spikes into an idle baseline without labeling them.

Each report includes:

- Median idle private commit and working set after the first two seconds; sampled aggregate peaks in MiB. Private commit is not physical RAM.
- Main-process OS lifetime peak working set/commit; never confuse a sum of independent process peaks with simultaneous aggregate peak.
- The matching Windows venv launcher parent and observed descendant identities; no hidden inference workers exist in this phase. The invoking shell/test harness is excluded and no models are loaded.
- Mean CPU expressed both as percent of one logical CPU and percent of the entire machine.
- Entry-to-first-paint and OS process-creation-to-first-paint times. Neither means the user has visually confirmed compositing.
- 16 ms timer lateness p95/max, which measures event-loop scheduling responsiveness, not animation FPS or pointer-to-pixel latency.
- Raw 100 ms samples, 5-second process-tree discovery, environment metadata, monitor DPI/work areas and caveats. Descendants shorter than the discovery interval can be missed.

Instrumentation adds timers and psutil work; ordinary startup does not run these probes. The original 100 ms process-tree scan substantially distorted idle CPU and was replaced with 5-second discovery. CPU averages are weighted by elapsed sample time. GPU/DWM memory and sub-sample transient peaks are not fully accounted for. Later AI profiling must add explicit worker ownership and Job Object accounting before claiming a full-application memory target.

Measure normal idle separately, with sampling in an external harness:

```powershell
.\.venv\Scripts\python.exe scripts/measure_idle.py --seconds 300 --data-dir .runtime\normal-idle --report .runtime\phase-2-normal-idle.json
```

This starts the ordinary application, includes its launcher/descendants, samples once per second, and closes only its owned overlay using WM_CLOSE. It reports early/late private-memory medians and verifies owned process termination. The harness's CPU/RAM is excluded. Do not interact during this run; a short stable observation does not prove there are no long-duration or interaction-dependent leaks.

For a transparent image artifact:

```powershell
.\.venv\Scripts\python.exe -m app --data-dir .runtime\preview --benchmark-seconds 5 --report .runtime\preview.json --snapshot .runtime\placeholder.png
```

This PNG contains only the avatar render, not the user's desktop. The current preview was rendered and visually inspected for clipping/proportions; actual desktop composition still requires the manual matrix above.

## Troubleshooting

- **PySide6 missing:** use `.venv\Scripts\python.exe`, not the system `python`; run setup or install matching wheels offline.
- **Python launcher fails:** the inspected Store Python 3.13 registration could not launch here. Pass the path to a working x64 interpreter. The existing Python 3.10.11 can run the Phase 2 subset; Python 3.12 remains recommended.
- **WinError 10013 during installation:** this environment blocks shell network access. Run setup from your own permitted PowerShell or supply trusted local wheels. Do not disable security controls or change firewall policy.
- **Qt platform DLL fails:** use matching PySide6/shiboken versions and x64 Python; capture the actual error and `pip check` output. Do not download individual DLLs from unofficial websites.
- **Tray hidden:** check Windows overflow. If the hotkey is unavailable too, restart into the default interactive mode; click-through is not persisted.
- **Character lost:** exit the existing process through its tray, then start with `--reset-position` and the same `--data-dir`.
- **Settings cannot save:** inspect `companion.log` in the data directory and folder permissions. Saves use a temporary file plus atomic replace; prior settings remain intact on a failed replace.
- **Instance lock error:** see [specific diagnoses and recovery](single-instance.md). An already-running companion must exit through its own tray before a fresh launch; never delete a live lock or terminate Python processes by name. The prior agent-held review instance has been closed normally.

Phase 3 approval should follow a successful Qt run and Phase 2 report update, not replace missing Phase 2 evidence.
