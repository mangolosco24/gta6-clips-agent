#!/usr/bin/env python3
"""Quality checks on a rendered Short (and on its source cut). Run automatically by agent.py;
a Short that fails is never scheduled.

  python qa.py output/<slug>/short_<slug>.mp4 [--expected 23.5]

Checks: audio and video both present, same duration (within 0.1 s) and starting together,
no timestamp jumps (the Kick bug: video froze while audio went on), constant 30 fps frame count,
1080x1920 H.264 + AAC.
"""
import argparse
import json
import subprocess
import sys

MAX_DRIFT = 0.10   # s, audio vs video duration / start
MAX_GAP = 0.10     # s, jump between consecutive packets


def _probe(path, args):
    r = subprocess.run(["ffprobe", "-v", "error", *args, "-of", "json", path],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def _packet_times(path, sel):
    data = _probe(path, ["-select_streams", sel, "-show_entries", "packet=pts_time,duration_time"])
    out = []
    for p in data.get("packets", []):
        try:
            out.append((float(p["pts_time"]), float(p.get("duration_time") or 0)))
        except (KeyError, ValueError):
            continue
    return sorted(out)


def gaps(path, sel):
    """Jumps bigger than MAX_GAP between consecutive packet timestamps: [(time, jump)].
    Uses the raw distance between timestamps: a muxer can 'cover' a jump by giving the frame
    before it a 2 s duration, which on screen is exactly a 2 s freeze."""
    pk = [t for t, _ in _packet_times(path, sel)]
    return [(round(a, 3), round(b - a, 3)) for a, b in zip(pk, pk[1:]) if b - a > MAX_GAP]


def check(path, expected=None, final=True):
    """Return a list of problems (empty = OK)."""
    problems = []
    info = _probe(path, ["-show_entries",
                         "stream=codec_type,codec_name,width,height,start_time,duration,nb_frames"])
    streams = {s["codec_type"]: s for s in info.get("streams", [])}
    v, a = streams.get("video"), streams.get("audio")
    if not v or not a:
        return [f"missing {'video' if not v else 'audio'} stream"]
    vd, ad = float(v.get("duration") or 0), float(a.get("duration") or 0)
    vs, as_ = float(v.get("start_time") or 0), float(a.get("start_time") or 0)
    if abs(vd - ad) > MAX_DRIFT:
        problems.append(f"audio/video length differ: video {vd:.2f}s, audio {ad:.2f}s")
    if abs(vs - as_) > MAX_DRIFT:
        problems.append(f"audio/video start differ: video {vs:.3f}s, audio {as_:.3f}s")
    if expected and abs(vd - expected) > 0.25:
        problems.append(f"duration {vd:.2f}s, expected {expected:.2f}s")
    for sel, name in (("v:0", "video"), ("a:0", "audio")):
        g = gaps(path, sel)
        if g:
            problems.append(f"{name} timestamp jumps (freeze/desync): {g[:3]}")
    if final:
        if (v.get("width"), v.get("height")) != (1080, 1920):
            problems.append(f"size {v.get('width')}x{v.get('height')}, expected 1080x1920")
        if v.get("codec_name") != "h264" or a.get("codec_name") != "aac":
            problems.append(f"codecs {v.get('codec_name')}/{a.get('codec_name')}, expected h264/aac")
        n = int(v.get("nb_frames") or 0)
        if n and abs(n - vd * 30) > 2:
            problems.append(f"{n} frames for {vd:.2f}s: not a constant 30 fps")
    return problems


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--expected", type=float)
    ap.add_argument("--source", action="store_true", help="source cut: skip size/codec/fps checks")
    a = ap.parse_args()
    p = check(a.video, a.expected, final=not a.source)
    print("QA OK" if not p else "QA FAILED:\n- " + "\n- ".join(p))
    sys.exit(1 if p else 0)
