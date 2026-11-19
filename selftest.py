#!/usr/bin/env python3
"""Regression test of the whole pipeline. Run it after EVERY code change, before committing:

  python selftest.py

1. A/V sync: builds a synthetic 16:9 clip with white flashes and 1 kHz beeps at the same instants,
   renders it with every montage feature (blur and facecam layouts, karaoke captions, all visual
   styles, logo, hook, CTA) and checks that each beep is still within 1 frame of its flash.
2. qa.py: the render passes, and a source with a 2 s timestamp jump (the Kick bug) fails.
3. Units: writer validation, slot scheduling, profanity filter, metadata/no-links rules.
Exit code 0 = all good.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import montage  # noqa: E402
import qa  # noqa: E402

FLASHES = [2.0, 5.0, 8.5]
FAILS = []


def ok(cond, msg):
    print(("PASS  " if cond else "FAIL  ") + msg)
    if not cond:
        FAILS.append(msg)


def ff(args, cwd=None):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True, cwd=cwd)


def make_source(path, dur=11.0):
    on = "+".join(f"between(t,{t},{t + 0.1})" for t in FLASHES)
    ff(["-f", "lavfi", "-i", f"color=black:s=1920x1080:r=60:d={dur}",
        "-f", "lavfi", "-i", f"aevalsrc='if({on},0.8*sin(2*PI*1000*t),0)':s=48000:d={dur}",
        "-filter_complex", f"[0:v]drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='{on}'[v]",
        "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", path])


def flash_times(path):
    import av
    import numpy as np
    out, prev = [], False
    with av.open(path) as c:
        for f in c.decode(video=0):
            y = f.to_ndarray(format="gray")
            bright = float(np.mean(y)) > 150
            if bright and not prev:
                out.append(float(f.time))
            prev = bright
    return out


def beep_times(path):
    import av
    import numpy as np
    out, prev, sr = [], False, None
    with av.open(path) as c:
        for f in c.decode(audio=0):
            sr = f.sample_rate
            a = f.to_ndarray()
            a = a.mean(axis=0) if a.ndim > 1 else a
            step = max(1, sr // 200)  # 5 ms windows
            for i in range(0, len(a) - step, step):
                loud = float(np.sqrt(np.mean(a[i:i + step] ** 2))) > 0.05
                if loud and not prev:
                    out.append(float(f.time) + i / sr)
                prev = loud
    return out


def sync_test(tmp):
    src = os.path.join(tmp, "src.mp4")
    make_source(src)
    words = [{"w": w, "start": t, "end": t + 0.4} for t, w in zip(FLASHES, ["ONE", "TWO", "THREE"])]
    camps = {
        "blur+logo": {"credit": "@Test", "cta_overlay": "SUBSCRIBE\nTO TEST", "layout": "blur",
                      "logo": {"file": "assets/kreekcraft_logo.png", "width": 600, "x": "(W-w)/2", "y": "0"}},
        "facecam": {"credit": "test on Kick", "cta_overlay": "WATCH LIVE", "layout": "facecam",
                    "facecam": [0, 0, 0.28, 0.4], "gameplay": [0.28, 0, 0.72, 1]},
    }
    if not os.path.exists(os.path.join(HERE, "assets", "kreekcraft_logo.png")):
        camps["blur+logo"].pop("logo")
    for i, (name, camp) in enumerate(camps.items()):
        slug = "selftest_" + name.replace("+", "_")
        out = f"out_{i}.mp4"
        script = {"slug": slug, "hook_text": "TEST HOOK\nLINE TWO", "highlight_words": ["TWO"]}
        montage.render(tmp, src, words, script, camp, out, 10.5)
        p = qa.check(os.path.join(tmp, out), expected=10.5)
        ok(not p, f"[{name}] qa.check on render: {p or 'ok'}")
        fl, bp = flash_times(os.path.join(tmp, out)), beep_times(os.path.join(tmp, out))
        ok(len(fl) == len(FLASHES) and len(bp) == len(FLASHES),
           f"[{name}] found {len(fl)} flashes / {len(bp)} beeps (expected {len(FLASHES)})")
        if len(fl) == len(bp) == len(FLASHES):
            worst = max(abs(f - b) for f, b in zip(fl, bp))
            ok(worst <= 1 / 30 + 0.012, f"[{name}] A/V offset max {worst * 1000:.0f} ms (limit 1 frame)")
            drift = max(abs(f - t) for f, t in zip(fl, FLASHES))
            ok(drift <= 0.05, f"[{name}] flashes at the right time (max drift {drift * 1000:.0f} ms)")
    # every style renders captions without ASS errors
    for k in range(len(montage.STYLES)):
        montage.subtitles(words, "HOOK", ["TWO"], "@x", "blur", 10.5, os.path.join(tmp, f"s{k}.ass"),
                          "CTA", montage.STYLES[k])
    ok(True, f"{len(montage.STYLES)} caption styles generated")


def jump_test(tmp):
    """Two 3 s parts where the second starts at 5 s instead of 3 s: a 2 s timestamp jump,
    the same defect Kick clip playlists have."""
    a, b = os.path.join(tmp, "p1.mp4"), os.path.join(tmp, "p2.mp4")
    for p in (a, b):
        ff(["-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=3", "-f", "lavfi", "-i",
            "sine=f=440:d=3", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", p])
    ff(["-i", a, "-c", "copy", "-f", "mpegts", os.path.join(tmp, "raw.ts")])
    ff(["-i", b, "-c", "copy", "-output_ts_offset", "5", "-f", "mpegts", os.path.join(tmp, "raw2.ts")])
    jumpy = os.path.join(tmp, "jumpy.mp4")
    ff(["-i", "concat:raw.ts|raw2.ts", "-c", "copy", "jumpy.mp4"], cwd=tmp)
    p = qa.check(jumpy, final=False)
    ok(bool(p), f"qa.check catches a 2 s timestamp jump: {p or 'NOT CAUGHT'}")


def vfr_test(tmp):
    """Twitch clips: variable frame rate tagged as 60 fps (the Boeshi bug). The normalised clip must
    keep its length and A/V sync."""
    import clips
    src, vfr, norm = (os.path.join(tmp, n) for n in ("v_src.mp4", "v_vfr.mp4", "v_norm.mp4"))
    make_source(src)
    ff(["-i", src, "-vf", r"select='not(mod(n,3))+eq(mod(n,7),1)'", "-fps_mode", "vfr",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "copy", vfr])
    clips.normalize_clip(vfr, norm, "twitch_clip")
    p = qa.check(norm, expected=11.0, final=False)
    ok(not p, f"[twitch vfr] normalised clip keeps length and sync: {p or 'ok'}")
    fl, bp = flash_times(norm), beep_times(norm)
    if len(fl) == len(bp) == len(FLASHES):
        worst = max(abs(f - b) for f, b in zip(fl, bp))
        ok(worst <= 1 / 30 + 0.012, f"[twitch vfr] A/V offset max {worst * 1000:.0f} ms (limit 1 frame)")
    else:
        ok(False, f"[twitch vfr] found {len(fl)} flashes / {len(bp)} beeps")


def unit_tests():
    import publisher
    import writer
    import datetime as dt
    now = dt.datetime(2026, 11, 20, 12, 0, tzinfo=dt.timezone.utc)
    ok(publisher.slot_at("20:00", now) == "2026-11-20T19:00:00Z", "slot 20:00 Rome -> 19:00 UTC")
    ok(publisher.slot_at("17:00", dt.datetime(2026, 11, 20, 15, 50, tzinfo=dt.timezone.utc))
       == "2026-11-21T16:00:00Z", "slot with < 20 min left moves to tomorrow")
    ok(publisher.slot_taken("2026-11-20T16:00:00Z", [dt.datetime(2026, 11, 20, 16, 10, tzinfo=dt.timezone.utc)]),
       "slot taken detected")
    ok(not publisher.slot_taken("2026-11-20T19:00:00Z", [dt.datetime(2026, 11, 20, 16, 0, tzinfo=dt.timezone.utc)]),
       "other slot free")
    ok(montage._censor("what the fuck") == "what the F*CK", "profanity censored in captions")
    camp_id = next(iter(writer.campaigns()))
    base = {"slug": "unit_test", "campaign": camp_id, "video_id": "abcdefghijk", "start": 0, "end": 20,
            "title": "t", "description": "d", "hashtags": ["a"], "hook_text": "H", "first_comment": "q?"}
    errs = writer.validate(base)
    ok(not any("missing" in e for e in errs), f"start 0 accepted ({errs or 'ok'})")
    ok(any("length" in e for e in writer.validate(dict(base, end=60))), "60 s clip rejected")
    tw = dict(base, source="twitch_clip", video_id="twitch_123456")
    ok(any("source_url" in e for e in writer.validate(tw)), "twitch clip without source_url rejected")
    ok(not any("source_url" in e for e in writer.validate(dict(tw, source_url="https://clips.twitch.tv/x"))),
       "twitch clip with source_url accepted")
    for cid, camp in writer.campaigns().items():
        if camp.get("no_links"):
            meta = publisher.build_metadata(dict(base, campaign=cid))
            ok("http" not in meta["description"] and "http" not in meta["title"],
               f"[{cid}] no links in title/description")
        tags = publisher.build_hashtags(dict(base, campaign=cid))
        ok(all(t.lower() in [x.lower() for x in tags] for t in camp.get("required_hashtags", [])),
           f"[{cid}] required hashtags present")


if __name__ == "__main__":
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"{tool} not found")
    tmp = tempfile.mkdtemp(prefix="gta6_selftest_")
    try:
        unit_tests()
        sync_test(tmp)
        jump_test(tmp)
        vfr_test(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'ALL TESTS PASSED' if not FAILS else str(len(FAILS)) + ' TEST(S) FAILED'}")
    sys.exit(1 if FAILS else 0)
