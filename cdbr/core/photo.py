"""Puzzle photograph input inspection."""

from __future__ import annotations

from enum import Enum
from pathlib import Path


class PhotoFormat(Enum):
    """Image containers accepted at the command-line boundary."""

    PNG = "PNG"
    JPEG = "JPEG"
    HEIF = "HEIF"
    TIFF = "TIFF"
    WEBP = "WebP"
    UNKNOWN = "unknown"

    @property
    def display_name(self) -> str:
        return self.value


def detect_photo_format(path: Path) -> PhotoFormat:
    """Identify a common photo container from its signature, not its suffix."""

    with path.open("rb") as stream:
        header = stream.read(32)

    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return PhotoFormat.PNG
    if header.startswith(b"\xff\xd8\xff"):
        return PhotoFormat.JPEG
    if header.startswith((b"II*\x00", b"MM\x00*")):
        return PhotoFormat.TIFF
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return PhotoFormat.WEBP
    if header[4:8] == b"ftyp" and header[8:12] in {
        b"avif",
        b"heic",
        b"heix",
        b"hevc",
        b"hevx",
        b"mif1",
        b"msf1",
    }:
        return PhotoFormat.HEIF
    return PhotoFormat.UNKNOWN
