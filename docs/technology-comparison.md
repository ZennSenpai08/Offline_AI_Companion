# Technology comparison and selection

Reviewed 2026-11-21. All memory ranges marked **estimate** are engineering planning allowances, not measured results or vendor guarantees. They include active runtime overhead where stated. Package download size is not RAM usage. Latency rankings are hypotheses until measured on the target CPU, which has not been identified.

## Memory first

A 1,024 MiB ceiling must contain the shell, artwork, audio, model runtime, weights, KV cache, and transient allocations. Simultaneous residency of even modest ASR, LLM and TTS workers is risky. The initial design therefore prioritizes sequential residency, a small context, native drawing, and CPU inference. The full arithmetic and measurement definitions are in [memory-budget.md](memory-budget.md).

## Desktop and rendering

Estimates below cover a small animated shell with modest artwork, excluding AI and audio inference. They are deliberately broad, not framework benchmarks.

| Candidate | Estimated RAM | Strengths | Weaknesses and Windows compatibility | License / decision |
| --- | --- | --- | --- | --- |
| Python + PySide6 Essentials Widgets/QPainter | 70–160 MiB | Mature tray, menus, native window APIs; small amount of application code | Python baseline; alpha hit testing and mixed DPI need Windows tests | LGPLv3/GPL/commercial choices; **selected** using eligible modules and dynamic libraries |
| C++ + Qt Widgets | 35–100 MiB | Removes Python shell overhead; same mature desktop features | More build and ownership complexity; audio/ML bridges still needed | Qt license obligations remain; fallback if measured shell cost is excessive |
| C++ Win32 + Direct2D | 20–80 MiB | Maximum control of layered windows and hit testing | Considerably more custom desktop/accessibility/settings code | Windows SDK terms plus chosen library licenses; reserve for demonstrated need |
| Tauri + WebView2 | 100–280 MiB across owned processes | Small distributable; web animation ecosystem | WebView2 process and GPU overhead; a small installer does not imply low RAM | Tauri MIT/Apache-2.0, separate WebView2 terms; defer |
| Electron | 180–400+ MiB across processes | Mature web UI ecosystem | Chromium/Node multi-process cost consumes too much of A's allowance | MIT plus bundled notices; reject for initial stack |

Qt documents translucent top-level widgets and Windows frameless requirements. PySide6 Essentials includes Core, Gui and Widgets without needing the WebEngine stack. [Qt widgets](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QWidget.html), [Essentials package](https://pypi.org/project/PySide6-Essentials/). Tauri uses the system WebView2 runtime on Windows; Electron adopts Chromium's process architecture. [Tauri](https://v2.tauri.app/reference/webview-versions/), [Electron](https://www.electronjs.org/docs/latest/tutorial/process-model).

| Renderer | Incremental planning allowance | Capability / limitation | Decision |
| --- | --- | --- | --- |
| Original layered 2D sprite rig | 8–32 MiB decoded assets/caches | Pivoted arms, eyelids, mouth, hair and head provide actual motion; limited mesh deformation | **Selected**; normalized pose interface leaves room for another renderer |
| Cubism Native SDK | 20–100+ MiB, strongly asset dependent | High-quality deformation and authored physics; needs rigged art, Core and native integration | Defer pending asset-specific memory and license review; not proven too heavy |
| Cubism Web SDK | Asset costs plus web shell above | Convenient web integration; extra runtime processes | Not the initial A renderer |

For scale, a 2,048 × 2,048 RGBA atlas alone occupies 16 MiB before copies, mipmaps or render targets. A static image is not a rig. Greeting/pointing require arm layers; missing capability must use a disclosed facial/head fallback. The renderer choice does not claim parity with a fully rigged Live2D model.

Cubism Core is proprietary and not simply covered by the framework's open source license. Publication rules distinguish ordinary content from Expandable Applications. An application that accepts user avatar models may require the latter review; do not assume the individual/small-business exemption applies. Art and motion licenses are separate. [Core terms](https://docs.live2d.com/en/cubism-sdk-manual/cubism-core/), [publication rules](https://www.live2d.com/en/sdk/license/). Original layered artwork avoids needing Cubism for the first release.

## Audio capture and speech detection

| Candidate | Estimated incremental RAM | Strengths / limitations | Decision and license |
| --- | --- | --- | --- |
| sounddevice / PortAudio | 5–20 MiB including small buffers, excluding NumPy baseline | Windows devices and callbacks; device rates/disconnects still require validation | Selected; MIT components, CFFI dependency |
| WebRTC VAD via webrtcvad-wheels | Less than 5 MiB allowance | No neural runtime, fast binary speech decision; background noise/music can trigger it | Selected; wrapper MIT and bundled WebRTC BSD notices |
| Silero ONNX VAD | 30–90 MiB including separate ONNX session/runtime allowance | Learned speech probabilities; possible better noisy-room performance | Optional only if WebRTC fails the microphone gate; MIT, ONNX Runtime MIT |
| Energy threshold alone | Negligible beyond capture | Simple but poor separation of noise and speech | Use as an auxiliary gate, not the only VAD |

WebRTC accepts mono signed 16-bit PCM at supported rates in 10/20/30 ms frames. Choose 16 kHz / 20 ms after rate conversion. [Frame contract](https://pypi.org/project/webrtcvad-wheels/). Windows sounddevice pip installation supplies PortAudio; this does not prove a particular microphone works. [Installation](https://python-sounddevice.readthedocs.io/en/latest/installation.html). Silero supports an ONNX path; avoid importing Torch merely for VAD. [Silero](https://github.com/snakers4/silero-vad).

## Offline recognition

| Candidate | Memory evidence / estimate | Strengths | Weaknesses / decision |
| --- | --- | --- | --- |
| whisper.cpp multilingual tiny, quantized | **Estimated worker** 220–380 MiB including Python/binding and scratch | Smallest initial multilingual trial; CPU capable | Tagalog and short slang accuracy uncertain; A's first candidate |
| whisper.cpp multilingual base, quantized | **Estimated worker** 300–500 MiB | Potential accuracy improvement without a huge model | More compute; A fallback if tiny fails and sequential peak fits |
| whisper.cpp multilingual small, quantized | **Estimated worker** 500–900 MiB | More recognition capacity | B/C candidate; CPU latency must be checked |
| Faster-Whisper / CTranslate2 INT8 | Upstream small CPU benchmark: **1,477 MB**, 8 threads, i7-12700K; not this application | Mature Python integration, CPU/GPU INT8 | Larger candidate footprint; alternative if measured quality/speed justify it |
| Vosk small English | Upstream describes about **300 MB runtime**, about 50 MB model | Streaming recognition, modest compute | Reviewed catalog does not establish a suitable Tagalog/Taglish model; English-only degraded alternative, not a full requirement match |

whisper.cpp's upstream table reports tiny ~273 MB, base ~388 MB and small ~852 MB; those are unquantized/reference figures with different accounting from our worker estimate. Do not subtract quantization ratios from all memory: scratch does not shrink with weight precision. [whisper.cpp](https://github.com/ggml-org/whisper.cpp). Faster-Whisper's benchmark is a 13-minute workload, not short conversational utterances. [Benchmark](https://github.com/SYSTRAN/faster-whisper). [Vosk catalog](https://alphacephei.com/vosk/models).

Whisper code/model licensing is MIT; pywhispercpp is MIT. Vosk API is Apache-2.0 and each model has its own license. Only multilingual Whisper variants are eligible for the primary pipeline; `.en` and English-only distilled variants do not meet the requirement. CPU builds are the baseline. GPU builds require separately validated native binaries and driver compatibility.

## Language generation

All ranges below are **estimated CPU worker totals**, not GGUF file sizes, with short contexts and no simultaneous ASR/TTS. Quantization does not prove conversational competence.

| Model candidate | Estimated worker RAM | Quality / latency hypothesis | License and selection |
| --- | --- | --- | --- |
| SmolLM2-360M-Instruct Q4 | 300–550 MiB | Very small; English-oriented, no satisfactory Tagalog evidence | Apache-2.0; only explicitly labeled English degraded mode |
| Qwen2.5-0.5B-Instruct Q4 | 430–700 MiB | Compact multilingual baseline; Taglish/slang uncertain | Apache-2.0; comparison candidate if Qwen3 does not fit |
| Qwen3-0.6B Q4_K_M, 1,024 context | 592–782 MiB | Better language-coverage rationale, but tiny size remains a substantial quality risk | Apache-2.0; **A candidate**, non-thinking mode |
| Qwen3-1.7B Q4_K_M, 2,048 context | 1.4–2.1 GiB | More capacity; potentially better context and Tagalog accuracy, more CPU latency | Apache-2.0; **B candidate** |
| Qwen3-4B Q4_K_M, 4,096 context | 3.0–4.5 GiB CPU | Higher expected quality; partial CUDA offload may reduce latency | Apache-2.0; **C candidate**, opt-in only |

Sources: [SmolLM2 card](https://huggingface.co/HuggingFaceTB/SmolLM2-360M-Instruct), [Qwen2.5 card](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct), [Qwen3-0.6B](https://huggingface.co/Qwen/Qwen3-0.6B), [1.7B](https://huggingface.co/Qwen/Qwen3-1.7B), [4B](https://huggingface.co/Qwen/Qwen3-4B). Qwen's published family coverage includes Tagalog, but is not a test of these small quantizations. [Language coverage](https://qwenlm.github.io/blog/qwen3/).

The official 0.6B GGUF repository currently lists Q8_0 at 639 MB on disk. Our Q4 range is an estimate pending a vetted artifact or conversion from original weights; no official Q4 artifact is asserted. [Official files](https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/tree/main).

| Backend | Strengths | Costs / decision |
| --- | --- | --- |
| Owned llama.cpp server | GGUF, CPU/CUDA, memory mapping, streaming, tokenizer/chat template handling, explicit process stop | Authenticated loopback surface and native binary packaging; selected, MIT |
| llama-cpp-python in worker | Direct bindings avoid local HTTP | Windows native wheel/build selection and ABI management; valid fallback, not loaded in UI |
| Ollama | Convenient installation/model management and local API | Shared service/model ownership complicates total accounting and shutdown; not mandatory or selected |

Use one inference slot and bounded context, batch and thread counts. Freeze a tested binary revision and inspect its help; flags change. [llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).

## English speech synthesis

| Candidate | Estimated incremental worker RAM | Strengths | Limitations / decision |
| --- | --- | --- | --- |
| Current Piper, one small/medium English ONNX voice | 170–320 MiB including Python, ONNX and synthesis scratch | CPU-oriented, sentence output, rate controls, PCM available for lips | GPL-3.0-or-later engine; voice-specific terms; **selected for evaluation** |
| Installed Windows SAPI voice | 40–150 MiB, voice dependent; count any spawned voice processes | Offline fallback where a compatible installed voice exists | Voice availability/quality vary; Windows/voice terms; optional degraded mode |
| Kokoro-82M | 400–900+ MiB using a suitably packaged runtime | Promising naturalness | More model/runtime and text-processing overhead; optional C comparison only |

Current Piper differs from the historical MIT project: the maintained package declares GPL-3.0-or-later. Its API exposes streaming PCM and synthesis controls. [Piper](https://github.com/OHF-Voice/piper1-gpl), [API](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md), [package](https://pypi.org/project/piper-tts/). Kokoro's model card declares Apache-2.0; backend and phonemizer licenses still require review. [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M). SAPI provides voice/rate/volume controls; verify an installed local voice and extract actual output PCM for lip sync. [Microsoft SAPI](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/ms723602(v=vs.85)).

No RVC, voice cloning, cloud fallback, second gesture classifier, embedding model, or vector database is needed for the first pipeline. SQLite and bounded text retrieval are sufficient. Failure of a quality or memory gate causes an explicit profile limitation or a measured backend change, not an unsupported claim of success.
