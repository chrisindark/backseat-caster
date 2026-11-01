# Branding Render Fix Plan

## Goal

Make branded intro/outro cards look intentional and ensure the subscribe voiceover finishes before the rendered video ends. Keep preview images, rendered outputs, manifests, staging, and YouTube uploads consistent.

## Findings

- `RenderService.execute_render_job` limits CTA narration to the configured outro duration. With a 2-second outro, generated speech and bell audio can be trimmed at 2 seconds.
- `render_card_png` draws a mostly flat dark full-frame background and uses oversized headline typography, which makes the cards read as a black screen with large text.
- The subtitle placement code does not calculate the subtitle width before centering it, so subtitles can be horizontally misplaced.
- The channel branding preview and final render both call the same card renderer, so updating the renderer will keep them visually aligned.

## Ordered implementation steps

### 1. Preserve CTA audio through the end of the outro

- Determine the complete generated CTA audio duration, including the bell mix.
- Ensure the outro lasts at least as long as the CTA audio, within an explicit supported duration bound.
- Pass the same effective outro duration into video concatenation, audio padding, render metadata, duration budgeting, and upload staging.
- If the CTA cannot fit within the supported bound, surface a clear warning or error instead of silently cutting speech.

### 2. Redesign intro and outro cards

- Replace the plain full-frame text treatment with a polished branded composition using restrained type sizes, clear hierarchy, accent color, and suitable spacing for both landscape and vertical formats.
- Make the outro's subscribe request visually clear without allowing the headline to dominate the whole frame.
- Fix subtitle measurement and centering, and handle long text safely.

### 3. Keep the branding preview aligned

- Confirm the channel preview uses the redesigned card renderer and exposes the same layout creators will see in rendered clips.

### 4. Review render-to-publish consistency

- Review output duration and manifest metadata against the composed video/audio duration and the upload-selection path.
- If a longer CTA outro would exceed the configured composed-duration ceiling, shorten the gameplay window to fit while preserving the complete CTA audio.
- Check that the render job duration, manifest budget, staging data, and upload classification describe the same encoded output.

## Completion notes

Implementation will proceed in the order above. Each step will be completed and reviewed before the next begins.

- **Step 1 complete:** Outro-card CTA speech and bell mixes are generated without a short-card trim. The rendered outro extends to the measured audio duration, and the render duration budget uses that effective outro length. Overlay CTAs retain their configured time window.
- **Step 2 complete:** Intro/outro cards now use a layered branded panel, reduced title sizing, role-specific kicker text, and a subscribe button on the outro. Subtitle layout is measured and centered; long text wraps. The render planner and preview endpoint select the correct card variant. Landscape and vertical PNG previews were rendered and visually reviewed; the vertical CTA button was widened to fit its label.
- **Step 3 complete:** The channel page already requests both card previews from `/channel/branding/preview`; that endpoint and final rendering now select `intro` or `outro` on the shared card renderer. No separate frontend layout implementation was needed.
- **Step 4 complete:** The renderer writes the actual composed duration and bookend budget into the manifest, and the uploader reads that manifest duration. Since audio-driven outro extension can consume more of the clip ceiling, render execution now trims the gameplay window only as much as needed to keep the final composition within the configured ceiling; the persisted job duration follows the encoded window. If the bookends leave less than the minimum gameplay window, rendering fails with a clear error.

## Final verification

- `pytest` on branding, TTS, channel profile, duration budget, duration-budget integration, auto-pipeline, and YouTube upload: **63 passed**.
- `ruff check`, `ruff format`, Python syntax compilation, and `git diff --check` passed.
