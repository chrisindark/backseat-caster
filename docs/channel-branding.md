# Channel Brand Consistency (Tier 3)

The channel profile keeps every clip looking like the same channel without
re-selecting the same settings per clip. It is stored in the SQLite database
(`channel_profiles`, singleton row `id = 1`), not in environment variables.

## Where to edit it

Open **Brand** in the navbar (`/channel`) or use the API:

```bash
curl http://localhost:3001/api/v1/channel/profile
curl -X PUT http://localhost:3001/api/v1/channel/profile \
  -H 'Content-Type: application/json' \
  -d '{
    "channel_name": "NightOwl",
    "default_framing_preset": "cinematic",
    "default_quality_preset": "high",
    "title_template": "{title} | {channel}",
    "pinned_hashtags": ["Shorts", "NightOwl"],
    "default_privacy": "public",
    "upload_slots": ["08:00", "12:30", "18:30"],
    "upload_timezone": "Asia/Kolkata"
  }'
curl -X POST http://localhost:3001/api/v1/channel/watermark \
  -F 'file=@logo.png'
```

The logo is saved under `data/channel/` and served for preview at
`GET /api/v1/channel/watermark`.

## What the defaults affect

| Default | Applied where |
|---|---|
| Watermark position/opacity/size/margin | Every new render, in all requested formats, composited before optional intro/outro cards |
| Intro/outro card toggle, copy, colours, lengths | Every new render: a channel card is prepended and a `SUBSCRIBE` card appended inside the same FFmpeg pass (edit at `/channel` → *Intro & Outro Cards*) |
| Framing preset | Render requests that omit a preset, auto-stage, Studio/batch-staging preselects |
| Quality preset | Encoder bitrate/CRF selection for new render jobs |
| Title template | Auto-generated and regenerated titles. Tokens: `{title}`, `{channel}`, `{hero}`, `{game}`, `{event}`, `{date}`, `{clip_id}` |
| Pinned hashtags | Inserted first in tags and appended to descriptions |
| Default privacy | Upload-selection fallback when no privacy is explicitly staged |
| Upload slots + timezone | Native YouTube `publishAt` scheduling when auto-stage assigns slots |

Explicit per-clip values still win; the profile is a default, not a lock.

## Rendering notes

The watermark is one extra still-image input per output. The engine scales the
logo relative to each output's width, so the same asset is proportionally sized
on 1920×1080 landscape and 1080×1920 vertical exports. Rendering still happens
in a single FFmpeg pass. `manifest.json` records the resolved quality preset and
watermark settings.

If the watermark file is removed from disk, rendering degrades gracefully: the
overlay is skipped and the clip renders unbranded.

---

## Planned Extensions

- **Intro & "Subscribe & Bell" CTA Pipeline:** Complete specification and multi-agent milestones for animated lower-third overlay banners, end card screens, edge-tts audio synthesis, and bell chime mixing are documented in [intro-cta-branding-plan.md](intro-cta-branding-plan.md).

