#!/usr/bin/env python3
"""Find candidate moments in the recent GTA streams/videos of every active campaign.

  python clips.py scan                    # -> output/candidates.json (and a short summary)
  python clips.py scan --days 4 --per-video 6

Signals, best first:
  1. YouTube "most replayed" heatmap (videos with enough views)
  2. live chat replay spikes (streams, when there is no heatmap yet)
  3. full transcript (videos up to 40 min with neither)
For each candidate window it adds the auto-caption transcript with absolute timestamps,
so Claude can choose the exact 15-58 s clip.
"""
import argparse
import datetime as dt
import glob
import json
import os
import subprocess
import sys

from writer import campaigns, used_clips

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "output", "cache")
YTDLP = [sys.executable, "-m", "yt_dlp", "--no-warnings", "--ignore-config"]


def _cookies():
    """Optional YouTube cookies (settings.json "youtube_cookies": path to a cookies.txt export),
    used only when YouTube asks to "confirm you're not a bot"."""
    cfg = os.path.join(HERE, "settings.json")
    if os.path.exists(cfg):
        p = json.load(open(cfg, encoding="utf-8")).get("youtube_cookies")
        if p and os.path.exists(os.path.join(HERE, p)):
            return ["--cookies", os.path.join(HERE, p)]
    return []


YTDLP += _cookies()
# YouTube's signature/n challenges need a JS runtime: deno from requirements.txt (in the venv)
_DENO = os.path.join(os.path.dirname(sys.executable), "deno.exe" if os.name == "nt" else "deno")
if os.path.exists(_DENO):
    YTDLP += ["--js-runtimes", f"deno:{_DENO}"]
FULL_TRANSCRIPT_MAX = 40 * 60  # without other signals, videos up to 40 min are read whole


def log(msg):
    print(f"[clips] {msg}", file=sys.stderr, flush=True)


def ytdlp(args, timeout=600):
    r = subprocess.run(YTDLP + args, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    if r.returncode:
        raise RuntimeError(r.stderr.strip()[-400:])
    return r.stdout


def hms(s):
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


# ---------- listing ----------

def recent_videos(source, n=8):
    """[(id, title, live_status)] from the channel tab: one cheap request, no per-video calls."""
    try:
        data = json.loads(ytdlp(["--flat-playlist", "-J", "--playlist-end", str(n), source]))
    except RuntimeError as e:
        log(f"cannot list {source}: {e}")
        return []
    return [(e["id"], e.get("title") or "", e.get("live_status"))
            for e in data.get("entries") or [] if e.get("id")]


def video_info(vid, max_age_h=6):
    """Full metadata, cached for a few hours to keep the number of YouTube requests low."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{vid}.info.json")
    if os.path.exists(path) and (dt.datetime.now().timestamp() - os.path.getmtime(path)) < max_age_h * 3600:
        return json.load(open(path, encoding="utf-8"))
    info = json.loads(ytdlp(["-J", "--skip-download", f"https://www.youtube.com/watch?v={vid}"]))
    info.pop("formats", None)
    info.pop("requested_formats", None)
    json.dump(info, open(path, "w", encoding="utf-8"))
    return info


def video_date(info):
    ts = info.get("release_timestamp") or info.get("timestamp")
    if ts:
        return dt.datetime.fromtimestamp(ts, dt.timezone.utc)
    if info.get("upload_date"):
        return dt.datetime.strptime(info["upload_date"], "%Y%m%d").replace(tzinfo=dt.timezone.utc)


# ---------- signals ----------

def heatmap_windows(info, k):
    hm = info.get("heatmap") or []
    if len(hm) < 10:
        return []
    dur = info.get("duration") or hm[-1]["end_time"]
    peaks = sorted(hm, key=lambda h: h["value"], reverse=True)
    out = []
    for h in peaks:
        if h["start_time"] < dur * 0.02:  # skip the "starting soon" part
            continue
        a = max(0, h["start_time"] - 30)
        b = min(dur, max(h["end_time"], a + 60) + 30)
        b = min(b, a + 240)
        if any(a < y and b > x for x, y, _ in out):
            continue
        out.append((a, b, round(h["value"], 3)))
        if len(out) >= k:
            break
    return out


def chat_windows(vid, dur, k, bin_s=30):
    """Spikes of messages per 30 s in the live chat replay. The reaction lags the moment,
    so the window starts 60 s before the spike."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{vid}.live_chat.json")
    if not os.path.exists(path):
        try:
            ytdlp(["--skip-download", "--write-subs", "--sub-langs", "live_chat",
                   "-o", os.path.join(CACHE, "%(id)s.%(ext)s"),
                   f"https://www.youtube.com/watch?v={vid}"], timeout=900)
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            log(f"{vid}: no chat replay ({str(e)[:120]})")
            return []
    if not os.path.exists(path):
        return []
    bins = {}
    for line in open(path, encoding="utf-8", errors="replace"):
        try:
            off = int(json.loads(line)["replayChatItemAction"]["videoOffsetTimeMsec"]) / 1000
        except (KeyError, ValueError, TypeError):
            continue
        bins[int(off // bin_s)] = bins.get(int(off // bin_s), 0) + 1
    if not bins:
        return []
    avg = sum(bins.values()) / max(len(bins), 1)
    out = []
    for b, n in sorted(bins.items(), key=lambda x: x[1], reverse=True):
        t = b * bin_s
        if t < dur * 0.02:
            continue
        a, e = max(0, t - 60), min(dur, t + bin_s + 30)
        if any(a < y and e > x for x, y, _ in out):
            continue
        out.append((a, e, round(n / avg, 2)))
        if len(out) >= k:
            break
    return out


# ---------- transcript ----------

def captions(vid):
    """[(seconds, text)] from YouTube auto captions (English), cached."""
    os.makedirs(CACHE, exist_ok=True)
    files = glob.glob(os.path.join(CACHE, f"{vid}.*.json3"))
    if not files:
        try:
            ytdlp(["--skip-download", "--write-auto-subs", "--write-subs", "--sub-langs", "en.*,en",
                   "--sub-format", "json3", "-o", os.path.join(CACHE, "%(id)s.%(ext)s"),
                   f"https://www.youtube.com/watch?v={vid}"])
        except RuntimeError as e:
            log(f"{vid}: no captions ({e})")
        files = glob.glob(os.path.join(CACHE, f"{vid}.*.json3"))
    if not files:
        return []
    files.sort(key=lambda f: ("orig" not in f, len(f)))
    data = json.load(open(files[0], encoding="utf-8"))
    out = []
    for ev in data.get("events", []):
        text = "".join(s.get("utf8", "") for s in ev.get("segs", []) or []).replace("\n", " ").strip()
        if text:
            out.append((ev.get("tStartMs", 0) / 1000, text))
    return out


def whisper_captions(vid, max_dur):
    """Fallback when YouTube captions are unavailable (e.g. HTTP 429): download the audio
    and transcribe it locally. Only for videos up to max_dur seconds."""
    path = os.path.join(CACHE, f"{vid}.whisper.json")
    if os.path.exists(path):
        return [tuple(x) for x in json.load(open(path, encoding="utf-8"))]
    try:
        ytdlp(["-f", "ba[ext=m4a]/ba", "--match-filter", f"duration<={max_dur}",
               "-o", os.path.join(CACHE, "%(id)s.audio.%(ext)s"),
               f"https://www.youtube.com/watch?v={vid}"], timeout=900)
    except RuntimeError as e:
        log(f"{vid}: audio download failed ({e})")
        return []
    files = glob.glob(os.path.join(CACHE, f"{vid}.audio.*"))
    if not files:
        return []
    from transcribe import ensure_model
    segs, _ = ensure_model().transcribe(files[0], language="en", vad_filter=True)
    out = [(round(s.start, 1), s.text.strip()) for s in segs if s.text.strip()]
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    os.remove(files[0])
    return out


def transcript(caps, a, b):
    return "\n".join(f"[{hms(t)}] {txt}" for t, txt in caps if a <= t <= b)


# ---------- main ----------

# ---------- Kick (clips made by viewers from the streamer's lives) ----------

KICK_API = "https://kick.com/api/v2/channels/{slug}/clips"
KICK_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/131.0 Safari/537.36",
                "Accept": "application/json"}


# Kick clip playlists have timestamp jumps (~2 s every ~10 s). Re-timing by frame/sample count
# gives continuous video and audio. Used both for transcripts here and for the download in agent.py,
# so candidate timestamps match the footage that gets cut.
KICK_RETIME = ["-vf", "setpts=N/FRAME_RATE/TB", "-af", "asetpts=N/SR/TB",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-c:a", "aac", "-b:a", "192k"]


def kick_clips(slug, time_range):
    import requests
    r = requests.get(KICK_API.format(slug=slug), params={"sort": "view", "time": time_range},
                     headers=KICK_HEADERS, timeout=30)
    r.raise_for_status()
    return r.json().get("clips", [])


def kick_transcript(clip):
    """Whisper transcript of a Kick clip ([(seconds, text)]), cached."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{clip['id']}.retimed.whisper.json")
    if os.path.exists(path):
        return [tuple(x) for x in json.load(open(path, encoding="utf-8"))]
    audio = os.path.join(CACHE, f"{clip['id']}.m4a")
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", clip["clip_url"], "-vn",
                        "-af", "asetpts=N/SR/TB", "-c:a", "aac", "-b:a", "96k", audio],
                       capture_output=True, text=True)
    if r.returncode or not os.path.exists(audio):
        log(f"{clip['id']}: audio download failed {r.stderr[-200:]}")
        return []
    from transcribe import ensure_model
    segs, _ = ensure_model().transcribe(audio, language="en", vad_filter=True)
    out = [(round(s.start, 1), s.text.strip()) for s in segs if s.text.strip()]
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    os.remove(audio)
    return out


def kick_candidates(camp, days, used, max_clips):
    """Most viewed GTA VI clips of the campaign's Kick channel, from eligible streams."""
    slug = camp["kick_channel"]
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    eligible = dt.datetime.fromisoformat(camp.get("eligible_from", "2000-01-01")).replace(
        tzinfo=dt.timezone.utc)
    used_ids = {u for u, _, _ in used}
    clips, seen = [], set()
    for rng in ("day", "week"):
        try:
            for c in kick_clips(slug, rng):
                if c["id"] not in seen:
                    seen.add(c["id"])
                    clips.append(c)
        except Exception as e:  # noqa: BLE001 - network/API errors: report and go on
            log(f"kick {slug} ({rng}): {e}")
    out = []
    for c in sorted(clips, key=lambda c: c.get("views", 0), reverse=True):
        created = dt.datetime.fromisoformat(c["created_at"].replace("Z", "+00:00"))
        cat = (c.get("category") or {}).get("slug", "")
        if "grand-theft-auto-vi" not in cat or created < max(since, eligible):
            continue
        if c.get("is_mature"):
            continue
        caps = kick_transcript(c)
        dur = c.get("duration") or 0
        out.append({
            "campaign": camp["id"], "source": "kick_clip", "video_id": c["id"],
            "source_url": c["clip_url"], "title": c.get("title", ""),
            "url": f"https://kick.com/{slug}/clips/{c['id']}",
            "livestream_id": c.get("livestream_id"),
            "date": created.date().isoformat(), "duration": hms(dur),
            "signal": "kick_clip_views", "score": c.get("views", 0),
            "window": [hms(0), hms(dur)], "window_s": [0, int(dur)],
            "already_used_overlap": c["id"] in used_ids,
            "transcript": transcript(caps, 0, dur + 1) or "(no speech)"})
        log(f"{camp['id']} kick {c['id']}: {c.get('views')} views, {dur}s - {c.get('title', '')[:50]}")
        if len(out) >= max_clips:
            break
    return out


def scan(days, per_video, per_source, only=None, kick_clips=8):
    used = used_clips()
    result = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "candidates": [], "skipped_videos": []}
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    for camp in campaigns().values():
        if not camp.get("active"):
            continue
        if only and camp["id"] != only:
            continue
        if camp.get("platform") == "kick":
            result["candidates"] += kick_candidates(camp, days, used, kick_clips)
            continue
        seen = set()
        for src in camp["sources"]:
            for vid, flat_title, flat_status in recent_videos(src, per_source):
                if vid in seen:
                    continue
                seen.add(vid)
                keys = camp.get("title_keywords", [])
                if flat_status in ("is_live", "is_upcoming") or (
                        keys and not any(k in flat_title.lower() for k in keys)):
                    result["skipped_videos"].append({
                        "video_id": vid, "title": flat_title,
                        "why": flat_status if flat_status in ("is_live", "is_upcoming")
                        else "title does not match"})
                    continue
                try:
                    info = video_info(vid)
                except RuntimeError as e:
                    result["skipped_videos"].append({"video_id": vid, "why": str(e)[:150]})
                    continue
                title = info.get("title", "")
                when = video_date(info)
                why = None
                if info.get("live_status") in ("is_live", "is_upcoming", "post_live"):
                    why = f"live_status {info.get('live_status')}"
                elif when and when < since:
                    why = f"older than {days} days"
                elif not any(k in title.lower() for k in camp.get("title_keywords", [])):
                    why = "title does not mention GTA 6"
                if why:
                    result["skipped_videos"].append({"video_id": vid, "title": title, "why": why})
                    continue
                dur = info.get("duration") or 0
                wins, signal = heatmap_windows(info, per_video), "most_replayed"
                if not wins and info.get("was_live"):
                    wins, signal = chat_windows(vid, dur, per_video), "chat_spike"
                if not wins and 0 < dur <= FULL_TRANSCRIPT_MAX:
                    # short edited video, too new for a heatmap: Claude reads the whole transcript
                    wins, signal = [(0, dur, 0)], "full_transcript"
                if not wins:
                    result["skipped_videos"].append({"video_id": vid, "title": title,
                                                     "why": "no heatmap, no chat replay, too long to read whole"})
                    continue
                caps = captions(vid)
                if not caps and dur <= FULL_TRANSCRIPT_MAX:
                    log(f"{vid}: transcribing audio locally")
                    caps = whisper_captions(vid, FULL_TRANSCRIPT_MAX)
                for a, b, score in wins:
                    overlap = any(u == vid and a < ub and b > ua for u, ua, ub in used)
                    result["candidates"].append({
                        "campaign": camp["id"], "video_id": vid, "title": title,
                        "url": f"https://www.youtube.com/watch?v={vid}&t={int(a)}s",
                        "date": when.date().isoformat() if when else None,
                        "duration": hms(dur), "signal": signal, "score": score,
                        "window": [hms(a), hms(b)], "window_s": [int(a), int(b)],
                        "already_used_overlap": overlap,
                        "transcript": transcript(caps, a, b) or "(no captions)"})
                log(f"{camp['id']} {vid}: {len(wins)} candidates ({signal}) - {title[:60]}")
    os.makedirs(os.path.join(HERE, "output"), exist_ok=True)
    out = os.path.join(HERE, "output", "candidates.json")
    json.dump(result, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    log(f"{len(result['candidates'])} candidates -> {out}")
    for c in result["candidates"]:
        print(f"{c['campaign']:8} {c['video_id']} {c['window'][0]}-{c['window'][1]} "
              f"{c['signal']}={c['score']} {'USED ' if c['already_used_overlap'] else ''}{c['title'][:50]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan")
    p.add_argument("--days", type=int, default=3, help="only streams/videos from the last N days")
    p.add_argument("--per-video", type=int, default=5, help="candidate windows per video")
    p.add_argument("--per-source", type=int, default=6, help="latest items per channel tab")
    p.add_argument("--campaign", help="scan only this campaign id")
    p.add_argument("--kick-clips", type=int, default=8, help="most viewed Kick clips to transcribe")
    a = ap.parse_args()
    scan(a.days, a.per_video, a.per_source, a.campaign, a.kick_clips)
