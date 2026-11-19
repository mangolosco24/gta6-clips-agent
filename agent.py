#!/usr/bin/env python3
"""GTA 6 clips agent: script JSON (moment + packaging) -> finished vertical Short.

  python agent.py --script scripts/<slug>.json     # download section, transcribe, render
  python agent.py --resume output/<slug>           # re-render after editing output/<slug>/script.json
  python agent.py --frames output/<slug>           # extract check frames (frame_1..5.jpg + src_frame.jpg)

Changing start/end in script.json and --resume downloads the section again.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import montage  # noqa: E402
import qa  # noqa: E402
import transcribe  # noqa: E402
from writer import campaigns, seconds, validate  # noqa: E402

from clips import KICK_RETIME, YTDLP  # noqa: E402  (same flags, incl. optional cookies)


def log(msg):
    print(f"[agent] {msg}", flush=True)


def download(script, d):
    a, b = seconds(script["start"]), seconds(script["end"])
    key = f"{script['video_id']}_{a:.2f}_{b:.2f}"
    src = os.path.join(d, "src.mp4")
    stamp = os.path.join(d, "src.key")
    if os.path.exists(src) and os.path.exists(stamp) and open(stamp).read() == key:
        return src
    for f in ("src.mp4", "words.json"):
        if os.path.exists(os.path.join(d, f)):
            os.remove(os.path.join(d, f))
    log(f"downloading {script['video_id']} {a:.1f}-{b:.1f}s")
    if script.get("source") == "kick_clip":
        # Kick clip (HLS): copy the whole clip first (seeking/re-encoding straight from the
        # playlist dropped frames -> stutter), then cut locally with an exact frame rate.
        full = os.path.join(d, "kick_full.mp4")
        if not os.path.exists(full):
            # Kick clip playlists jump ~2 s in their timestamps every ~10 s: rebuild continuous
            # timestamps from frame/sample counts, otherwise video freezes and audio drifts.
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", script["source_url"],
                            "-map", "0:v:0", "-map", "0:a:0", *KICK_RETIME, full], check=True)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", full, "-ss", f"{a:.2f}", "-to", f"{b:.2f}",
                        "-vf", "fps=30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
                        "-c:a", "aac", "-b:a", "192k", src], check=True)
        open(stamp, "w").write(key)
        return src
    subprocess.run(YTDLP + [
        "-f", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b",
        "--download-sections", f"*{a:.2f}-{b:.2f}", "--force-keyframes-at-cuts",
        "--merge-output-format", "mp4", "-o", os.path.join(d, "src.%(ext)s"),
        f"https://www.youtube.com/watch?v={script['video_id']}"], check=True)
    open(stamp, "w").write(key)
    return src


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", path], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def social_caption(s, camp, extra_tags, limit=6):
    """Short caption for TikTok / Instagram Reels: title, CTA, a few hashtags (required first)."""
    from publisher import _clean_tag
    tags = []
    for t in list(camp.get("required_hashtags", [])) + list(s.get("hashtags", [])) + extra_tags:
        t = _clean_tag(t)
        if t and t.lower() not in (x.lower() for x in tags):
            tags.append(t)
    cta = camp.get("required_text") or f"Watch more from {camp['streamer']}: {camp['credit']}"
    # searchable keywords: TikTok search weighs caption text (no links: some campaigns forbid them)
    kw = [k for k in (s.get("tags") or [])[:2]] + [f"{camp['streamer']} GTA 6", "GTA 6 funny moments"]
    keywords = " | ".join(dict.fromkeys(k for k in kw if k))
    return f"{s['title']}\n\n{keywords}\n\n{cta}\n\n" + " ".join("#" + t for t in tags[:limit])


def source_link(s):
    if s.get("source") == "kick_clip":
        return s.get("source_page") or s["source_url"]
    return f"https://www.youtube.com/watch?v={s['video_id']}&t={int(seconds(s['start']))}s"


def upload_text(s, camp):
    from publisher import build_metadata
    meta = build_metadata(s)
    within = camp.get("submit_within_minutes", 30)
    platforms = camp.get("platforms", ["youtube", "tiktok", "instagram"])
    out = (f"CAMPAIGN: {camp['name']}\n\n"
           f"===== YOUTUBE SHORTS =====\n"
           f"TITLE (copy):\n{meta['title']}\n\nDESCRIPTION (copy):\n{meta['description']}\n\n"
           f"FIRST COMMENT (post it, then pin it):\n{s['first_comment']}\n\n")
    if "tiktok" in platforms:
        out += (f"===== TIKTOK (same mp4) =====\n"
                f"CAPTION (copy):\n{social_caption(s, camp, ['gtavi', 'gaming', 'fyp'])}\n\n")
    if "instagram" in platforms:
        out += (f"===== INSTAGRAM REELS (same mp4) =====\n"
                f"CAPTION (copy):\n{social_caption(s, camp, ['gtavi', 'gaming', 'reels'], limit=8)}\n\n")
    names = ", ".join(p.capitalize() for p in platforms)
    return out + (f"===== CAMPAIGN =====\n"
                  f"Post only on: {names}. Submit EACH link within {within} minutes of posting it:\n"
                  f"{camp['campaign_url']}\n\nSource: {source_link(s)}\n")


def share(files):
    """Copy the finished Short to the first available folder in settings.json `share_dirs`
    (e.g. Google Drive for desktop), so it can be posted from the phone."""
    cfg = os.path.join(HERE, "settings.json")
    if not os.path.exists(cfg):
        return None
    dirs = json.load(open(cfg, encoding="utf-8")).get("share_dirs", [])
    for target in dirs:
        root = os.path.dirname(target.rstrip("\\/"))
        if os.path.isdir(root):
            os.makedirs(target, exist_ok=True)
            for f in files:
                shutil.copy2(f, target)
            log(f"copied to {target}")
            return target
    log("share folder not available (is Google Drive for desktop running?): copy skipped")
    return None


def build(d, script):
    camp = campaigns()[script["campaign"]]
    src = download(script, d)
    problems = qa.check(src, final=False)
    if problems:
        sys.exit("QA FAILED on the source cut (do not publish):\n- " + "\n- ".join(problems))
    log("transcribing (faster-whisper)")
    words = transcribe.words(src, os.path.join(d, "words.json"))
    total = min(duration(src), seconds(script["end"]) - seconds(script["start"]), 59.0)
    name = f"short_{script['slug']}.mp4"
    log(f"montage ({script.get('layout') or camp.get('layout')}, {total:.1f}s)")
    montage.render(d, src, words, script, camp, name, total)
    problems = qa.check(os.path.join(d, name), expected=total)
    if problems:
        os.replace(os.path.join(d, name), os.path.join(d, f"FAILED_QA_{name}"))
        sys.exit("QA FAILED on the Short (renamed FAILED_QA_..., do not publish):\n- "
                 + "\n- ".join(problems))
    log("QA OK (audio/video in sync, no timestamp jumps, 30 fps, 1080x1920)")
    txt = os.path.join(d, f"short_{script['slug']}_upload.txt")
    open(txt, "w", encoding="utf-8").write(upload_text(script, camp))
    share([os.path.join(d, name), txt])
    log(f"done: {os.path.join(d, name)}")
    return os.path.join(d, name), total


def check_frames(d):
    script = json.load(open(os.path.join(d, "script.json"), encoding="utf-8"))
    video = os.path.join(d, f"short_{script['slug']}.mp4")
    out = montage.frames(d, video, duration(video))
    src = os.path.join(d, "src.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "2", "-i", "src.mp4", "-frames:v", "1",
                    "-vf", "scale=960:-2", "src_frame.jpg"], check=True, cwd=d)
    out.append(os.path.join(d, "src_frame.jpg"))
    print("\n".join(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", help="scripts/<slug>.json")
    ap.add_argument("--resume", help="existing output/<slug> folder")
    ap.add_argument("--frames", help="output/<slug> folder: extract check frames")
    ap.add_argument("--out", default=os.path.join(HERE, "output"))
    a = ap.parse_args()

    if a.frames:
        return check_frames(os.path.abspath(a.frames))
    if a.resume:
        d = os.path.abspath(a.resume)
        script = json.load(open(os.path.join(d, "script.json"), encoding="utf-8"))
    elif a.script:
        script = json.load(open(a.script, encoding="utf-8"))
        d = os.path.join(os.path.abspath(a.out), script["slug"])
        os.makedirs(d, exist_ok=True)
        json.dump(script, open(os.path.join(d, "script.json"), "w", encoding="utf-8"),
                  indent=1, ensure_ascii=False)
    else:
        ap.error("give --script, --resume or --frames")
    problems = validate(script)
    if problems:
        sys.exit("script problems:\n- " + "\n- ".join(problems))
    build(d, script)


if __name__ == "__main__":
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"{tool} not found")
    main()
