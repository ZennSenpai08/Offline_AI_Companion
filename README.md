# Original temporary layered character

This teal-haired chibi is original geometric artwork authored for this project in `app/avatar/placeholder.py`. No image, character design, voice or model was downloaded or copied from another companion project. It remains a development placeholder, now animated by the Phase 3 procedural idle system.

Segmentation was inspected before motion was implemented: 19 named body, head, back/front hair, limb, hand, eye, eyebrow, cheek, mouth, scarf and accessory layers. The upper body pivots at the coat/hip overlap (120, 286); the head at the neck (120, 179); hair at (120, 75). Facial features inherit the head transform and the hair pin follows front hair. Legs/boots stay planted while small weight shifts move the upper body. Existing overlaps conceal joint edges; no disconnected parts were seen in inspected poses or extreme-pose tests.

Blinking compresses the open-eye layers and blends into original curved closed lids. Breathing scales the upper-body group slightly; the head and face inherit it. Back/front hair receive different amplitudes from a damped spring. This is rigid layered motion, not mesh deformation or strand simulation. Arms remain independently segmented for Phase 7, but waving, pointing, expressions and lip sync are not implemented or advertised.

The renderer caches cropped raster layers at the current scale/DPI and composites equal-transform neighbors into nine draw groups. It paints directly to the transparent Qt widget without allocating a full image each frame. A bounded motion-envelope mask is rebuilt on scale/orientation/DPI changes, and mouse presses use current-pose alpha. Snapshot export allocates an image explicitly; normal animation does not.

Artwork is included for use and modification with this project; it introduces no third-party asset license. The project's final distribution license remains a later decision. See `docs/media/phase-3-animation.png` for a single-play 18-second APNG rendered from the actual engine.
