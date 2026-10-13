"""Video filtergraph builders for Landscape and Vertical compositions."""


def build_landscape_filter(
    width: int = 1920,
    height: int = 1080,
    input_label: str = "",
    output_label: str = "",
) -> str:
    """
    Construct filtergraph for 16:9 Landscape export.
    Preserves original aspect ratio using Lanczos scaling and pads with black bars if non-16:9.
    """
    in_prefix = f"[{input_label.strip('[]')}]" if input_label else ""
    out_suffix = f"[{output_label.strip('[]')}]" if output_label else ""
    return (
        f"{in_prefix}scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,"
        f"setsar=1{out_suffix}"
    )


def build_vertical_blur_filter(
    width: int = 1080,
    height: int = 1920,
    blur_sigma: int = 25,
    input_label: str = "[0:v]",
    output_label: str = "[v_out]",
    prefix: str = "v",
) -> str:
    """
    Construct filtergraph for 9:16 Vertical export with blurred background.
    - Background: scaled and cropped to 1080x1920, heavily blurred with boxblur.
    - Foreground: full-width gameplay scaled to fit width 1080, centered vertically.
    """
    in_pad = f"[{input_label.strip('[]')}]"
    out_pad = f"[{output_label.strip('[]')}]"
    p = prefix or "v"
    return (
        f"{in_pad}split=2[{p}_bg_in][{p}_fg_in];"
        f"[{p}_bg_in]scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={width}:{height},boxblur={blur_sigma}:5[{p}_bg];"
        f"[{p}_fg_in]scale={width}:-2:flags=lanczos[{p}_fg];"
        f"[{p}_bg][{p}_fg]overlay=(W-w)/2:(H-h)/2{out_pad}"
    )


def build_vertical_crop_filter(
    width: int = 1080,
    height: int = 1920,
    blur_padding: float = 0.3333,
    blur_sigma: int = 25,
    input_label: str = "",
    output_label: str = "",
    prefix: str = "v",
) -> str:
    """
    Construct filtergraph for 9:16 Vertical crop composition.
    - If blur_padding <= 0: direct 100% full-height center crop.
    - If blur_padding > 0: expanded center crop in middle with blurred top/bottom bars.
      Default 0.3333 allocates ~16.66% top and ~16.66% bottom as blurred background,
      allowing the center crop to be 50% wider (ideal for third-person character views).
    """
    in_pad = f"[{input_label.strip('[]')}]" if input_label else ""
    out_suffix = f"[{output_label.strip('[]')}]" if output_label else ""

    if blur_padding <= 0.001:
        return (
            f"{in_pad}scale=-2:{height}:flags=lanczos,"
            f"crop={width}:{height}:(in_w-{width})/2:0,"
            f"setsar=1{out_suffix}"
        )

    # Compute foreground center crop height (e.g. 1920 * (2/3) = 1280px)
    fg_height = round(height * (1.0 - blur_padding))
    if fg_height % 2 != 0:
        fg_height -= 1

    in_pad_padded = in_pad if in_pad else "[0:v]"
    out_pad_padded = out_suffix if out_suffix else "[v_out]"
    p = prefix or "v"

    return (
        f"{in_pad_padded}split=2[{p}_bg_in][{p}_fg_in];"
        f"[{p}_bg_in]scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={width}:{height},boxblur={blur_sigma}:5[{p}_bg];"
        f"[{p}_fg_in]scale=-2:{fg_height}:flags=lanczos,"
        f"crop={width}:{fg_height}:(in_w-{width})/2:0[{p}_fg];"
        f"[{p}_bg][{p}_fg]overlay=(W-w)/2:(H-h)/2{out_pad_padded}"
    )
