"""Command line interface for BackseatCaster rendering engine."""

import argparse
import json
import sys

from app.rendering.config import RenderConfig
from app.rendering.engine import RenderEngine
from app.rendering.probe import probe_media


def main():
    parser = argparse.ArgumentParser(
        prog="backseatcaster-render",
        description="BackseatCaster Local Video Clip Renderer",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Render subcommand
    render_parser = subparsers.add_parser(
        "render", help="Render landscape, vertical-blur, and vertical-crop clips"
    )
    render_parser.add_argument(
        "-i", "--input", required=True, help="Path to input gameplay video"
    )
    render_parser.add_argument(
        "-s", "--start", type=float, required=True, help="Start time in seconds"
    )
    render_parser.add_argument(
        "-d", "--duration", type=float, required=True, help="Clip duration in seconds"
    )
    render_parser.add_argument(
        "-o", "--out", required=True, help="Output directory path"
    )
    render_parser.add_argument(
        "-n",
        "--narration",
        default=None,
        help="Optional voiceover narration audio file",
    )
    render_parser.add_argument(
        "--encoder",
        choices=["auto", "h264_videotoolbox", "libx264"],
        default="auto",
        help="H.264 encoder selection",
    )
    render_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output files if present",
    )
    render_parser.add_argument(
        "--clip-id", default=None, help="Optional custom clip ID"
    )
    render_parser.add_argument(
        "--crop-preset",
        choices=["third_person", "cinematic", "direct_crop"],
        default="third_person",
        help="Vertical crop layout preset (default: third_person with 33% blur padding)",
    )
    render_parser.add_argument(
        "--crop-blur-padding",
        type=float,
        default=None,
        help="Custom vertical blur padding ratio (0.0 to 0.6, e.g. 0.3333)",
    )

    # Probe subcommand
    probe_parser = subparsers.add_parser(
        "probe", help="Inspect video metadata and streams"
    )
    probe_parser.add_argument("-i", "--input", required=True, help="Path to video file")

    args = parser.parse_args()

    if args.command == "probe":
        try:
            res = probe_media(args.input)
            print(json.dumps(res.model_dump(), indent=2))
        except Exception as e:
            print(f"Error probing media: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "render":
        config = RenderConfig(
            preferred_encoder=args.encoder,
            crop_preset=args.crop_preset,
            crop_blur_padding=args.crop_blur_padding
            if args.crop_blur_padding is not None
            else 0.3333,
        )
        engine = RenderEngine(config=config)
        try:
            print(
                f"🎬 Starting render of {args.input} [{args.start}s - {args.start + args.duration}s]..."
            )
            result = engine.render_clip(
                source_path=args.input,
                start_seconds=args.start,
                duration_seconds=args.duration,
                output_dir=args.out,
                clip_id=args.clip_id,
                narration_path=args.narration,
                overwrite=args.overwrite,
                crop_preset=args.crop_preset,
                crop_blur_padding=args.crop_blur_padding,
            )
            print(f"✨ Successfully exported clips to: {result.output_dir}")
            print(
                f"   - Landscape (16:9): {result.local_landscape_path} (stream: {result.landscape_path})"
            )
            print(
                f"   - Vertical Blur (9:16): {result.local_vertical_blur_path} (stream: {result.vertical_blur_path})"
            )
            print(
                f"   - Vertical Crop (9:16): {result.local_vertical_crop_path} (stream: {result.vertical_crop_path})"
            )
            print(
                f"   - Manifest: {result.local_manifest_path} (stream: {result.manifest_path})"
            )
            print(
                f"⏱️ Render completed in {result.render_duration_seconds:.2f}s using {result.encoder_used}"
            )
        except Exception as e:
            print(f"❌ Render failed: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
