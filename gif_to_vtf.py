"""Convert an animated GIF into the VTF layout used by the working spray tool."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


DEFAULT_WIDTH = 252
DEFAULT_HEIGHT = 256
DEFAULT_FLAGS = 0x230C
DXT1_FORMAT = 13
MAX_FRAMES = 64


class GifToVtfError(ValueError):
    """Raised when a GIF cannot be converted to a spray VTF."""


def _pack_rgb565(color: tuple[int, int, int]) -> int:
    red, green, blue = color
    return (
        ((red * 31 + 127) // 255) << 11
        | ((green * 63 + 127) // 255) << 5
        | ((blue * 31 + 127) // 255)
    )


def _unpack_rgb565(value: int) -> tuple[int, int, int]:
    return (
        ((value >> 11) & 31) * 255 // 31,
        ((value >> 5) & 63) * 255 // 63,
        (value & 31) * 255 // 31,
    )


def _dxt1_block(pixels: list[tuple[int, int, int, int]]) -> bytes:
    transparent = any(alpha < 128 for _, _, _, alpha in pixels)
    opaque = [(red, green, blue) for red, green, blue, alpha in pixels if alpha >= 128]
    if not opaque:
        return struct.pack("<HHI", 0, 0, 0xFFFFFFFF)

    low = tuple(min(pixel[channel] for pixel in opaque) for channel in range(3))
    high = tuple(max(pixel[channel] for pixel in opaque) for channel in range(3))
    low_endpoint = _pack_rgb565(low)
    high_endpoint = _pack_rgb565(high)
    if transparent:
        color0, color1 = sorted((low_endpoint, high_endpoint))
    else:
        color0, color1 = max(low_endpoint, high_endpoint), min(low_endpoint, high_endpoint)
        if color0 == color1:
            color0 = min(0xFFFF, color0 + 1)
            color1 = max(0, color1 - 1)

    palette = [_unpack_rgb565(color0), _unpack_rgb565(color1)]
    if color0 > color1:
        palette.extend((
            tuple((2 * palette[0][index] + palette[1][index]) // 3 for index in range(3)),
            tuple((palette[0][index] + 2 * palette[1][index]) // 3 for index in range(3)),
        ))
    else:
        palette.append(tuple((palette[0][index] + palette[1][index]) // 2 for index in range(3)))
        palette.append((0, 0, 0))

    indices = 0
    for pixel_index, (red, green, blue, alpha) in enumerate(pixels):
        if transparent and alpha < 128:
            palette_index = 3
        else:
            palette_index = min(
                range(3 if color0 <= color1 else 4),
                key=lambda index: sum(
                    (value - target) ** 2
                    for value, target in zip((red, green, blue), palette[index])
                ),
            )
        indices |= palette_index << (pixel_index * 2)
    return struct.pack("<HHI", color0, color1, indices)


def _encode_dxt1(image) -> bytes:
    width, height = image.size
    pixels = list(image.getdata())
    blocks = bytearray()
    for block_y in range(0, height, 4):
        for block_x in range(0, width, 4):
            block = []
            for local_y in range(4):
                for local_x in range(4):
                    x = min(width - 1, block_x + local_x)
                    y = min(height - 1, block_y + local_y)
                    block.append(pixels[y * width + x])
            blocks.extend(_dxt1_block(block))
    return bytes(blocks)


def _fit_frame(image, width: int, height: int):
    from PIL import Image

    image = image.convert("RGBA")
    image.thumbnail((width, height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    canvas.alpha_composite(image, ((width - image.width) // 2, (height - image.height) // 2))
    return canvas


def _template_header(template: Path | None) -> tuple[bytearray, int, int]:
    if template is None:
        header = bytearray(64)
        struct.pack_into("<4sII", header, 0, b"VTF\x00", 7, 1)
        struct.pack_into("<I", header, 12, 64)
        struct.pack_into("<HH", header, 16, DEFAULT_WIDTH, DEFAULT_HEIGHT)
        struct.pack_into("<I", header, 20, DEFAULT_FLAGS)
        struct.pack_into("<I", header, 52, DXT1_FORMAT)
        header[56] = 1
        struct.pack_into("<I", header, 57, DXT1_FORMAT)
        return header, DEFAULT_WIDTH, DEFAULT_HEIGHT

    data = template.read_bytes()
    if len(data) < 64 or data[:4] != b"VTF\x00":
        raise GifToVtfError(f"模板不是有效的 VTF：{template}")
    header_size = struct.unpack_from("<I", data, 12)[0]
    if header_size < 64 or len(data) < header_size:
        raise GifToVtfError("VTF 模板头部不完整")
    major, minor = struct.unpack_from("<II", data, 4)
    width, height = struct.unpack_from("<HH", data, 16)
    image_format = struct.unpack_from("<I", data, 52)[0]
    mip_count = data[56]
    low_width, low_height = data[61], data[62]
    if (major, minor) != (7, 1):
        raise GifToVtfError("模板必须使用 VTF 7.1，才能匹配网站输出格式")
    if image_format != DXT1_FORMAT or mip_count != 1 or low_width or low_height:
        raise GifToVtfError("模板不是网站使用的 DXT1、单 mipmap、无缩略图格式")
    return bytearray(data[:header_size]), width, height


def encode_frames_to_vtf(
    frames: list,
    output: str | Path,
    template: str | Path | None = None,
) -> dict:
    """Encode already-decoded RGBA frames using the website-compatible layout."""
    if not frames:
        raise GifToVtfError("至少需要一帧图片")
    if len(frames) > MAX_FRAMES:
        raise GifToVtfError(f"最多支持 {MAX_FRAMES} 帧，当前为 {len(frames)} 帧")
    template_path = Path(template).resolve() if template else None
    header, width, height = _template_header(template_path)
    prepared = [_fit_frame(frame, width, height) for frame in frames]
    image_data = b"".join(_encode_dxt1(frame) for frame in prepared)
    struct.pack_into("<HH", header, 16, width, height)
    struct.pack_into("<H", header, 24, len(prepared))
    output_path = Path(output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(bytes(header) + image_data)
    return {
        "output": str(output_path),
        "width": width,
        "height": height,
        "frames": len(prepared),
        "format": "DXT1",
        "bytes": output_path.stat().st_size,
    }


def encode_frames_to_vtf_bytes(
    frames: list,
    template: str | Path | None = None,
) -> bytes:
    """Return website-compatible VTF bytes for already-decoded frames."""
    if not frames:
        raise GifToVtfError("至少需要一帧图片")
    if len(frames) > MAX_FRAMES:
        raise GifToVtfError(f"最多支持 {MAX_FRAMES} 帧，当前为 {len(frames)} 帧")
    template_path = Path(template).resolve() if template else None
    header, width, height = _template_header(template_path)
    prepared = [_fit_frame(frame, width, height) for frame in frames]
    image_data = b"".join(_encode_dxt1(frame) for frame in prepared)
    struct.pack_into("<HH", header, 16, width, height)
    struct.pack_into("<H", header, 24, len(prepared))
    return bytes(header) + image_data


def convert_gif_to_vtf(
    source: str | Path,
    output: str | Path,
    template: str | Path | None = None,
) -> dict:
    """Convert every GIF frame into one multi-frame DXT1 VTF."""
    try:
        from PIL import Image
    except ImportError as error:
        raise GifToVtfError("需要安装 Pillow：python -m pip install Pillow") from error

    source_path = Path(source).resolve()
    output_path = Path(output).resolve()
    template_path = Path(template).resolve() if template else None
    if not source_path.is_file():
        raise GifToVtfError(f"找不到 GIF 文件：{source_path}")
    if source_path.suffix.casefold() != ".gif":
        raise GifToVtfError("输入文件必须是 GIF")

    with Image.open(source_path) as image:
        frame_count = max(1, int(getattr(image, "n_frames", 1)))
        if frame_count > MAX_FRAMES:
            raise GifToVtfError(f"GIF 最多支持 {MAX_FRAMES} 帧，当前为 {frame_count} 帧")
        frames = []
        for frame_index in range(frame_count):
            image.seek(frame_index)
            frames.append(image.convert("RGBA").copy())

    result = encode_frames_to_vtf(frames, output_path, template_path)
    result["source"] = str(source_path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="将 GIF 转换为 L4D2 动态喷漆 VTF")
    parser.add_argument("source", type=Path, help="输入 GIF 文件")
    parser.add_argument("output", type=Path, help="输出 VTF 文件")
    parser.add_argument("--template", type=Path, help="可选：使用已验证的 spray (1).vtf 作为格式模板")
    args = parser.parse_args()
    try:
        result = convert_gif_to_vtf(args.source, args.output, args.template)
    except GifToVtfError as error:
        parser.error(str(error))
    print(
        f"已生成：{result['output']} "
        f"({result['width']}x{result['height']}，{result['frames']} 帧，{result['format']}，{result['bytes']} 字节)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
