"""Tests for puzzle photograph input inspection."""

from pathlib import Path

import pytest

from cdbr.core.photo import PhotoFormat, detect_photo_format


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (b"\x89PNG\r\n\x1a\n", PhotoFormat.PNG),
        (b"\xff\xd8\xff\xe0", PhotoFormat.JPEG),
        (b"\x00\x00\x00\x18ftypheic", PhotoFormat.HEIF),
        (b"II*\x00", PhotoFormat.TIFF),
        (b"RIFF\x00\x00\x00\x00WEBP", PhotoFormat.WEBP),
        (b"not an image", PhotoFormat.UNKNOWN),
    ],
)
def test_detect_photo_format(tmp_path: Path, header: bytes, expected: PhotoFormat):
    photo = tmp_path / "misleading.extension"
    photo.write_bytes(header + bytes(32))

    assert detect_photo_format(photo) is expected
