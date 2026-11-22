# Phase 4 — Offline microphone and multilingual speech recognition

Validation date: **2026-11-22**, Windows 11 build 26200, Python **3.10.11 x64**, Qt **6.10.2**, psutil **7.2.2**, 12 logical CPUs, one 125% DPI display.

**Latest status: native dependencies/model and automated inference validation PASS; physical microphone and speech-quality acceptance remain INCOMPLETE.** The user's local installation resolved the earlier package/model blocker. Capture cannot open under the agent's `codexsandboxoffline` Windows account, so no human speech or physical mute/release result is claimed. Phase 5 has not begun. The current user-requested Phase 4 RAM ceiling is **1.8 GiB**, superseding the older 1.5 GiB ceiling for this validation.

## Latest native validation — 2026-11-22

`.\scripts\validate.ps1 -Audio` completed with **86 tests passing in 25.842 seconds**, zero failures/errors/skips. `pip check`, native diagnostics and compilation passed. Log: `.runtime/phase4-native-validation-final.txt`. The three added native checks use the actual WebRTC library on synthetic silence/low noise/one short impulse, actual SoXR 44.1/48 kHz streaming conversion into exact VAD frames, and the actual quantized Tiny model in an owned worker. An additional regression checks that an unfinished/cancelled second turn cannot reuse the previous turn's latency. These tests do **not** prove real microphone or speech accuracy.

All direct audio pins are installed: **sounddevice 0.5.3**, **webrtcvad-wheels 2.0.14**, **NumPy 2.2.6**, **SoXR 0.5.0.post1**, **pywhispercpp 1.5.0**. Full installed package inventory: [package versions](measurements/phase4-installed-packages.txt). Native checks and detected devices: [environment JSON](measurements/phase4-audio-environment.json).

The approved implementation uses `pywhispercpp`'s native `_pywhispercpp.cp310-win_amd64.pyd` and bundled CPU backend, **not a standalone whisper-cli executable**. That binary imported and executed successfully. Local binding SHA-256: `d7212991cd6fdbdf59ac80f6c87f784ba8ef7d6bde2795ffb9128e20294220c6`. PortAudio reports V19.7.0-devel, revision unknown. The exact bundled whisper.cpp Git revision is not exposed by the inspected binding; the pinned wheel/version, local binary hash and CPU feature string identify the tested build without inventing a commit.

Installed model: `models/ggml-tiny-q5_1.bin`, multilingual **Tiny Q5_1**, **32,152,673 bytes / 30.663 MiB**. The size, multilingual GGML header and SHA-256 match its provenance manifest:

```text
SHA-256: 818710568da3ca15689e31a743197b520007872ff9576237bda97bd1b469c3d7
Repository revision: 5359861c739e955e79d9a303bcbc70fb988958b1
Source: ggerganov/whisper.cpp, MIT
```

### Input detection and capture failure

Nine input entries are enumerated. These include repeated host-API views of the AMD microphone array, mapper/default entries, a Realtek microphone entry, Stereo Mix and PC Speaker. **They are not nine physical microphones.** The default is MME `Microphone Array (AMD Audio Dev`, with a reported default native rate of 44.1 kHz. Named WASAPI and DirectSound views identify `Microphone Array (AMD Audio Device)`.

Real capture attempts failed before any stream delivered PCM:

| Interface | Actual error |
| --- | --- |
| Default MME | PortAudio **−9999**, “Undefined external error”, MME error 1 |
| Named WASAPI AMD array | PortAudio **−9996**, “Invalid device” |
| Named DirectSound AMD array | PortAudio **−9999**, DirectSound **−2147467259** |

The failure reproduces with raw sounddevice streams outside the companion adapter, including 44.1 kHz stereo MME and 48 kHz stereo WASAPI. Windows `Audiosrv` and `AudioEndpointBuilder` are Running. HKLM microphone consent is Allow; the agent account has no inspected HKCU microphone consent entry. Both the process and active console are session 12, but `whoami` identifies **codexsandboxoffline**, not the desktop user's account. Account/sandbox access is a plausible explanation, **not a proven root cause**. No registry permissions, drivers or security settings were changed.

The companion was launched through the physical-validation harness with real microphone enablement and displayed Device Unavailable. The harness exited cleanly after failure. It records **zero streams opened** and **null** for native-stream closure verification; an empty set is not reported as a successful physical mute test. [Exact errors](measurements/phase4-capture-diagnostic.json), [physical test attempt](measurements/phase4-physical-toggle.json).

### Actual inference and resource results

Five runs sent a six-second **synthetic silence WAV** through the actual Tiny worker while the actual Qt overlay animated. This is a native engine/resource benchmark, **not recorded human speech or a recognition-quality test**. A separate three-second silence smoke run returned `[BLANK_AUDIO]` in 2.685 seconds; that is a non-speech marker, not a successful English/Tagalog transcript.

Command:

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_speech.py .runtime\phase4-fixtures\synthetic-silence-6s.wav --source-kind synthetic-fixture --repeats 5 --report docs\measurements\phase4-native-inference-final.json
```

| Metric, all owned application processes | Final measured result |
| --- | ---: |
| Pre-inference baseline, median resident / private (short 3-second window) | **73.496 / 38.176 MiB** |
| During inference, aggregate median resident / private | **216.703 / 670.652 MiB** |
| During inference, sampled peak resident / private | **225.414 / 677.398 MiB** |
| End-to-end worker request latency, median / range | **2.797 s / 2.704–3.366 s** |
| Native inference time, range | **1.524–1.910 s** |
| Model initialization time, range | **0.106–0.148 s** |
| Inference CPU, one-core / whole 12-thread machine | **270.567% / 22.547%** |
| Paint FPS during each inference | **29.976–30.029** |
| Inference frame interval p95 | **34.939–36.021 ms** |
| Final recovery median resident / private | **73.232 / 37.926 MiB** |
| Maximum concurrent owned processes | **3** |
| Inference errors / surviving benchmark PID-and-creation identities | **0 / 0** |

The three processes are the GUI, matching Windows venv launcher and one native inference worker. The measured subset is below **1.8 GiB**, including private commit, but real speech, physical listening and future LLM/TTS totals remain unproven. Request latency includes worker startup, model verification, imports, loading and decoding; it is not speech-end-to-preview latency. Memory returned near baseline in all five recovery windows; this demonstrates model release, not absence of every long-duration leak. One sample raced worker exit and could not read that process. Sampling cannot capture every transient peak or final CPU quantum. [Final raw measurements](measurements/phase4-native-inference-final.json).

A separate **60-second normal desktop run with microphone OFF**, measured externally with sampler cost excluded, recorded **68.707 MiB median resident / 33.898 MiB private**, **68.738 / 33.969 MiB sampled peaks**, and **17.093% one-core / 1.424% whole-machine CPU**. Private-memory medians for the first/last 30-second windows were **33.969 / 33.898 MiB**. Both owned processes exited (code 0); zero survivors. This is the current idle baseline, distinct from the short instrumented pre-inference window and **not mic-enabled listening**. [Normal idle evidence](measurements/phase4-native-idle.json).

Investigation/fixes: CREATE_NO_WINDOW spawned a headless `conhost.exe` on this Windows build; DETACHED_PROCESS with explicit private standard handles removed that unnecessary helper while retaining Job ownership. A focused native process experiment and the final three-process measurement confirm this. Global psutil descendant scans were causing benchmark-induced frame gaps even off the GUI thread. The sampler now reads the native PID lists of all active application-owned Job Objects every 100 ms, plus GUI/launcher, avoiding those scans. The earlier scan-based benchmark is retained as [development evidence](measurements/phase4-native-inference-silence.json), not the accepted final timing result. Win32 semantics: [creation flags](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags), [Job PID lists](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_process_id_list).

### Recognition quality and remaining manual acceptance

**English, Tagalog and Taglish accuracy, real transcription examples, WER/CER, physical VAD endpoints and mic-enabled idle RAM remain NOT VERIFIED.** No human recordings/manifest were available in the project when checked. No test transcript was fed to the recognizer, and no synthetic fixture was labeled as human speech. Tiny has not been demonstrated to struggle or succeed on these languages, so there is no evidence yet to justify switching to Base. Compare automatic language versus a Tagalog hint on the same real corpus first; then evaluate Base Q5_1 only if measured errors justify its extra resources.

Run these from **your ordinary desktop PowerShell**, not the agent account:

```powershell
cd C:\Users\Romcill\Desktop\Local_AI_Companion\offline-ai-companion
.\.venv\Scripts\python.exe scripts/validate_microphone.py --consent-to-microphone --cycles 6 --report docs\measurements\phase4-user-physical-toggle.json
.\.venv\Scripts\python.exe scripts/record_speech_samples.py --consent-and-retain-audio --output .runtime\speech-samples
.\.venv\Scripts\python.exe scripts/evaluate_speech.py .runtime\speech-samples\manifest.json --output docs\measurements\phase4-tiny-accuracy.json
.\.venv\Scripts\python.exe scripts/benchmark_microphone.py --consent-to-microphone --seconds 60 --report docs\measurements\phase4-listening.json
.\.venv\Scripts\python.exe scripts/benchmark_microphone.py --consent-to-microphone --seconds 120 --report docs\measurements\phase4-live-speech.json
.\.venv\Scripts\python.exe scripts/benchmark_speech.py .runtime\speech-samples\01-tagalog.wav --source-kind human-recording --repeats 3 --report docs\measurements\phase4-real-speech.json
```

For the listening run remain quiet; for the speech run say the prompted phrases and wait for Listening before each next utterance. The recorder requires an empty output folder and explicitly retains local WAVs for scoring; normal app/benchmarks retain no raw audio. If capture also fails in your PowerShell, check **Windows Settings → Privacy & security → Microphone**, both device access and desktop-app access; select the AMD input in the app's Microphone settings and test it with Windows Sound Recorder. If needed, repeat the toggle harness with `--device 'Windows WASAPI | Microphone Array (AMD Audio Device)'` and retain its exact error. Do not infer success from device enumeration alone.

The physical toggle harness alternates actual tray and panel controls, checks native PortAudio `closed`, empty buffers and no callbacks for 300 ms after confirmed mute, then verifies reopening on the next cycle. Also manually confirm the Windows capture indicator, device unplug/replug, quiet/noisy speech endpoints, preview/drag/resize while transcribing, and shutdown during speech. Instructions and eight phrases: [audio acceptance guide](phase-4-audio.md). Launch normally with `.\.venv\Scripts\python.exe -m app --data-dir .runtime\manual`.

Changed in this continuation: `app/audio/service.py` preserves native errors and clears stale latency when a new turn starts (preventing a cancelled/pending turn from inheriting the previous result's benchmark timing); `app/audio/recognizer.py` removes the console helper; `app/core/process_job.py` exposes scoped PID enumeration; `app/performance/audio_probe.py` uses it; diagnostics record model/binary provenance; WAV benchmarks label source type; new `scripts/validate_microphone.py` and `tests/test_audio_native.py`; regression updates, reports and documentation. No Phase 5 code or new model was added. No companion is intentionally left running after the benchmarks.

## Historical initial implementation record

The following sections preserve the earlier implementation and dependency-blocked validation. Their 82-test count, missing-package statements and 1.5 GiB target are historical; the latest results and 1.8 GiB validation target above supersede them.

## Implemented source

- Explicit first-enable consent; separate persisted auto-listen preference; no default microphone capture. Device-access errors give Windows desktop-microphone permission instructions.
- Lazy sounddevice capture adapter, named input selection, 16 kHz PCM and streaming conversion from supported native sample rates. Background enumeration/settings; sensitivity, endpoint/minimum/max duration, language hints and preview options.
- WebRTC VAD adapter with onset, bounded pre-roll, energy gate, minimum speech, endpoint silence, 25-second maximum and duplicate-trigger prevention. A fixed-capacity callback queue discards incomplete audio on overflow.
- Background coordinator and generation-based cancellation, stream abort/close on mute, bounded disconnect retry, late-result suppression and shutdown cleanup.
- Multilingual whisper.cpp worker through pywhispercpp; CPU/thread limits, no translation/context reuse, explicit verified model path, in-memory PCM, bounded pipe protocol, timeout and process-per-utterance release.
- Windows Job Object ownership before request delivery; cancellation remains responsive even if a worker blocks before reading stdin. Owner-crash cleanup is exercised with a real test process. No unrelated Python processes are terminated.
- Visible microphone panel, context/tray toggle and settings, current status/error detail, bounded plain-text preview beneath the character. Existing animation/drag/scale/topmost/recovery behavior is retained and exercised with a simulated recognition worker.
- Explicit model installation/provenance verifier, dependency/device diagnostic, retained-human-recording tool, transcript-independent WER/CER evaluation, real-WAV and live-microphone all-process benchmark scripts.

The source is **not a claim of verified native capture or multilingual recognition**. Heavy/native package integration cannot be validated until those packages and a model exist locally. The [audio design and acceptance guide](phase-4-audio.md) describes contracts, bounds, commands and limitations. A [rendered disabled-state preview](media/phase4-disabled-preview.png) was inspected for character/panel layout; it is a composite of the app's own rendered widgets, not evidence of physical microphone or desktop interaction acceptance.

## Files created and modified

Created:

| Area | Paths |
| --- | --- |
| Audio | `app/audio/__init__.py`, `config.py`, `capture.py`, `vad.py`, `model.py`, `worker.py`, `recognizer.py`, `service.py`, `evaluation.py` |
| Worker ownership | `app/core/process_job.py` |
| Desktop | `app/desktop/microphone.py` |
| Measurement | `app/performance/audio_probe.py` |
| Installation/validation | `requirements-audio.txt`; `scripts/install_speech_model.py`, `check_audio.py`, `record_speech_samples.py`, `evaluate_speech.py`, `benchmark_speech.py`, `benchmark_microphone.py` |
| Regressions | `tests/test_audio.py`, `tests/test_audio_desktop.py` |
| Documentation/evidence | `docs/phase-4-audio.md`, this report, `docs/media/phase4-disabled-preview.png`, `docs/measurements/phase4-disabled-final.json` |

Modified: `app/__init__.py`, `app/main.py`, `app/core/config.py`, `app/desktop/tray.py`, `app/performance/probe.py`, `scripts/validate.ps1`, `.gitignore`, README, architecture/dependency/roadmap/memory documentation and the Phase 3 acceptance header. Existing settings/position data is preserved; the added `audio` object defaults to unconsented/OFF when loading older settings. Earlier binaries reject unknown settings fields, so a rollback should use an appropriate backed-up configuration rather than silently dropping audio fields. No Phase 5/6 code, external character assets or prohibited repository content was introduced.

## Automated results and fixes

Commands:

```powershell
.\scripts\validate.ps1
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_audio.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_audio_desktop.py -v
```

**Final integrated result: 82 tests passed in 22.633 seconds; zero failures, errors or skips.** The log is retained at `.runtime/phase4-validation.txt`. Dependency consistency (`pip check`) and compilation passed for the installed desktop environment; this does not assert that uninstalled audio packages passed compatibility checks. The preceding 80-test run passed in 22.234 seconds after fixing tray signal dispatch; the final run also includes model hash/header validation and owner-crash cleanup. These counts cover implemented non-hardware tests, not the blocked native checks listed below.

Verified automatically:

- All 57 previous animation/desktop/config/geometry/single-instance/native Windows regressions.
- Synthetic segmentation: silence, short-noise/minimum duration, energy gate, exact PCM framing, consecutive utterances, maximum duration and no duplicate retrigger before silence. The detector is injected; these are **not WebRTC acoustic accuracy results**.
- Simulated capture: selected/missing devices, inactive stream detection, abort/close, buffer clearing, 50-block queue overflow and rejection after cancellation.
- Simulated service: explicit consent, 15 sequential ON/OFF cycles, 100 rapid ON/OFF cycles, no stale result after mute, device released before recognition, cancellation during disconnect retry and actionable preflight failures without opening input.
- Real process mechanics: missing-model worker response/exit, cancellation before spawn, oversized PCM rejection, termination of an intentionally stalled owned process, native Job close, and abrupt owner exit with owned-worker cleanup. These tests do **not** load whisper.cpp.
- Qt: consent decline, error status, tray mute, bounded/plain-text preview/expiry, and animation paints while a synthetic blocking recognizer runs in the background. Resizing/topmost/click-through and visible mute remain usable in that test.
- Evaluation scoring and file gates: WER/CER edits/normalization, missing model, renamed English-only vocabulary rejection, hash mismatch and size mismatch using explicitly artificial model bytes.

Detected/fixed issues: Qt's overloaded QAction signal omitted the boolean when connected directly to `Signal.emit`, preventing tray mute; an explicit lambda now forwards it and the regression passes. A potentially blocking PCM pipe write was moved to its own bounded-lifetime I/O thread so cancellation can close the Job independently. The worker uses the real interpreter with the venv package path to avoid a venv redirector child escaping assignment before it spawns. Repeated preview status updates no longer redisplay an already expired transcript.

## Actual resource measurements — microphone disabled ONLY

Final 60-second Windows run:

```powershell
.\.venv\Scripts\python.exe -m app --data-dir .runtime\phase4-final --benchmark-seconds 60 --report docs\measurements\phase4-disabled-final.json
```

| Metric, GUI plus matching Windows venv launcher | Measured result |
| --- | ---: |
| Median resident working set | **71.848 MiB** |
| Median private commit | **36.191 MiB** |
| Sampled peak resident / private | **72.570 / 37.465 MiB** |
| CPU, percent of one core / whole 12-thread machine | **19.619% / 1.635%** |
| QWidget paint FPS, requested 30 | **30.014** |
| Frame interval p95 / maximum | **35.139 / 48.081 ms** |
| Paint duration p95 | **3.961 ms** |
| Entry-to-first-paint / process-creation-to-first-paint | **1,038.022 / 1,137.298 ms** |
| Event-loop lateness p95 / maximum (including startup) | **2.110 / 394.107 ms** |
| Observed owned processes | **2** |
| Exit code | **0** |

The panel/control integration increases this desktop subset relative to the previous Phase 3 baseline. The numbers include in-app instrumentation and are not directly comparable to the uninstrumented five-minute Phase 3 soak. The desktop probe scans descendants every five seconds and is unsuitable for short ASR-worker accounting; audio-specific probes use a background sampler and 250 ms discovery. Measured paint callbacks are not physical display presentation. The final probe includes startup in heartbeat maxima; no visual smoothness or physical drag-latency claim is inferred.

The desktop subset remains below **1.5 GiB**, but the **Phase 4 mic/recognition total and future full-application target remain unproven**. Neither this short run nor simulated ON/OFF tests rule out native audio/model memory leaks. No unnecessary capture/ASR background process is started while the microphone is disabled. Both benchmark runs exited normally; all recorded PID/creation identities were checked afterward with **zero survivors**, and the final run released its lock. No review companion is intentionally left running.

## Blocked checks — not silently skipped or passed

Actual local diagnostics:

- `pip install --only-binary=:all: ...` failed. Verbose output shows PyPI connection denied by **WinError 10013**; the brief “No matching distribution” message does not identify the root cause.
- `scripts/install_speech_model.py` failed at its first Hugging Face metadata request with the same socket error. No model was downloaded.
- `scripts/check_audio.py` reports missing **sounddevice, webrtcvad-wheels, numpy, soxr and pywhispercpp**, no model, and no successfully enumerated audio devices.
- `scripts/benchmark_microphone.py --consent-to-microphone --seconds 10 --report .runtime/phase4-live-attempt.json` failed its explicit prerequisite check with those missing modules. It did not record audio or produce a performance report.

| Required evidence | Current result |
| --- | --- |
| Physical microphone activation, actual OFF/device release, selection and unplug/replug | **NOT VERIFIED** — dependencies unavailable |
| WebRTC VAD acoustic behavior, resampler and PortAudio native compatibility | **NOT RUN** — native packages unavailable |
| Tiny/Base multilingual recognition | **NOT RUN** — package/model unavailable |
| Human English/Tagalog/Taglish recordings and WER/CER | **NOT AVAILABLE / NOT MEASURED** — no labeled recordings supplied or made |
| Mic-enabled/listening RAM, peak ASR RAM/CPU, latency and memory recovery | **NOT MEASURED** |
| Animation FPS during actual whisper.cpp recognition | **NOT MEASURED** — synthetic background-recognizer responsiveness only |
| Mixed-monitor/DPI and live visual interaction checks | **Manual checks remain** |

Further limitations: optional push-to-talk and a dedicated microphone hotkey are deferred; device enumeration can be cached by PortAudio, requiring restart for a newly attached input; native audio cleanup that hangs beyond six seconds is reported but cannot be safely killed as a Python thread; the exact audio wheel/transitive dependency/backend revision inventory is pending successful installation. These are not concealed by the automated pass count.

## Resume Phase 4

Run the installation/diagnostic commands in the [audio guide](phase-4-audio.md) from a PowerShell with permitted internet access. Start the app with:

```powershell
cd C:\Users\Romcill\Desktop\Local_AI_Companion\offline-ai-companion
.\.venv\Scripts\python.exe -m app --data-dir .runtime\manual
```

Then complete physical microphone acceptance, record the eight reference phrases, run real WER/CER and both recognition/listening benchmarks, fix any native integration errors and update this report with evidence. Only after those Phase 4 gates pass should Phase 5 authorization be requested. No Phase 5 implementation is included or started.
