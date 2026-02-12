"""Tests for the ODSH v2 ring buffer shared memory protocol."""

import os
import struct
import tempfile
import pytest

# Ensure project root is on sys.path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.shm_frames import (
    SharedMemoryFrameReader,
    SharedFrame,
    GLOBAL_HEADER_SIZE,
    GLOBAL_HEADER_STRUCT,
    SLOT_HEADER_SIZE,
    SLOT_HEADER_STRUCT,
    SLOT_FLAG_READY,
    FORMAT_RGB,
    FORMAT_RGBA,
    FORMAT_GRAY,
    MAGIC,
    SLOT_MAGIC,
)


def _make_ring_buffer(num_slots: int, slot_capacity: int) -> bytearray:
    """Create a valid ODSH v2 ring buffer in memory."""
    slot_size = SLOT_HEADER_SIZE + slot_capacity
    total = GLOBAL_HEADER_SIZE + num_slots * slot_size
    buf = bytearray(total)

    # Global header
    buf[0:4] = b"ODSH"
    struct.pack_into("<I", buf, 4, 2)  # version
    struct.pack_into("<I", buf, 8, num_slots)
    struct.pack_into("<I", buf, 12, slot_size)
    struct.pack_into("<Q", buf, 16, 0)  # write_seq
    struct.pack_into("<I", buf, 24, slot_capacity)
    return buf


def _write_frame(buf: bytearray, seq: int, num_slots: int, slot_capacity: int,
                  width: int, height: int, fmt: int, payload: bytes, ts_ns: int = 1000):
    """Write a single frame into the ring buffer at the correct slot."""
    slot_size = SLOT_HEADER_SIZE + slot_capacity
    slot_index = (seq - 1) % num_slots
    off = GLOBAL_HEADER_SIZE + slot_index * slot_size

    buf[off:off + 4] = b"ODSF"
    struct.pack_into("<I", buf, off + 4, width)
    struct.pack_into("<I", buf, off + 8, height)
    struct.pack_into("<I", buf, off + 12, fmt)
    struct.pack_into("<I", buf, off + 16, len(payload))
    struct.pack_into("<I", buf, off + 20, SLOT_FLAG_READY)
    struct.pack_into("<Q", buf, off + 24, seq)
    struct.pack_into("<Q", buf, off + 32, ts_ns)
    buf[off + SLOT_HEADER_SIZE: off + SLOT_HEADER_SIZE + len(payload)] = payload

    # Update global write_seq
    struct.pack_into("<Q", buf, 16, seq)


@pytest.fixture()
def shm_path(tmp_path):
    return str(tmp_path / "test_frames")


class TestRingBufferProtocol:
    """Verify the ring buffer binary protocol and reader behaviour."""

    def test_empty_buffer_returns_none(self, shm_path):
        num_slots, cap = 4, 256
        buf = _make_ring_buffer(num_slots, cap)
        with open(shm_path, "wb") as f:
            f.write(buf)

        reader = SharedMemoryFrameReader(path=shm_path)
        assert reader.read_latest(attempts=1) is None
        reader.close()

    def test_read_latest_single_frame(self, shm_path):
        num_slots, cap = 4, 256
        w, h = 2, 2
        payload = bytes([255, 0, 0] * (w * h))  # red pixels
        buf = _make_ring_buffer(num_slots, cap)
        _write_frame(buf, seq=1, num_slots=num_slots, slot_capacity=cap,
                      width=w, height=h, fmt=FORMAT_RGB, payload=payload, ts_ns=5000)
        with open(shm_path, "wb") as f:
            f.write(buf)

        reader = SharedMemoryFrameReader(path=shm_path)
        frame = reader.read_latest(attempts=1)
        assert frame is not None
        assert frame.width == w
        assert frame.height == h
        assert frame.fmt == FORMAT_RGB
        assert frame.seq == 1
        assert frame.timestamp_ns == 5000
        assert len(frame.data) == len(payload)
        reader.close()

    def test_read_latest_returns_most_recent(self, shm_path):
        num_slots, cap = 4, 256
        w, h = 2, 2
        buf = _make_ring_buffer(num_slots, cap)

        # Write 3 frames; latest should be seq=3
        for seq in range(1, 4):
            payload = bytes([seq * 10] * (w * h * 3))
            _write_frame(buf, seq=seq, num_slots=num_slots, slot_capacity=cap,
                          width=w, height=h, fmt=FORMAT_RGB, payload=payload, ts_ns=seq * 1000)
        with open(shm_path, "wb") as f:
            f.write(buf)

        reader = SharedMemoryFrameReader(path=shm_path)
        frame = reader.read_latest(attempts=1)
        assert frame is not None
        assert frame.seq == 3
        assert frame.data[0] == 30  # seq=3 → pixel value 30
        reader.close()

    def test_read_window_returns_ordered_frames(self, shm_path):
        num_slots, cap = 8, 64
        w, h = 2, 2
        buf = _make_ring_buffer(num_slots, cap)

        for seq in range(1, 6):  # 5 frames
            payload = bytes([seq] * (w * h * 3))
            _write_frame(buf, seq=seq, num_slots=num_slots, slot_capacity=cap,
                          width=w, height=h, fmt=FORMAT_RGB, payload=payload, ts_ns=seq * 1000)
        with open(shm_path, "wb") as f:
            f.write(buf)

        reader = SharedMemoryFrameReader(path=shm_path)
        frames = reader.read_window(n=5)
        assert len(frames) == 5
        # Verify oldest-to-newest order
        seqs = [f.seq for f in frames]
        assert seqs == [1, 2, 3, 4, 5]
        reader.close()

    def test_read_window_clamps_to_available(self, shm_path):
        num_slots, cap = 4, 64
        w, h = 1, 1
        buf = _make_ring_buffer(num_slots, cap)

        for seq in range(1, 3):  # only 2 frames
            _write_frame(buf, seq=seq, num_slots=num_slots, slot_capacity=cap,
                          width=w, height=h, fmt=FORMAT_RGB, payload=bytes(3), ts_ns=seq)
        with open(shm_path, "wb") as f:
            f.write(buf)

        reader = SharedMemoryFrameReader(path=shm_path)
        frames = reader.read_window(n=64)  # request more than exist
        assert len(frames) == 2
        reader.close()

    def test_ring_wraps_around(self, shm_path):
        num_slots, cap = 4, 64
        w, h = 1, 1
        buf = _make_ring_buffer(num_slots, cap)

        # Write 6 frames into 4 slots → slots 0,1 are overwritten
        for seq in range(1, 7):
            _write_frame(buf, seq=seq, num_slots=num_slots, slot_capacity=cap,
                          width=w, height=h, fmt=FORMAT_RGB, payload=bytes([seq] * 3),
                          ts_ns=seq * 100)
        with open(shm_path, "wb") as f:
            f.write(buf)

        reader = SharedMemoryFrameReader(path=shm_path)
        # Latest should be seq=6
        frame = reader.read_latest(attempts=1)
        assert frame is not None
        assert frame.seq == 6

        # Window of 4 should return the 4 most recent (seq 3,4,5,6)
        frames = reader.read_window(n=4)
        assert len(frames) == 4
        assert [f.seq for f in frames] == [3, 4, 5, 6]
        reader.close()

    def test_rgba_and_gray_formats(self, shm_path):
        num_slots, cap = 2, 256
        w, h = 2, 2
        buf = _make_ring_buffer(num_slots, cap)

        # RGBA frame
        rgba_payload = bytes([128] * (w * h * 4))
        _write_frame(buf, seq=1, num_slots=num_slots, slot_capacity=cap,
                      width=w, height=h, fmt=FORMAT_RGBA, payload=rgba_payload)

        # GRAY frame
        gray_payload = bytes([64] * (w * h * 1))
        _write_frame(buf, seq=2, num_slots=num_slots, slot_capacity=cap,
                      width=w, height=h, fmt=FORMAT_GRAY, payload=gray_payload)

        with open(shm_path, "wb") as f:
            f.write(buf)

        reader = SharedMemoryFrameReader(path=shm_path)
        frames = reader.read_window(n=2)
        assert len(frames) == 2
        assert frames[0].fmt == FORMAT_RGBA
        assert frames[1].fmt == FORMAT_GRAY
        reader.close()

    def test_shared_frame_to_image_bytes(self, shm_path):
        w, h = 4, 4
        payload = bytes([255, 0, 0] * (w * h))
        frame = SharedFrame(width=w, height=h, fmt=FORMAT_RGB,
                            data=payload, seq=1, timestamp_ns=0)
        png_bytes = frame.to_image_bytes("PNG")
        # PNG files start with the PNG signature
        assert png_bytes[:4] == b"\x89PNG"

    def test_version_mismatch_fails_open(self, shm_path):
        buf = _make_ring_buffer(4, 64)
        # Overwrite version to 99
        struct.pack_into("<I", buf, 4, 99)
        with open(shm_path, "wb") as f:
            f.write(buf)

        reader = SharedMemoryFrameReader(path=shm_path)
        assert reader.open() is False
        reader.close()

    def test_missing_file_returns_none(self):
        reader = SharedMemoryFrameReader(path="/tmp/nonexistent_shm_test_file")
        assert reader.read_latest(attempts=1) is None
        assert reader.read_window(n=4) == []
        reader.close()
