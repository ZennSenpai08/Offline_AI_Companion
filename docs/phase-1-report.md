# Phase 1 report — Research and Architecture

Date: 2026-11-21. Status: architecture review complete for user approval, with the validation limits below. Phase 2 has not begun.

## Work actually completed

Read the workspace AGENTS.md before working. Inspected the approved repository through its README and accessible audio, VAD, pipeline, lifecycle, ASR, TTS scheduling, memory, configuration, application and dependency sources. Evaluated desktop/rendering, STT, VAD, LLM and TTS candidates against Windows compatibility, licensing and realistic memory allowances. Defined process ownership, cancellation, half-duplex behavior, original layered animation, gesture capabilities, SQLite categories, profiles, degradation, benchmarks and phase acceptance gates.

The workspace initially contained README.md, architecture.md and reference-review.md as research drafts. Those were reviewed and corrected; no prior application was migrated. Five missing documents were added. No implementation code, models, dependencies, reference artwork or reference source was installed/copied.

## Recommendation

CPython 3.12 x64, PySide6 Essentials/QPainter, an original layered 2D character, sounddevice/WebRTC VAD, pywhispercpp/whisper.cpp multilingual recognition, an owned llama.cpp process, Qwen3 small quantized models, Piper English speech and SQLite. Keep all AI away from the UI thread. A runs heavy stages sequentially. B/C reuse workers only after combined memory is measured. The renderer and inference backends have replaceable contracts.

Initial Profile A envelope: **766–1,036 MiB (0.75–1.01 GiB), estimated including contingency**. It may miss the strict 1 GiB target and it has not passed the Filipino quality gate. The documented broader 1.5 GiB envelope is a separate fallback target. B is estimated at 2.1–3.5 GiB; C's CPU path at 3.8–6.2 GiB, with optional GPU use needing separate accounting.

## Files created or modified

All paths relative to `offline-ai-companion/`:

| File | Change |
| --- | --- |
| [README.md](../README.md) | Updated deliverable index, scope and estimate status |
| [docs/architecture.md](architecture.md) | Reviewed and clarified independent runtime, worker adapters and model provenance |
| [docs/reference-review.md](reference-review.md) | Corrected source/inspection limits and added VAD observation |
| [docs/technology-comparison.md](technology-comparison.md) | Created candidate tables, licensing and selection rationale |
| [docs/memory-budget.md](memory-budget.md) | Created derived budget, A/B/C profiles, degradation and repeatable benchmark protocol |
| [docs/dependencies.md](dependencies.md) | Created dependency/asset inventory and compatibility evidence |
| [docs/roadmap.md](roadmap.md) | Created all phase gates, Filipino evaluation specification and risk register |
| [docs/phase-1-report.md](phase-1-report.md) | Created this report |

## Verified findings and real checks

- `Get-Content -LiteralPath AGENTS.md`: succeeded; instructions read, including Phase 1-only scope and phase approval requirement.
- `rg --files --hidden ...` and workspace listing: succeeded; initially found AGENTS.md plus three research documents, no application source.
- Primary-source web inspection: accessible reference implementation files and vendor/package/model documentation reviewed. Qt translucency/frameless support, PCM ASR input, Piper PCM streaming, Qwen Tagalog family coverage and Windows wheel metadata were confirmed as documented capabilities, not local integration results.
- `python -c ...`: succeeded, reports Python 3.9.13 x64. `py -0p` lists Store Python 3.13; `py -3.13 -c ...` fails to create that process. A working selected interpreter remains a Phase 2 prerequisite.
- `Invoke-RestMethod -Uri 'https://api.github.com/repos/LiiLk/Local-AI-Companion/commits/main'`: failed with socket permission restrictions. Read-only web access provided research evidence without requiring a clone.
- Individual upstream test and Qt shell source fetches failed with cache misses. Upstream tests were not run; no reference performance claim was adopted as a local result.

Documentation consistency and scope audit: a one-off Python standard-library script supplied through a PowerShell here-string to `python` checked every local Markdown link, required deliverable existence, nonempty documents, paired code fences, budget arithmetic and absence of non-document files. **Exit code 0**; output:

```text
Documents: 8
Local link occurrences checked: 21
Budget arithmetic: KV=112 MiB; sequential=766-1036 MiB; concurrent=1156-1736 MiB
Non-document files: 0
Errors: 0
```

`rg -n 'TODO|TBD|PLACEHOLDER|passed|measured|completed|NOT RUN|cp31' offline-ai-companion/docs` and a file inventory were reviewed for unfinished claims and compatibility statements. The Phase 2 placeholder-art mention is a future test asset, not a completed avatar. No feature/unit/integration benchmark was run because no application has been implemented.

## Performance and limitations

**Actual application performance: not measured.** Every local RAM/latency/FPS/VRAM/accuracy metric remains NOT RUN. The budget contains estimates, mathematical buffer/cache calculations and explicitly attributed upstream values.

The reference review is not a reproducible single-commit audit: web views have differing crawl dates and no consistent commit hash was recovered. Deep desktop hit testing and upstream test implementation were unavailable. These limits do not prevent an independent architecture recommendation, but they prevent claiming verified reference behavior.

The 0.6B official GGUF listing inspected contains Q8_0 only; a trustworthy Q4 artifact/conversion is still needed. Tiny-model Filipino quality is unknown. Current Piper is GPL-3.0-or-later; each voice has separate rights to review. Live2D is deferred for license/integration and asset-budget reasons, not because it was measured to exceed the memory target. Original production artwork is not yet created.

## Next phase and stop condition

Phase 2 will establish a working isolated Python/Qt environment and implement the transparent draggable shell, always-on-top setting, tray, scale, saved monitor-aware placement and clean exit, then test actual Windows interaction and baseline resources. It will not load AI models or implement later phases.

The workspace [AGENTS.md](../../AGENTS.md), section 20 rule 20, says: “Stop after each completed phase and request authorization to continue.” Section 22 explicitly requests approval before Phase 2. Work stops here pending that approval.
