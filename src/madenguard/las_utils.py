from __future__ import annotations

import math
import struct
import zipfile
from math import ceil
from pathlib import Path
from typing import Iterator


LAS_HEADER_MIN_BYTES = 227


def read_las_header(path: Path) -> dict[str, object]:
    with path.open("rb") as handle:
        header = handle.read(375)
    if len(header) < LAS_HEADER_MIN_BYTES or header[:4] != b"LASF":
        raise ValueError(f"Not a LAS file or unsupported header: {path}")

    version_major = header[24]
    version_minor = header[25]
    header_size = struct.unpack_from("<H", header, 94)[0]
    offset_to_points = struct.unpack_from("<I", header, 96)[0]
    point_format = header[104] & 0x3F
    record_length = struct.unpack_from("<H", header, 105)[0]
    legacy_point_count = struct.unpack_from("<I", header, 107)[0]
    scales = struct.unpack_from("<ddd", header, 131)
    offsets = struct.unpack_from("<ddd", header, 155)
    max_x, min_x, max_y, min_y, max_z, min_z = struct.unpack_from("<dddddd", header, 179)
    return {
        "signature": "LASF",
        "version": f"{version_major}.{version_minor}",
        "header_size": header_size,
        "offset_to_points": offset_to_points,
        "point_format": point_format,
        "record_length": record_length,
        "point_count": legacy_point_count,
        "scales": list(scales),
        "offsets": list(offsets),
        "mins": [min_x, min_y, min_z],
        "maxs": [max_x, max_y, max_z],
    }


def _decode_xyz(record: bytes, scales: list[float], offsets: list[float]) -> tuple[float, float, float]:
    xi, yi, zi = struct.unpack_from("<iii", record, 0)
    return (
        xi * scales[0] + offsets[0],
        yi * scales[1] + offsets[1],
        zi * scales[2] + offsets[2],
    )


def iter_las_points_stream(path: Path, max_points: int | None = None, batch_records: int = 250_000) -> Iterator[tuple[float, float, float]]:
    header = read_las_header(path)
    point_count = int(header["point_count"])
    record_length = int(header["record_length"])
    offset = int(header["offset_to_points"])
    scales = list(header["scales"])
    offsets = list(header["offsets"])
    target = min(point_count, max_points) if max_points else point_count

    yielded = 0
    with path.open("rb") as handle:
        handle.seek(offset)
        while yielded < target:
            to_read = min(batch_records, target - yielded)
            data = handle.read(to_read * record_length)
            if not data:
                break
            records = len(data) // record_length
            for i in range(records):
                start = i * record_length
                yield _decode_xyz(data[start : start + record_length], scales, offsets)
            yielded += records


def systematic_las_sample(path: Path, target_points: int) -> tuple[list[tuple[float, float, float]], dict[str, object]]:
    """Read a distributed sample with few seek operations.

    The old one-record-per-seek strategy is safe but slow on USB/NTFS media.
    This version reads small contiguous windows spread across the file, so it
    still avoids loading the full LAS while keeping flash-drive access practical.
    """
    header = read_las_header(path)
    total = int(header["point_count"])
    record_length = int(header["record_length"])
    offset = int(header["offset_to_points"])
    scales = list(header["scales"])
    offsets = list(header["offsets"])
    actual = min(target_points, total)
    if actual <= 0:
        return [], header
    window_count = min(100, actual)
    records_per_window = max(1, ceil(actual / window_count))
    window_count = ceil(actual / records_per_window)
    last_start = max(0, total - records_per_window)
    points: list[tuple[float, float, float]] = []
    with path.open("rb") as handle:
        for window_idx in range(window_count):
            start_idx = int(round(window_idx * last_start / max(1, window_count - 1)))
            handle.seek(offset + start_idx * record_length)
            data = handle.read(records_per_window * record_length)
            records = len(data) // record_length
            for record_idx in range(records):
                if len(points) >= actual:
                    break
                start = record_idx * record_length
                points.append(_decode_xyz(data[start : start + record_length], scales, offsets))
    meta = dict(header)
    meta.update({
        "sampled_point_count": len(points),
        "sampling_method": f"windowed_distributed_sample_{window_count}_windows_{records_per_window}_records_each",
    })
    return points, meta


def _npy_header(shape: tuple[int, int]) -> bytes:
    header = "{'descr': '<f4', 'fortran_order': False, 'shape': " + repr(shape) + ", }"
    magic = b"\x93NUMPY\x01\x00"
    pad_len = 16 - ((len(magic) + 2 + len(header) + 1) % 16)
    full_header = (header + " " * pad_len + "\n").encode("latin1")
    return magic + struct.pack("<H", len(full_header)) + full_header


def write_points_npz(path: Path, points: list[tuple[float, float, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = bytearray()
    for x, y, z in points:
        raw.extend(struct.pack("<fff", float(x), float(y), float(z)))
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("points.npy", _npy_header((len(points), 3)) + bytes(raw))


def read_points_npz(path: Path, limit: int | None = None) -> list[tuple[float, float, float]]:
    with zipfile.ZipFile(path, "r") as archive:
        data = archive.read("points.npy")
    if not data.startswith(b"\x93NUMPY"):
        raise ValueError(f"Unsupported npy payload in {path}")
    major = data[6]
    if major != 1:
        raise ValueError("Only npy v1.0 is supported by this lightweight reader")
    header_len = struct.unpack_from("<H", data, 8)[0]
    start = 10 + header_len
    count = (len(data) - start) // 12
    if limit is not None:
        count = min(count, limit)
    points: list[tuple[float, float, float]] = []
    for idx in range(count):
        base = start + idx * 12
        points.append(struct.unpack_from("<fff", data, base))
    return points


def point_bounds(points: list[tuple[float, float, float]]) -> dict[str, list[float]]:
    if not points:
        return {"mins": [0.0, 0.0, 0.0], "maxs": [0.0, 0.0, 0.0]}
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return {"mins": [min(xs), min(ys), min(zs)], "maxs": [max(xs), max(ys), max(zs)]}


def distance_xy(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])
