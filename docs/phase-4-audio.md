# Phase 4 audio design and validation guide

The approved Qt / sounddevice / WebRTC VAD / supervised pywhispercpp design is preserved. Phase 4 adds no conversational language model, TTS, server, cloud API or advanced gestures. See the [validation report](phase-4-report.md) before treating native speech support as verified.

## Installation and diagnostics

Run from `C:\Users\Romcill\Desktop\Local_AI_Companion\offline-ai-companion` in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-audio.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/install_speech_model.py
.\.venv\Scripts\python.exe scripts/check_audio.py
.\scripts\validate.ps1 -Audio
.\.venv\Scripts\python.exe -m app --data-dir .runtime\manual
```

The explicit installer obtains multilingual **Tiny Q5_1** from `ggerganov/whisper.cpp`, resolves a repository revision, verifies the download against its upstream LFS SHA-256 and size, and writes a provenance manifest beside the model. It never installs `.en` models. Existing models are verified and preserved. Base Q5_1 can be installed with `--model base` for a separate measured comparison after Tiny works. Runtime verifies the local manifest/hash/header, uses an absolute existing filename and never invokes the downloader. Only Tiny/Base Q5_1 are accepted at this stage. The manifest records MIT licensing and source; it is integrity/provenance metadata, not a digital signature.

The installer needs HTTPS access to Hugging Face; pip needs PyPI and its file host. Runtime recognition needs neither network nor API keys. Earlier agent installation attempts failed with **WinError 10013**; the user subsequently installed the packages/model successfully. No elevation or alternate tunnel was used.

Python 3.10.11 x64 is the working interpreter. All `requirements-audio.txt` pins now import; native VAD/resampling and real Tiny inference on synthetic PCM pass. Capture fails under the agent's `codexsandboxoffline` account despite successful enumeration; run physical checks from your ordinary desktop PowerShell. Desktop-only `validate.ps1` remains available without audio packages. `-Audio` checks installed native components/model and enumeration; neither command by itself certifies physical capture or recognition quality. See the current report for exact errors.

## Consent and user controls

The microphone starts **disabled** until the user selects Enable and accepts the disclosure. Consent and the startup preference are separate settings. A later launch opens input only when both permit it. A successful PortAudio stream open establishes actual device access; Windows failures show instructions for **Settings → Privacy & security → Microphone → Allow desktop apps to access your microphone**. Desktop Python does not fabricate an OS permission prompt or silently alter privacy settings.

The small visible status panel beneath the character provides Enable/Disable. Both the context menu and system tray provide **Microphone ON** and **Microphone settings**. The panel remains interactive when the character is click-through, providing an additional visible mute control. Statuses distinguish Listening, Speech Detected, Transcribing, Microphone Disabled, Device Unavailable and Recognition Error, with brief starting/stopping states. Hover for error detail; no raw audio or transcript is logged. A checked ON action represents the user's requested state; the adjacent status reports actual operation/error.

Settings expose device (host API + name), sensitivity, VAD aggressiveness, endpoint silence, minimum voiced time, maximum segment, language hint, preview and startup preference. Device enumeration runs in a background thread and does not capture. Ambiguous/missing named devices are rejected; the application does not silently switch a named input. Auto language is the default for mixed speech; hints `en` and `tl` are optional. Translation is always disabled.

Preview text is plain text, limited to 400 visible characters, expires after 15 seconds and is not saved. The presentation widget can later receive Phase 8 text events; it does not implement chat. Its own visible rectangle intercepts clicks; it does not create a large invisible overlay. It follows drag/scale/topmost changes and moves the avatar upward when needed to keep the panel on screen. The character renderer and idle engine are unchanged. Very small work areas may require overlapping placement rather than fitting the entire character and panel.

## Audio and process lifecycle

- A single lazy Python coordinator thread owns capture/VAD/recognition orchestration. Qt polls a fixed-size latest-state mailbox every 100 ms; no inference or native audio open/close runs in a Qt callback.
- Capture prefers 16 kHz mono signed 16-bit PCM. Supported native-rate fallback is 32/44.1/48 kHz with streaming SoXR conversion. The PortAudio callback copies at most one 20 ms block into a 50-block queue; it does no inference, file I/O or text logging.
- VAD consumes exact 20 ms frames, a 300 ms pre-roll, a 60 ms onset, configurable minimum voiced time (240 ms default), 600 ms endpoint silence and a maximum 25-second segment. WebRTC classification is combined with an adaptive non-speech energy floor and sensitivity threshold. This is not advanced noise cancellation; real noise rejection must be measured.
- Raw callback storage is at most 96,000 PCM bytes at 48 kHz; retained utterance PCM is at most 800,000 bytes, plus bounded copies during transfer/conversion. These are buffer bounds, not measurements of process RAM.
- Overflow discards the affected partial utterance visibly. A maximum-duration utterance requires a new silence endpoint before another trigger. No queued backlog of recorded speech is processed.
- Capture is aborted and closed before transcription (approved half-duplex policy). After completion and a 300 ms settling interval it reopens if still enabled. Speech spoken while Transcribing is **not captured**. There is one active recognition request and no pending utterance queue.
- The worker receives a bounded binary PCM request over private inherited stdin/stdout, returns bounded JSON and exits after each utterance to release native model memory. The real base Python interpreter is launched with the selected venv's package path, avoiding a Windows venv redirector child racing Job assignment. It waits for input before loading native libraries/models. No Qt is imported in the worker.
- A Windows Job Object with kill-on-close owns the worker before PCM is sent. Cancellation closes only that Job/Popen handle. No global Python-process search/termination is used. The worker also exits on EOF if the parent dies before sending a request. A separate pipe thread makes cancellation work even if the initial pipe write blocks. Inference has a 120-second timeout; failure requires a deliberate retry rather than an infinite respawn loop.
- Microphone OFF invalidates the generation, aborts callback acceptance, closes capture, cancels the worker, clears pending PCM and ignores late results. The status remains Stopping until coordinator cleanup completes. A new ON waits behind cleanup in the same coordinator. Shutdown joins the coordinator with a bounded timeout and logs a failure if native cleanup hangs.
- Device failure retries every three seconds, at most five consecutive failures; mute interrupts the wait. Some PortAudio host APIs cache device enumeration. A newly attached device not listed after refresh can require application restart; actual unplug/replug recovery remains a hardware check.

Optional push-to-talk and a dedicated microphone hotkey are not implemented. Tray/panel mute and the existing character recovery hotkey remain available. LLM and TTS half-duplex coordination belongs to later phases.

## Real recordings and accuracy

The application stores no raw audio by default. The separate evaluation recorder requires an explicit retention flag and an empty destination:

```powershell
.\.venv\Scripts\python.exe scripts/record_speech_samples.py --consent-and-retain-audio --output .runtime\speech-samples
.\.venv\Scripts\python.exe scripts/evaluate_speech.py .runtime\speech-samples\manifest.json --output docs\measurements\phase4-tiny-accuracy.json
.\.venv\Scripts\python.exe scripts/benchmark_speech.py .runtime\speech-samples\01-tagalog.wav --source-kind human-recording --repeats 3 --report docs\measurements\phase4-recognition.json
```

The recorder prompts for the eight requested English/Tagalog/Taglish phrases, records six seconds per phrase, releases the input between phrases, and identifies each WAV as a human microphone recording. Listen to the files locally to verify the speech matches its reference before evaluation. Use additional speakers, accents, background noise and spontaneous mixed-language recordings before generalizing quality. Do not classify generated speech/tones as human recordings. Existing corpora need a JSON `cases` list with `file`, `reference`, `language`, `source` and explicit `synthetic` boolean for every case.

Scoring normalizes Unicode NFKC, case and punctuation; WER uses word edit distance, CER uses character edit distance without spaces. Aggregate scores are weighted by reference length within language groups. The model receives only PCM and the language hint—never the expected transcript. Scores may exceed 1 with many insertions. No score exists until the real model runs on actual labeled audio. Recognition/transcription alone does not prove semantic understanding, which belongs to later LLM evaluation.

## Live microphone and performance acceptance

Close other companion instances first so the recovery hotkey is available. These commands explicitly consent to actual capture, retain no audio/transcripts and count the GUI, matching venv launcher and all observed worker descendants:

```powershell
# Quiet-room listening: remain silent for this run.
.\.venv\Scripts\python.exe scripts/benchmark_microphone.py --consent-to-microphone --seconds 60 --report docs\measurements\phase4-listening.json
# Speech: speak several English/Tagalog/Taglish phrases, waiting for Listening between turns.
.\.venv\Scripts\python.exe scripts/benchmark_microphone.py --consent-to-microphone --seconds 120 --report docs\measurements\phase4-live-speech.json
```

The audio benchmark sampler runs off the UI thread at 100 ms and enumerates every active application-owned Windows Job Object's native PID list, plus GUI/venv launcher. It reports private/resident memory, CPU by phase and QWidget paint FPS. New worker types must use ProcessJob to be included. This avoids the global process scans that distorted earlier instrumentation. It still includes sampling overhead and can miss sub-sample peaks/final CPU; it does not measure physical display presentation, GPU/DWM memory or prove absence of long-duration leaks. Use the audio-specific tools for short ASR worker totals. Worker launches use DETACHED_PROCESS with explicit private pipes, avoiding an unnecessary headless console helper.

An opt-in native stream/Qt-control check is also available. It alternates tray and panel mute, verifies closed PortAudio handles, cleared buffers and stopped callbacks, and checks reopening. A failure before any stream opens is explicitly **not** a successful release test:

```powershell
.\.venv\Scripts\python.exe scripts/validate_microphone.py --consent-to-microphone --cycles 6 --report docs\measurements\phase4-user-physical-toggle.json
```

Manual acceptance:

1. Start with fresh settings: Windows microphone indicator must remain off until explicit consent. Decline once; verify no stream. Enable, grant Windows desktop-app access if needed, and check Listening.
2. Disable during silence, speech and transcription. Confirm Windows' actual capture indicator turns off, the device can be opened by another app and no late transcript appears. Repeat 20 toggles, including rapid OFF/ON. Restart with auto-listen disabled and enabled; verify the saved consent policy.
3. Select each intended device/host API. Deny OS permission, select an unplugged device, then restore permission/reconnect. Confirm actionable status, bounded retries, correct device and no unrequested fallback. Refresh/restart if host enumeration is stale.
4. Record silence, a short click, fan/keyboard noise and normal speech. Check false triggers, endpoint delay and minimum-duration rejection. Speak beyond the maximum segment and verify a visible limit without immediate duplicate transcription. Repeat consecutive utterances only after Listening resumes.
5. Run the recorded corpus evaluation; inspect actual English, Filipino and Taglish output. Test both automatic language and an optional Tagalog hint without translating. Compare Base only if Tiny quality/resources justify it.
6. During real Transcribing, watch and drag/resize the animated character. Verify panel alignment, topmost, click-through recovery and input routing at 125% DPI and other available scales/monitors. Automated widget paints are not physical visual acceptance.
7. Run repeated recognition/recovery and a longer 5–10 minute listening sample. Check total owned-process memory, CPU/FPS and worker exits. Exit while recording and while transcribing, verify device release/worker cleanup/lock release, then restart.

## Primary API references

- [sounddevice raw streams](https://python-sounddevice.readthedocs.io/en/latest/api/raw-streams.html) and [0.5.3 package](https://pypi.org/project/sounddevice/0.5.3/).
- [WebRTC VAD wheel project](https://pypi.org/project/webrtcvad-wheels/) for frame/rate constraints; MIT wrapper and bundled WebRTC notices.
- [SoXR streaming API](https://python-soxr.readthedocs.io/en/latest/soxr.html); wrapper and bundled libsoxr licensing must be preserved when packaging.
- [pywhispercpp 1.5.0 API](https://raw.githubusercontent.com/absadiki/pywhispercpp/v1.5.0/pywhispercpp/model.py) and [Windows CPython wheels](https://pypi.org/project/pywhispercpp/1.5.0/).
- [Multilingual Tiny Q5_1 model](https://huggingface.co/ggerganov/whisper.cpp/blob/main/ggml-tiny-q5_1.bin), published as MIT, approximately 32.2 MB on disk (upstream metadata, not local RAM).
- [Windows Job Object limits](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-setinformationjobobject).
