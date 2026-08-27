import io
import struct
import tempfile
import unittest
from pathlib import Path

from gif_to_vtf import convert_gif_to_vtf
from spray_manager import spray_preview_frame


class GifToVtfTests(unittest.TestCase):
    def test_preview_can_extract_a_selected_imported_gif_frame(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            imported = root / "tudou mod manger" / "imported_sprays"
            imported.mkdir(parents=True)
            source = imported / "animated.gif"
            buffer = io.BytesIO()
            red = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
            blue = Image.new("RGBA", (4, 4), (0, 0, 255, 255))
            red.save(buffer, format="GIF", save_all=True, append_images=[blue], loop=0)
            source.write_bytes(buffer.getvalue())

            preview = spray_preview_frame(
                root,
                {
                    "sourceType": "imported",
                    "importedPath": "tudou mod manger/imported_sprays/animated.gif",
                },
                1,
            )

            with Image.open(io.BytesIO(preview)) as image:
                self.assertEqual(image.convert("RGBA").getpixel((0, 0))[:3], (0, 0, 255))

    def test_converts_all_gif_frames_to_website_layout(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.gif"
            output = root / "output.vtf"
            buffer = io.BytesIO()
            red = Image.new("RGBA", (20, 20), (255, 0, 0, 255))
            blue = Image.new("RGBA", (20, 20), (0, 0, 255, 255))
            red.save(buffer, format="GIF", save_all=True, append_images=[blue], loop=0)
            source.write_bytes(buffer.getvalue())

            result = convert_gif_to_vtf(source, output)
            data = output.read_bytes()

            self.assertEqual(result["frames"], 2)
            self.assertEqual(struct.unpack_from("<II", data, 4), (7, 1))
            self.assertEqual(struct.unpack_from("<I", data, 12)[0], 64)
            self.assertEqual(struct.unpack_from("<HH", data, 16), (252, 256))
            self.assertEqual(struct.unpack_from("<H", data, 24)[0], 2)
            self.assertEqual(struct.unpack_from("<I", data, 52)[0], 13)
            self.assertEqual(data[56], 1)
            self.assertEqual(len(data), 64 + 2 * 63 * 64 * 8)


if __name__ == "__main__":
    unittest.main()
