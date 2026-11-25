#!/usr/bin/env python3
"""
Selectively download one time window of LiDAR scans from a remote ROS1 bag, without downloading the bag.

A ROS1 bag (v2.0) stores messages in chunks and keeps an index of every chunk (byte position, start and
end time, which topics it holds) at the end of the file. This tool uses HTTP range requests to read:

  1. the 4 KB bag header (gives the index position),
  2. the index at the tail (connection records + chunk-info records),
  3. only the chunks that overlap the requested time window AND contain the LiDAR topic.

Camera and IMU messages that share those chunks are discarded in memory. Nothing but the PCD files of the
window is written to disk, so a 2-4 GB bag costs a few hundred MB of transfer for a 30-60 s window.

Output: cloud_<sec>_<nsec>.pcd per scan (same naming and binary PCD layout as tools/extract_bag.py), plus
fetch_manifest.json recording the source file name, window, chunk count, bytes transferred and topic.

Usage:
    python tools/fetch_bag_window.py --url <direct-download-url-or-drive-file-id> --out <dir>
        [--topic auto] [--start-s 0] [--duration-s 30] [--list]

The URL is never written to the manifest (Drive share links are private to the person who was given them).
"""

import argparse
import bz2
import json
import struct
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_bag import _build_dtypes, _pcd_header  # noqa: E402  (same PCD writer as the local extractor)

OP_MSG, OP_BAG_HDR, OP_INDEX, OP_CHUNK, OP_CHUNK_INFO, OP_CONN = 0x02, 0x03, 0x04, 0x05, 0x06, 0x07
MAGIC = b"#ROSBAG V2.0\n"


def _drive_url(spec: str) -> str:
    if spec.startswith("http"):
        return spec
    return f"https://drive.usercontent.google.com/download?id={spec}&export=download&confirm=t"


class RangeReader:
    def __init__(self, url: str):
        self.url = url
        self.bytes_read = 0
        self.size = None

    def get(self, start: int, stop: int, tries: int = 5) -> bytes:
        """Bytes [start, stop)."""
        for attempt in range(tries):
            try:
                req = urllib.request.Request(self.url, headers={"Range": f"bytes={start}-{stop - 1}",
                                                                "User-Agent": "bag-window-fetch/1.0"})
                with urllib.request.urlopen(req, timeout=120) as r:
                    if r.status != 206:
                        raise IOError(f"server ignored the range request (HTTP {r.status})")
                    cr = r.headers.get("Content-Range", "")
                    if "/" in cr:
                        self.size = int(cr.rsplit("/", 1)[1])
                    data = r.read()
                if len(data) != stop - start:
                    raise IOError(f"short read {len(data)} of {stop - start}")
                self.bytes_read += len(data)
                return data
            except Exception as exc:  # network hiccups: retry with backoff
                if attempt == tries - 1:
                    raise
                print(f"  retry {attempt + 1} for bytes {start}-{stop}: {exc}", file=sys.stderr)
                time.sleep(2 * (attempt + 1))
        raise AssertionError


def _fields(header: bytes) -> dict:
    out, i = {}, 0
    while i < len(header):
        (n,) = struct.unpack_from("<I", header, i)
        i += 4
        k, _, v = header[i:i + n].partition(b"=")
        out[k.decode()] = v
        i += n
    return out


def _records(buf: bytes, start: int = 0):
    i = start
    while i + 4 <= len(buf):
        (hl,) = struct.unpack_from("<I", buf, i)
        if i + 4 + hl + 4 > len(buf):
            return
        hdr = _fields(buf[i + 4:i + 4 + hl])
        (dl,) = struct.unpack_from("<I", buf, i + 4 + hl)
        d0 = i + 8 + hl
        if d0 + dl > len(buf):
            return
        yield hdr, buf[d0:d0 + dl]
        i = d0 + dl


def _time(b: bytes) -> float:
    s, ns = struct.unpack("<II", b)
    return s + ns * 1e-9


def read_index(rr: RangeReader):
    head = rr.get(0, 8192)
    if not head.startswith(MAGIC):
        raise SystemExit("not a ROS1 v2.0 bag")
    hdr, _ = next(_records(head, len(MAGIC)))
    if hdr["op"][0] != OP_BAG_HDR:
        raise SystemExit("bag header record missing")
    index_pos = struct.unpack("<Q", hdr["index_pos"])[0]
    if index_pos == 0:
        raise SystemExit("bag is not indexed (index_pos = 0)")
    rr.get(0, 1)  # learn total size from Content-Range
    tail = rr.get(index_pos, rr.size)
    conns, chunks = {}, []
    for h, data in _records(tail):
        op = h["op"][0]
        if op == OP_CONN:
            cid = struct.unpack("<I", h["conn"])[0]
            meta = _fields(data)
            conns[cid] = {"topic": h["topic"].decode(), "type": meta.get("type", b"").decode()}
        elif op == OP_CHUNK_INFO:
            counts = {}
            for k in range(struct.unpack("<I", h["count"])[0]):
                c, n = struct.unpack_from("<II", data, 8 * k)
                counts[c] = n
            chunks.append({"pos": struct.unpack("<Q", h["chunk_pos"])[0], "t0": _time(h["start_time"]),
                           "t1": _time(h["end_time"]), "counts": counts})
    chunks.sort(key=lambda c: c["pos"])
    for k, c in enumerate(chunks):
        c["end"] = chunks[k + 1]["pos"] if k + 1 < len(chunks) else index_pos
    return conns, chunks


def _decompress(h: dict, data: bytes) -> bytes:
    comp = h["compression"].decode()
    if comp == "none":
        return data
    if comp == "bz2":
        return bz2.decompress(data)
    if comp == "lz4":
        import lz4.frame  # installed with rosbags
        return lz4.frame.decompress(data)
    raise SystemExit(f"unsupported chunk compression {comp}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--url", required=True, help="direct download URL, or a Google Drive file id")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--topic", default="auto", help="PointCloud2 topic; 'auto' picks the only PointCloud2 topic")
    ap.add_argument("--start-s", type=float, default=0.0, help="window start, seconds after the bag's first message")
    ap.add_argument("--start-unix", type=float, default=None,
                    help="window start as an absolute UNIX time (overrides --start-s), e.g. ground-truth start + offset")
    ap.add_argument("--duration-s", type=float, default=30.0)
    ap.add_argument("--list", action="store_true", help="only print topics, duration and size")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    from rosbags.typesys import Stores, get_typestore
    ts = get_typestore(Stores.ROS1_NOETIC)

    rr = RangeReader(_drive_url(args.url))
    conns, chunks = read_index(rr)
    t_bag0, t_bag1 = min(c["t0"] for c in chunks), max(c["t1"] for c in chunks)
    clouds = {cid: c for cid, c in conns.items() if c["type"].endswith("PointCloud2")}
    if args.list or not args.out:
        print(f"size {rr.size / 1e9:.2f} GB, {len(chunks)} chunks, duration {t_bag1 - t_bag0:.1f} s")
        for cid, c in sorted(conns.items()):
            n = sum(ch["counts"].get(cid, 0) for ch in chunks)
            print(f"  {c['topic']:45s} {c['type']:35s} {n} msgs")
        return 0

    if args.topic == "auto":
        if len({c["topic"] for c in clouds.values()}) != 1:
            raise SystemExit(f"several PointCloud2 topics, pass --topic: {[c['topic'] for c in clouds.values()]}")
        topic = next(iter(clouds.values()))["topic"]
    else:
        topic = args.topic
    cids = {cid for cid, c in conns.items() if c["topic"] == topic}
    if not cids:
        raise SystemExit(f"topic {topic} not in bag")
    if args.start_unix is not None:
        args.start_s = args.start_unix - t_bag0
    w0, w1 = t_bag0 + args.start_s, t_bag0 + args.start_s + args.duration_s
    sel = [c for c in chunks if c["t1"] >= w0 and c["t0"] <= w1 and any(c["counts"].get(i) for i in cids)]
    total = sum(c["end"] - c["pos"] for c in sel)
    print(f"bag {rr.size / 1e9:.2f} GB; window {args.start_s:.1f}-{args.start_s + args.duration_s:.1f} s "
          f"-> {len(sel)} of {len(chunks)} chunks, {total / 1e6:.0f} MB to transfer")

    args.out.mkdir(parents=True, exist_ok=True)
    msgtype = "sensor_msgs/msg/PointCloud2"
    written = []

    def fetch(c):
        return rr.get(c["pos"], c["end"])

    topic_bytes = {}  # serialized payload bytes and message count per topic inside the window (MEASURED data rate)
    t_start = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for k, raw in enumerate(pool.map(fetch, sel)):
            h, data = next(_records(raw))
            assert h["op"][0] == OP_CHUNK
            for mh, payload in _records(_decompress(h, data)):
                if mh["op"][0] != OP_MSG:
                    continue
                t_rec = _time(mh["time"])
                if not (w0 <= t_rec <= w1):
                    continue
                cid = struct.unpack("<I", mh["conn"])[0]
                tb = topic_bytes.setdefault(conns[cid]["topic"], [0, 0])
                tb[0] += len(payload)
                tb[1] += 1
                if cid not in cids:
                    continue
                msg = ts.deserialize_ros1(payload, msgtype)
                src, packed, order = _build_dtypes(msg.fields, msg.point_step)
                n = int(msg.width) * int(msg.height)
                arr = np.frombuffer(np.asarray(msg.data, dtype=np.uint8)[: n * int(msg.point_step)], dtype=src, count=n)
                rec = np.empty(n, dtype=packed)
                for name in order:
                    rec[name] = arr[name]
                st = msg.header.stamp
                name = f"cloud_{int(st.sec)}_{int(st.nanosec):09d}.pcd"
                (args.out / name).write_bytes(_pcd_header(order, packed, int(msg.width), int(msg.height)) + rec.tobytes())
                written.append(name)
            print(f"  chunk {k + 1}/{len(sel)}  {rr.bytes_read / 1e6:.0f} MB  {len(written)} scans", end="\r")
    print()
    span = min(w1, t_bag1) - max(w0, t_bag0)
    manifest = {
        "tool": "tools/fetch_bag_window.py",
        "bag_size_bytes": rr.size, "bytes_transferred": rr.bytes_read,
        "topic": topic, "window_s": [args.start_s, args.start_s + args.duration_s], "window_span_s": round(span, 3),
        "bag_time_span": [t_bag0, t_bag1], "chunks_fetched": len(sel), "chunks_total": len(chunks),
        "scans_written": len(written), "seconds": round(time.time() - t_start, 1),
        "topic_payload_in_window": {
            t: {"bytes": b, "messages": n, "mbit_per_s": round(8 * b / 1e6 / span, 2)}
            for t, (b, n) in sorted(topic_bytes.items())},
    }
    (args.out / "fetch_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {len(written)} scans; transferred {rr.bytes_read / 1e6:.0f} MB of {rr.size / 1e9:.2f} GB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
