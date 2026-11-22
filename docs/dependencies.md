# Dependencies, compatibility, licensing and setup boundary

## Phase 4 installation status

The user installed all `requirements-audio.txt` pins: sounddevice 0.5.3, webrtcvad-wheels 2.0.14, NumPy 2.2.6, SoXR 0.5.0.post1 and pywhispercpp 1.5.0. Python 3.10.11 x64 imports, native VAD/resampling, Tiny Q5_1 worker inference and `pip check` pass. The model's revision/size/SHA-256/multilingual header/MIT provenance are verified. [Installed versions](measurements/phase4-installed-packages.txt) and [native binary hash/environment](measurements/phase4-audio-environment.json) identify the tested environment; a full wheel-hash distribution lock and the binding's exact underlying whisper.cpp Git revision remain unavailable. Actual microphone capture still fails under the agent account; enumeration alone is not hardware compatibility. See [current results](phase-4-report.md). No LLM/TTS dependency/model was added. Desktop requirements are unchanged.

## Desktop and animation dependency status

Phase 3 adds no dependencies or model downloads. `requirements.txt` pins only PySide6-Essentials 6.10.2, matching shiboken6 6.10.2 and psutil 7.2.2. Tests use standard-library unittest and QtTest instead of adding pytest/pytest-qt. This reduces the initial dependency surface. No AI/audio packages are installed by setup. Current environment: Python 3.10.11 x64 runs and a project-local `.venv` was created; 3.12 remains recommended. Phase 2's subset accepts 3.10–3.14, but this is not a validated full AI dependency matrix. The user installed dependencies locally. Imports, pip check, all 44 Windows tests and application launch now pass with Python 3.10.11 x64 / Qt 6.10.2 / psutil 7.2.2. Python 3.12 remains untested locally.

Pinned release metadata: [PySide6 Essentials](https://pypi.org/project/PySide6-Essentials/6.10.2/), [shiboken6](https://pypi.org/project/shiboken6/6.10.2/), [psutil](https://pypi.org/project/psutil/7.2.2/). Keep Qt LGPL/GPL/commercial obligations and third-party notices in the eventual package. No final project distribution license has been applied. The inventory below remains the Phase 1 plan for later components.

Research date: 2026-11-21. This is a proposed dependency inventory, not an installation manifest or resolved lockfile. No packages/models were installed in Phase 1. Windows x64 and CPython 3.12 are the baseline; wheel metadata establishes candidate compatibility, not a successful integration test.

## Runtime inventory

| Component | Purpose / phase | Compatibility evidence and candidate | License / packaging action |
| --- | --- | --- | --- |
| CPython 3.12 x64 | Host, Phase 2 | Supported baseline chosen conservatively; a working installation is still needed here | PSF; include interpreter notices |
| PySide6-Essentials + matching shiboken6 | Widgets, drawing, tray, signals; Phase 2 | PyPI lists 6.12.0 cp310-abi3 win_amd64; compatible ABI tag for 3.12; pair exact matching versions | LGPLv3/GPL/commercial; use eligible modules, preserve notices and required replaceability/source provisions |
| sounddevice + CFFI + PortAudio | Capture/playback, Phase 4/6 | Official installation documents Windows binary support | MIT-family components; audit bundled DLL notices |
| NumPy | Bounded PCM, numerical envelopes, Phase 4 | Required by recognition binding; pin a mutually supported Windows wheel during resolution | BSD-3-Clause; include bundled numerical-library notices |
| webrtcvad-wheels | VAD, Phase 4 | 2.0.14.post1 explicitly lists cp312-cp312-win_amd64 | MIT wrapper plus bundled WebRTC notices; install instead of duplicate webrtcvad package |
| soxr | Streaming rate conversion if device rate differs, Phase 4 | Package documents Windows wheels and NumPy input | Python wrapper BSD-3-Clause; libsoxr LGPL-2.1-or-later; verify bundled notices |
| pywhispercpp / bundled whisper.cpp | ASR worker, Phase 4 | 1.5.1 lists cp312 Windows x64 wheel; model API accepts NumPy arrays | MIT; record wheel and underlying backend revision/hash; no automatic model download |
| llama.cpp CPU binary | LLM worker, Phase 5 | Native Windows builds; Qwen model card documents llama.cpp usage | MIT; freeze tested build, preserve notices; optional CUDA separately validated |
| HTTP client | Local inference, Phase 5 | Prefer Python standard library streaming in coordinator thread; no UI-thread reads | Standard library; use bounded reads, timeouts and cancellation |
| piper-tts + ONNX Runtime CPU + phonemizer dependencies | TTS worker, Phase 6 | 1.8.0 has cp39-abi3 Windows x64 wheel and Python >=3.9 metadata | Piper GPL-3.0-or-later, ONNX Runtime MIT; preserve all bundled phonemizer/data terms |
| sqlite3, json, logging, threading, queue, ctypes | Storage/config/runtime/Win32 integration | Python standard library; no separate SQLite server | Python and SQLite notices; SQLite upstream is public domain |
| psutil | Process metrics, introduced with first runnable shell | Package supports Windows; resolve a matching wheel | BSD-3-Clause; cross-check Windows counters against native APIs |
| pytest + pytest-qt | Critical behavior tests in corresponding phases | Development only; choose versions compatible with the pinned Qt/Python pair | MIT; not runtime dependencies |
| PyInstaller | Windows one-folder packaging, Phase 12 | Candidate only; frozen multiprocessing, Qt plugins and native DLLs require packaged tests | GPL with bootloader exception; audit actual distribution |

Sources: [Qt wheel/modules](https://pypi.org/project/PySide6-Essentials/), [Qt license](https://doc.qt.io/qt-6/licensing.html), [sounddevice](https://python-sounddevice.readthedocs.io/en/latest/installation.html), [VAD wheels](https://pypi.org/project/webrtcvad-wheels/), [SoXR](https://pypi.org/project/soxr/), [ASR wheels](https://pypi.org/project/pywhispercpp/), [ASR API](https://raw.githubusercontent.com/absadiki/pywhispercpp/main/pywhispercpp/model.py), [llama.cpp](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md), [Piper wheels](https://pypi.org/project/piper-tts/), [psutil](https://pypi.org/project/psutil/).

Do not import Qt in inference workers. Do not import ASR/TTS libraries in the UI process. No Torch, Transformers, browser engine, Node, web server framework or FFmpeg is needed for the normal PCM/GGUF/ONNX path. Quantization/conversion tooling belongs to a separate preparation environment, not the installed runtime.

## Models and assets

| Artifact | Initial choice / selection gate | License handling |
| --- | --- | --- |
| ASR | Multilingual Whisper tiny Q5, base Q5 if quality requires | MIT model/code lineage; exact model source/hash and quantization recipe must be recorded |
| LLM A | Qwen3-0.6B Q4_K_M | Apache-2.0; official GGUF listing has Q8_0 only, so obtain a vetted Q4 conversion or convert original weights during setup |
| LLM B/C | Qwen3-1.7B / 4B Q4_K_M | Apache-2.0 cards reviewed; opt-in installation after justification |
| English voice | Piper en_US-ljspeech-medium is a concrete audition candidate; smaller voice only if quality/license permit | Review the per-voice model card and dataset terms; repository-wide MIT label alone is insufficient |
| Character | Original layered anime artwork with explicit redistribution grant and rig metadata | Record author, source, usage/redistribution rights, supported poses and texture limits; no reference-project character/voice assets |
| Optional Live2D | None in baseline | Core/framework/publication/Expandable Application and artwork rights are separate gates |

The candidate LJSpeech medium ONNX file is listed at 63.5 MB (about 60.6 MiB) on disk; runtime usage is much larger and remains estimated. Its card identifies English speech at 22,050 Hz and the dataset as public domain; preserve the exact model/repository terms when preparing the artifact. [Files](https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/ljspeech/medium), [voice card](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/ljspeech/medium/MODEL_CARD). The inspected Lessac low card points to separate dataset license terms; it is not automatically interchangeable with a freely redistributable voice. [Lessac card](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/lessac/low/MODEL_CARD).

For distribution, a GPL-compatible open-source release is the simplest proposed licensing route with current Piper. No project license is applied in Phase 1. Process separation is for ownership/memory, not an asserted exemption from GPL obligations. Freeze the exact engine, transitive phonemizer and voice licenses before bundling. If a future closed-source distribution is required, review that constraint before adopting a different TTS route. [Piper license declaration](https://pypi.org/project/piper-tts/).

## Compatibility findings on this workstation

Actual read-only commands on 2026-11-21:

- `Get-Command python,py,git`: finds a Python39 executable, Windows Python launcher, and Git.
- `python -c "import sys,struct; print(sys.version); print(sys.executable); print('bits:', struct.calcsize('P')*8)"`: succeeds; Python **3.9.13, 64-bit**. This is not the selected interpreter.
- `py -0p`: reports a registered Python 3.13 x64 Store installation.
- `py -3.13 -c "import sys,struct; print(sys.version); print(sys.executable); print('bits:', struct.calcsize('P')*8)"`: fails to create the Store Python process in this environment. Registration is not evidence of a usable interpreter.
- Direct `Invoke-RestMethod` to the approved repository's GitHub API fails with socket permissions. Web research works. No permission escalation or global installation was attempted.

Before Phase 2 implementation, locate/provision a runnable supported Python in the project environment, then install only the Qt/test/measurement subset. A working 3.13 can be reconsidered after verifying the full dependency wheel matrix; do not silently use 3.9 with the current packages.

## Dependency acceptance process for later phases

Resolve exact versions into a fresh isolated environment; use Windows x64 binary wheels where possible. Run dependency consistency checks, import tests and a minimal native operation for each newly introduced component. Capture hashes, software bill of materials and notices. Freeze the tested combination rather than claiming floating `>=` requirements are reproducible.

Model manifests must include revision, SHA-256, size, format, quantization, source model, license, tokenizer/template requirements and an offline self-test. Reject missing or mismatched artifacts with actionable messages. Review third-party conversions rather than assuming the repository name proves provenance. Runtime loading uses local paths and no arbitrary remote code.

Initial installation may use Python/PyPI, upstream binary releases and model hosting over HTTPS. Normal execution uses local files and only the authenticated owned loopback inference endpoint. Optional updates are user initiated, never a fallback for failed inference. A clean-machine offline installation bundle and packaged runtime are Phase 12 deliverables, not current capabilities.
