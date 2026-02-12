import mmap
import os
import struct
import time
from dataclasses import dataclass
from typing import Optional, List

from PIL import Image
import io

# ---------- ODSH v2 Ring Buffer Protocol ----------
#
# Global Header (64 bytes):
#   [0:4]   magic    = "ODSH"
#   [4:8]   version  = 2
#   [8:12]  num_slots
#   [12:16] slot_size           (SLOT_HEADER_SIZE + slot_data_capacity)
#   [16:24] write_seq (uint64)  monotonically increasing
#   [24:28] slot_data_capacity  max payload bytes per slot
#   [28:64] reserved
#
# Per-Slot Header (40 bytes):
#   [0:4]   magic    = "ODSF"
#   [4:8]   width
#   [8:12]  height
#   [12:16] format   (1=RGB, 2=RGBA, 3=GRAY)
#   [16:20] data_len
#   [20:24] flags    (0=empty, 1=ready, 2=writing)
#   [24:32] seq      (uint64)
#   [32:40] timestamp_ns (uint64)
#
# Slot Payload:
#   [40 .. 40+data_len)  raw pixel data

MAGIC = b"ODSH"
SLOT_MAGIC = b"ODSF"

GLOBAL_HEADER_SIZE = 64
# magic(4s) + version(I) + num_slots(I) + slot_size(I) + write_seq(Q) + slot_capacity(I) = 28 bytes
GLOBAL_HEADER_STRUCT = struct.Struct("<4sIIIQI")

SLOT_HEADER_SIZE = 40
# magic(4s) + width(I) + height(I) + format(I) + data_len(I) + flags(I) + seq(Q) + timestamp_ns(Q)
SLOT_HEADER_STRUCT = struct.Struct("<4sIIIIIQQ")

FORMAT_RGB = 1
FORMAT_RGBA = 2
FORMAT_GRAY = 3

SLOT_FLAG_EMPTY = 0
SLOT_FLAG_READY = 1
SLOT_FLAG_WRITING = 2

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
    """Reads frames from an ODSH v2 ring buffer in shared memory."""

    def __init__(self, path: str = "/dev/shm/opendeploy_frames"):
        self.path = path
        self._mmap: Optional[mmap.mmap] = None
        self._num_slots: int = 0
        self._slot_size: int = 0
        self._slot_capacity: int = 0

    @classmethod
    def from_env(cls) -> "SharedMemoryFrameReader":
        path = os.getenv("OPENDEPLOY_SHM_PATH", "/dev/shm/opendeploy_frames")
        return cls(path=path)

    def open(self) -> bool:
        if self._mmap is not None:
            return True
        if not os.path.exists(self.path):
            return False
        file_size = os.path.getsize(self.path)
        if file_size < GLOBAL_HEADER_SIZE:
            return False
        fd = os.open(self.path, os.O_RDONLY)
        try:
            self._mmap = mmap.mmap(fd, file_size, access=mmap.ACCESS_READ)
        finally:
            os.close(fd)

        # Parse global header to learn ring buffer layout
        raw = self._mmap[: GLOBAL_HEADER_STRUCT.size]
        magic, version, num_slots, slot_size, _, slot_capacity = (
            GLOBAL_HEADER_STRUCT.unpack(raw)
        )
        if magic != MAGIC or version != 2:
            self._mmap.close()
            self._mmap = None
            return False
        self._num_slots = num_slots
        self._slot_size = slot_size
        self._slot_capacity = slot_capacity
        return True

    def close(self) -> None:
        if self._mmap is not None:
            self._mmap.close()
            self._mmap = None

    # ---- internal helpers ----

    def _read_write_seq(self) -> int:
        """Read the current global write sequence number (offset 16, uint64 LE)."""
        return struct.unpack_from("<Q", self._mmap, 16)[0]

    def _slot_offset(self, index: int) -> int:
        return GLOBAL_HEADER_SIZE + index * self._slot_size

    def _read_slot(self, slot_index: int) -> Optional[SharedFrame]:
        """Read a single slot. Returns None if the slot is invalid or torn."""
        off = self._slot_offset(slot_index)
        raw = self._mmap[off : off + SLOT_HEADER_SIZE]
        magic, width, height, fmt, data_len, flags, seq, timestamp_ns = (
            SLOT_HEADER_STRUCT.unpack(raw)
        )

        if magic != SLOT_MAGIC or flags != SLOT_FLAG_READY:
            return None
        if width <= 0 or height <= 0:
            return None
        if width > MAX_FRAME_WIDTH or height > MAX_FRAME_HEIGHT:
            return None
        if fmt not in (FORMAT_RGB, FORMAT_RGBA, FORMAT_GRAY):
            return None

        channels = 3 if fmt == FORMAT_RGB else 4 if fmt == FORMAT_RGBA else 1
        expected = width * height * channels
        if data_len < expected or data_len > MAX_FRAME_BYTES:
            return None
        if data_len > self._slot_capacity:
            return None

        payload_start = off + SLOT_HEADER_SIZE
        payload = self._mmap[payload_start : payload_start + data_len]

        # Double-read consistency: re-check header after reading payload
        raw_check = self._mmap[off : off + SLOT_HEADER_SIZE]
        _, _, _, _, data_len_ck, flags_ck, seq_ck, _ = SLOT_HEADER_STRUCT.unpack(
            raw_check
        )
        if seq != seq_ck or data_len != data_len_ck or flags_ck != SLOT_FLAG_READY:
            return None

        return SharedFrame(
            width=width,
            height=height,
            fmt=fmt,
            data=bytes(payload),
            seq=seq,
            timestamp_ns=timestamp_ns,
        )

    # ---- public API ----

    def read_latest(self, attempts: int = 3) -> Optional[SharedFrame]:
        """Read the most recently written frame from the ring buffer."""
        if not self.open():
            return None
        for _ in range(max(1, attempts)):
            write_seq = self._read_write_seq()
            if write_seq == 0:
                time.sleep(0.005)
                continue
            slot_index = (write_seq - 1) % self._num_slots
            frame = self._read_slot(slot_index)
            if frame is not None:
                return frame
            time.sleep(0.002)
        return None

    def read_window(self, n: int = 64) -> List[SharedFrame]:
        """Read the last *n* frames, ordered oldest → newest.

        Skips any slots that were overwritten mid-read (torn) or that are
        older than the current ring buffer horizon.
        """
        if not self.open():
            return []
        write_seq = self._read_write_seq()
        if write_seq == 0:
            return []

        n = min(n, self._num_slots, write_seq)
        start_seq = write_seq - n + 1

        frames: List[SharedFrame] = []
        for seq in range(start_seq, write_seq + 1):
            slot_index = (seq - 1) % self._num_slots
            frame = self._read_slot(slot_index)
            # Verify the slot still holds the frame we expect (not overwritten)
            if frame is not None and frame.seq == seq:
                frames.append(frame)
        return frames
