import mmap
import os
import struct
import time
from dataclasses import dataclass
from typing import Optional

from PIL import Image
import io

MAGIC = b"ODSH"
HEADER_STRUCT = struct.Struct("<4sIIIIIQQ")
HEADER_SIZE = HEADER_STRUCT.size
FORMAT_RGB = 1
FORMAT_RGBA = 2
FORMAT_GRAY = 3

MAX_FRAME_WIDTH = int(os.getenv("OPENDEPLOY_MAX_FRAME_WIDTH", "1920"))
MAX_FRAME_HEIGHT = int(os.getenv("OPENDEPLOY_MAX_FRAME_HEIGHT", "1080"))
MAX_FRAME_BYTES = int(os.getenv("OPENDEPLOY_MAX_FRAME_BYTES", str(4 * 1920 * 1080)))


@dataclass
class SharedFrame:
    width: int
    height: int
    fmt: int
    data: bytes
    seq: int
    timestamp_ns: int

    def to_image_bytes(self, image_format: str = "PNG") -> bytes:
        if self.fmt == FORMAT_RGB:
            mode = "RGB"
        elif self.fmt == FORMAT_RGBA:
            mode = "RGBA"
        elif self.fmt == FORMAT_GRAY:
            mode = "L"
        else:
            raise ValueError(f"Unsupported frame format: {self.fmt}")

        image = Image.frombytes(mode, (self.width, self.height), self.data)
        if mode == "RGBA":
            image = image.convert("RGB")

        buffer = io.BytesIO()
        image.save(buffer, format=image_format)
        return buffer.getvalue()


class SharedMemoryFrameReader:
    def __init__(self, path: str = "/dev/shm/opendeploy_frames", size: int = 16 * 1024 * 1024):
        self.path = path
        self.size = size
        self._mmap: Optional[mmap.mmap] = None

    @classmethod
    def from_env(cls) -> "SharedMemoryFrameReader":
        path = os.getenv("OPENDEPLOY_SHM_PATH", "/dev/shm/opendeploy_frames")
        size = int(os.getenv("OPENDEPLOY_SHM_SIZE", str(16 * 1024 * 1024)))
        return cls(path=path, size=size)

    def open(self) -> bool:
        if self._mmap is not None:
            return True
        if not os.path.exists(self.path):
            return False
        fd = os.open(self.path, os.O_RDONLY)
        try:
            self._mmap = mmap.mmap(fd, self.size, access=mmap.ACCESS_READ)
        finally:
            os.close(fd)
        return True

    def close(self) -> None:
        if self._mmap is not None:
            self._mmap.close()
            self._mmap = None

    def read_latest(self, attempts: int = 3) -> Optional[SharedFrame]:
        if not self.open():
            return None
        for _ in range(max(1, attempts)):
            header = self._mmap[:HEADER_SIZE]
            magic, version, width, height, fmt, data_len, seq, timestamp_ns = HEADER_STRUCT.unpack(header)
            if magic != MAGIC or data_len == 0:
                time.sleep(0.005)
                continue

            if width <= 0 or height <= 0:
                time.sleep(0.002)
                continue
            if width > MAX_FRAME_WIDTH or height > MAX_FRAME_HEIGHT:
                time.sleep(0.002)
                continue
            if fmt not in (FORMAT_RGB, FORMAT_RGBA, FORMAT_GRAY):
                time.sleep(0.002)
                continue

            channels = 3 if fmt == FORMAT_RGB else 4 if fmt == FORMAT_RGBA else 1
            expected_len = width * height * channels
            if data_len < expected_len or data_len > MAX_FRAME_BYTES:
                time.sleep(0.002)
                continue
            if data_len > self.size - HEADER_SIZE:
                time.sleep(0.002)
                continue

            payload = self._mmap[HEADER_SIZE:HEADER_SIZE + data_len]
            header_check = self._mmap[:HEADER_SIZE]
            _, _, _, _, _, data_len_check, seq_check, _ = HEADER_STRUCT.unpack(header_check)
            if seq != seq_check or data_len != data_len_check:
                time.sleep(0.002)
                continue

            return SharedFrame(
                width=width,
                height=height,
                fmt=fmt,
                data=bytes(payload),
                seq=seq,
                timestamp_ns=timestamp_ns,
            )
        return None
