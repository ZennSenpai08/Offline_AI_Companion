# Memory budget, feasibility, and benchmark protocol

Latest Phase 4 measurement: a 60-second externally sampled microphone-OFF run measured **68.707 MiB median resident / 33.898 MiB private** and **1.424% whole-machine CPU**. Actual Tiny Q5_1 inference on explicitly synthetic silence peaked at **225.414 MiB resident / 677.398 MiB private** across all owned processes, maintained **29.976–30.029 paint FPS**, and returned near baseline after worker exit. Physical capture and real speech-quality/resource validation remain pending. The latest user-requested Phase 4 ceiling is **1.8 GiB**; the numbers/targets below preserve Phase 1 planning history. See [Phase 4 report](phase-4-report.md) for methodology, limitations and exact hardware-access errors.

Historical baseline for the estimates below: Phase 1, 2026-11-21. No companion process/model had been run at that point. Desktop and native ASR synthetic-input measurements now exist as linked above; real speech, recognition quality and conversational generation remain unmeasured.

## Targets and accounting

The strict engineering target for A is **less than 1,024 MiB (1 GiB)** across all application-owned processes. The broader requested A envelope is **less than 1,536 MiB (1.5 GiB)**. Meeting the broader envelope does not count as meeting the stricter target. Neither is currently proven.

Record three separate memory series:

1. Sum of private committed bytes across the UI and every owned worker, including transient overlap during start/stop. Private commit is not synonymous with physical RAM.
2. Sum of resident working sets, explicitly labeled as potentially double-counting shared pages; include mapped model pages. Also report private working set and mapped resident pages where obtainable. Never treat mmap weights as free merely because private commit excludes clean file-backed pages.
3. Dedicated and shared GPU memory attributable to owned processes; report separately from host memory and do not hide shared GPU allocations. Include Windows composition overhead as a separately reported system observation where attributable; never subtract it to improve the result.

Use owned process handles/creation times and the Job Object membership, not process names. Sample synchronously at 100 ms for benchmarks and around load/unload boundaries; keep exit-time peaks and Job Object aggregate peak commit as additional evidence. Peak of a sampled sum is not the sum of independent process peaks. Shorter spikes can be missed, so report sampling resolution. Microsoft exposes process memory statistics and grouped process accounting. [Memory counters](https://learn.microsoft.com/en-us/windows/win32/psapi/process-memory-usage-information), [Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects).

An A success claim requires private commit below the threshold **and** transparent disclosure of working-set/mapped/GPU use; do not declare low total RAM on private commit alone. Use summed working set as a conservative resident-memory gate until unique physical attribution is available.

## Profile A: bottom-up estimate

All figures in this section are **planning estimates in MiB**, not measurements. The weight allowance counts the resident mapping once; the runtime allowance excludes those weights. Sum-of-working-set measurements may differ. Model allocation and import peaks are not yet characterized.

| Component | Estimated active contribution | Assumptions |
| --- | ---: | --- |
| Python, Qt, original artwork, small windows | 85–150 | Widgets/QPainter, 30 FPS, bounded decoded layers, no browser |
| Audio, VAD, NumPy baseline, coordinator, SQLite, monitoring | 25–40 | Small buffers, no neural VAD, bounded history |
| **Persistent main process total** | **110–190** | Includes all baseline runtime work |
| ASR worker, multilingual tiny quantized | 220–380 | Includes its interpreter, binding, model and scratch |
| LLM quantized weights | 400–500 | Qwen3-0.6B Q4_K_M allowance; artifact not installed |
| LLM F16 KV cache | 112 | Calculated for 1,024 tokens, see below |
| LLM non-weight/non-KV runtime and scratch | 80–170 | One slot, small prompt batch/microbatch, CPU build |
| **LLM worker total** | **592–782** | Sum of preceding three rows |
| Piper English voice worker | 170–320 | Interpreter, ONNX model/runtime, bounded synthesis output |
| Contingency | 64 | Budget reserve, not an observed allocation |

With strict sequential heavy-stage residency:

`peak planning envelope = baseline + max(ASR, LLM, TTS) + contingency`

`low = 110 + 592 + 64 = 766 MiB (0.748 GiB)`

`high = 190 + 782 + 64 = 1,036 MiB (1.012 GiB)`

The upper estimate crosses 1 GiB. This is a feasible investigation, not a promise. Keeping all three workers resident yields **1,156–1,736 MiB (1.13–1.70 GiB)** with the same reserve, and is not the default A policy. No overlap is allowed until the prior process has exited and its memory release is observed; process retirement itself must be measured.

Upgrading tiny to base at an estimated 300–500 MiB can still leave LLM inference as the sequential peak, but increases recognition latency/loading cost. A small ASR worker may become the peak. User-visible language quality must determine whether tiny is acceptable.

### Derivations and uncertainty

Qwen3-0.6B's [configuration](https://huggingface.co/Qwen/Qwen3-0.6B/blob/main/config.json) gives 28 layers, 8 KV heads and a 128-element head. For standard full attention F16 K and V:

`2 (K,V) × 28 × 8 × 128 × 1,024 × 2 bytes = 117,440,512 bytes = 112 MiB`.

At 2,048 tokens this cache alone becomes 224 MiB. Padding, metadata and implementation buffers are additional; alternate cache quantization must be tested for quality and backend compatibility, not assumed. Start A at 1,024 context tokens including system, history, user turn and reserved response; reserve 128 output tokens and trim oldest complete turns first. Initial batch/microbatch ceilings are 128/64 tokens; inspect supported flags in the pinned engine.

The theoretical 0.6-billion-parameter four-bit payload is about 286 MiB, but block scales, non-four-bit tensors, vocabulary and metadata make that a lower bound, not a GGUF size. The 400–500 MiB allowance is deliberately larger. Official Q8_0 is listed as 639 MB, approximately 609 MiB on disk; that is neither Q4 nor a runtime benchmark. [Official listing](https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/tree/main).

25 seconds of mono 16 kHz PCM16 is 800,000 bytes, approximately 0.763 MiB. A float32 ASR copy adds 1.526 MiB. Four seconds of 48 kHz stereo float32 output adds 1.465 MiB. Audio buffers themselves are small; excessive model/runtime residency is the larger risk. A renderer's 2,048-square RGBA atlas costs 16 MiB before extra copies. Cache counts and scaling variants must be bounded.

Published whisper.cpp figures are **upstream reference values**, not our measurements: tiny ~273 MB, base ~388 MB, small ~852 MB. Their units and accounting are retained as published. Quantized worker estimates include additional Python and scratch allowances and must be validated independently. [Upstream table](https://github.com/ggml-org/whisper.cpp#memory-usage).

## Three profiles, one architecture

| Setting | A: Ultra-Low-Memory | B: Balanced | C: Enhanced |
| --- | --- | --- | --- |
| ASR candidate | Multilingual tiny Q5; base Q5 if quality requires | Multilingual small Q5 | Same small initially; larger only after a justified test |
| LLM candidate | Qwen3-0.6B Q4_K_M | Qwen3-1.7B Q4_K_M | Qwen3-4B Q4_K_M, or 1.7B if GPU headroom is insufficient |
| Context / output tokens | 1,024 / 128 | 2,048 / 256 | 4,096 / 384 |
| TTS | One Piper English voice | Same engine, chosen voice | Piper first; optional Kokoro comparison |
| Heavy residency | One stage at a time | Retain only after combined peak passes; overlap LLM/TTS if safe | Same ownership rules; measured CPU/GPU split |
| CPU threads | Start at 2, never exceed available cores; leave UI capacity | Start at 4 with aggregate cap | Start at 4; coordinate CPU/GPU work |
| Animation target | 30 FPS, pressure floor 20 | 30 FPS | Optional 60 FPS |
| **Host planning envelope, not measurement** | **766–1,036 MiB** | **2.1–3.5 GiB** with resident models | **3.8–6.2 GiB CPU path**; GPU path must be separately measured |
| GPU | None required | None required | Optional partial CUDA offload |

B's rough envelope sums a 0.11–0.19 GiB baseline, 1.4–2.1 GiB LLM, 0.5–0.9 GiB ASR, 0.17–0.32 GiB TTS and allowance for transitions (rounded). C increases LLM/runtime/context cost; its upper bound adds extra loading/driver contingency. These are broad capacity-planning envelopes, not quality guarantees.

On a 4 GiB RTX 2050, start with at least 1 GiB reserved for desktop/other users and use only available VRAM below that limit. A 4B model plus KV/scratch may not fully fit. Lower GPU layers or use 1.7B; do not launch GPU ASR concurrently by default. GPU offload can retain host mappings and staging buffers, so subtracting VRAM from the CPU estimate is invalid. No CUDA speedup or VRAM consumption has been measured here.

## Degradation and worker reuse

At startup, read available system memory and the last measured model admission estimate. Do not load if projected peak exceeds the chosen profile cap or leaves insufficient OS headroom (initial reserve 1 GiB). Runtime pressure handling is independent of the UI thread:

1. Cancel pending work and retire inactive models; drain buffers and verify process exit. In B/C, switch to A's sequential policy before changing models.
2. Reduce context at the next turn, never mid-generation; shorten output and prompt batches. A 768-token F16 KV cache calculates to 84 MiB, freeing 28 MiB against 1,024 tokens, at the expense of memory/context quality.
3. Reduce artwork caches/frame rate within the continuous-animation floor. Do not empty working sets to disguise resident demand.
4. Select a smaller **already installed and evaluated** model or local SAPI voice with a visible quality notice. A different language model must pass its own Filipino gate.
5. If safe model admission is impossible, keep the desktop/text editor usable and show that AI is unavailable. This UI-only state does not satisfy the functional offline-companion target.

Reusable workers avoid reimporting/reloading during a permitted residency interval. Profile A intentionally trades this benefit for process exit between heavy stages. Benchmark reliable explicit unload later; allocator reuse is not evidence that committed memory was released. Avoid automatic restart loops and repeated failed loads under pressure. Pressure thresholds, projected admission costs and hysteresis are settings to validate in Phase 10.

## Repeatable benchmark plan

Record OS build, CPU model/core count, RAM, SSD, GPU/driver, power mode, display DPI, application revision, dependency versions, model/voice hashes, asset size, context, batch/thread settings and profile. Use 3 cold launches and 20 warm turns per scenario; retain raw timestamped observations and report p50/p95/max, including failures. Do not flush the operating system cache artificially and call that a normal cold launch.

| Scenario | Measurements and expected evidence |
| --- | --- |
| Idle 10 minutes, microphone OFF and ON | Total private/working-set memory, all-owned-process CPU, frame interval distribution, capture overruns |
| Fixed 5/15/25-second English, Tagalog and Taglish audio | Endpoint delay separately from ASR time, real-time factor, WER/CER and human intent accuracy |
| Fixed text turns, full context, 128/256-token responses | Model startup/load time, first token from request, tokens/sec, peak private/resident/GPU memory |
| Fixed English sentences | TTS load/first-PCM/total synthesis time, playback latency, underruns, mouth envelope alignment |
| Full voice turn | Last user speech sample to first audible reply and full completion; include reloads, endpoint silence and scheduling |
| Cancel/mute/restart/unplug/invalid model | Cancellation acknowledgement, actual compute termination, stale-event rejection, microphone release and recovery |
| 100 load/unload cycles plus 8-hour soak | Per-process and aggregate trends, post-unload baseline, handle/thread counts, queues; investigate growth over 10% or 30 MiB after warmup |
| Offline and packaged runs | Block outbound networking, allow owned loopback only; no downloads or remote fallback; repeat all critical tests on clean Windows |

Initial responsiveness goals, **not achieved results**: 30 FPS with p95 frame gaps under 50 ms, idle normalized CPU below 2% on reference hardware, stop-audio response within 150 ms, microphone state indication within 100 ms and confirmed device close within 500 ms. Set conversational latency acceptance from Phase 4/5 measurements; do not invent tokens/sec for the unspecified CPU.

Current benchmark record: startup, idle CPU, UI FPS, capture latency, ASR latency, first token, tokens/sec, TTS latency, end-to-end latency, peak RAM and VRAM are all **NOT RUN**. No under-1-GiB or production-readiness claim is authorized by this document.
