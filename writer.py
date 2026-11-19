#!/usr/bin/env python3
"""Script format and writing rules for one Short. Claude (the daily routine) is the writer:
it reads the candidates from clips.py and writes scripts/<slug>.json by hand.

  python writer.py check scripts/<slug>.json      # validate a script before rendering
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MIN_LEN, MAX_LEN = 12, 35  # seconds; prefer 15-25: higher "viewed vs swiped away" and completion

SCHEMA = {
    "slug": "short snake_case name, unique (e.g. tomo_police_chase_fail)",
    "campaign": "id from campaigns.json",
    "video_id": "YouTube id of the source stream/video, or the Kick clip id (clip_...)",
    "source": "only for Kick: 'kick_clip' (copy from the candidate)",
    "source_url": "only for Kick: the clip's playlist URL (candidate source_url)",
    "source_page": "only for Kick: the clip page URL (candidate url), shown as source",
    "start": "clip start in the source, seconds or 'h:mm:ss'",
    "end": "clip end in the source, seconds or 'h:mm:ss' (12-35 s after start, prefer 15-25)",
    "tags": "3-4 post-specific search phrases describing exactly this clip (e.g. 'dom gta 6 gas station robbery'); niche and broad tags are added automatically",
    "layout": "optional: 'blur' (16:9 video on blurred background) or 'facecam' (cam on top, game below); default from campaigns.json",
    "zoom": "optional, blur layout only: 1.0-1.5, default 1.25",
    "facecam": "optional [x, y, w, h] as fractions 0-1 of the source frame; required for layout 'facecam'",
    "gameplay": "optional [x, y, w, h] fractions for the game area, default whole frame",
    "title": "YouTube title, max 70 chars, English, no #shorts (added automatically)",
    "description": "1-2 sentences of context in English; credit + links are added automatically",
    "hashtags": "3-6 hashtags without # (gta6 and the campaign's required ones are added automatically)",
    "hook_text": "1-2 short ALL CAPS lines separated by \\n, shown in the first 2.5 s",
    "highlight_words": "UPPERCASE words to colour yellow in captions",
    "first_comment": "comment the channel posts and pins, max 150 chars, no links",
}

RULES = """You pick and package one moment from a streamer's GTA 6 stream as a YouTube Short in English.

Picking the moment:
- Funny, high-energy, unexpected, or a mini story with setup and payoff. A viewer who never saw
  the stream must understand it, but keep setup to 1-3 s: start as close to the action as
  possible (cold open), end right after the reaction (do not let it trail off). An ending that
  flows back into the start (loop) is a bonus.
- 12-35 seconds, prefer 15-25: the share of people who stop instead of swiping away (aim > 70%)
  and the completion rate decide how far a Short travels. Go above 25 s only if the moment
  really needs it; cut any setup the payoff does not need.
- The first 1-2 seconds must stop the scroll: start on the most intriguing line or action, and
  make hook_text tease the payoff.
- Read performance.md first and favour the kind of moment that performed best so far.
- Never: leaked footage, story spoilers, an isolated cutscene or in-game TV/radio show posted on
  its own, hacks/mods/exploit tutorials, drama bait, anything hateful or sexual, a clip already in
  used_clips.md. (Funny glitches/fails and the game's built-in single-player cheat codes are fine.)
- The streamer must be the focus (their voice/reaction), not just raw gameplay.

- Prefer in-game GTA 6 moments (funny/chaotic moments and first reactions to new features,
  cars, places, missions; stunts, chases, fails, interactions). One clear moment.
- Never portray the streamer in a negative light. Never cut an answer so it says something
  different from what they meant.
- Story moments (a character's death, betrayal, big reveal): only with "SPOILER WARNING" as the
  first hook line. Adult/NSFW jokes: skip the moment unless it stays clean for YouTube/TikTok
  without changing its meaning.

Packaging:
- title: what happens, curiosity WITHOUT exaggerating or inventing: no misleading titles, fake
  context or clickbait ("Tomo tried to rob a bank with a lawnmower" only if he really did).
- hook_text: the 1-2 line tease shown in the first 2 seconds, ALL CAPS, max ~22 chars per line,
  accurate like the title.
- The end-screen CTA (cta_overlay in campaigns.json) is added automatically.
- hashtags: pick 3-5 from the campaign's optional_hashtags plus clip-specific ones, and vary them
  between posts (required ones are added automatically).
- description: 1-2 plain sentences of context. Credit and links are added by publisher.py.
- first_comment: an easy either/or or "what would you do" question about the clip.
- Respect every line of the campaign's "brief" in campaigns.json."""


def seconds(t):
    if isinstance(t, (int, float)):
        return float(t)
    parts = [float(p) for p in str(t).strip().split(":")]
    s = 0.0
    for p in parts:
        s = s * 60 + p
    return s


def campaigns():
    return {c["id"]: c for c in json.load(open(os.path.join(HERE, "campaigns.json"), encoding="utf-8"))}


def used_clips(with_slug=False):
    """(video_id, start, end[, slug]) already published, from used_clips.md."""
    out = []
    path = os.path.join(HERE, "used_clips.md")
    if not os.path.exists(path):
        return out
    for line in open(path, encoding="utf-8"):
        m = re.match(r"\|\s*[\d-]+\s*\|\s*([\w-]*)\s*\|\s*([\w-]{6,})\s*\|\s*([\d:.]+)\s*-\s*([\d:.]+)\s*\|", line)
        if m:
            row = (m.group(2), seconds(m.group(3)), seconds(m.group(4)))
            out.append(row + (m.group(1),) if with_slug else row)
    return out


def validate(s):
    errs = []
    for k in ("slug", "campaign", "video_id", "start", "end", "title", "description",
              "hashtags", "hook_text", "first_comment"):
        if not s.get(k):
            errs.append(f"missing {k}")
    if errs:
        return errs
    camp = campaigns().get(s["campaign"])
    if not camp:
        errs.append(f"unknown campaign {s['campaign']}")
    elif not camp.get("active"):
        errs.append(f"campaign {s['campaign']} is not active")
    if camp and camp.get("logo") and not os.path.exists(os.path.join(HERE, camp["logo"]["file"])):
        errs.append(f"campaign logo missing: put it at {camp['logo']['file']}")
    if s.get("source") == "kick_clip" and not s.get("source_url"):
        errs.append("kick_clip needs source_url")
    if not re.fullmatch(r"[a-z0-9_]+", s["slug"]):
        errs.append("slug must be snake_case")
    a, b = seconds(s["start"]), seconds(s["end"])
    if not MIN_LEN <= b - a <= MAX_LEN:
        errs.append(f"clip length {b - a:.1f}s, must be {MIN_LEN}-{MAX_LEN}s")
    for vid, ua, ub, slug in used_clips(with_slug=True):
        if vid == s["video_id"] and a < ub and b > ua and slug != s["slug"]:
            errs.append(f"overlaps a clip already used ({ua:.0f}-{ub:.0f}s of {vid})")
    if len(s["title"]) > 70:
        errs.append("title longer than 70 chars")
    if len(s["first_comment"]) > 150 or "http" in s["first_comment"]:
        errs.append("first_comment: max 150 chars, no links")
    layout = s.get("layout") or (camp or {}).get("layout", "blur")
    if layout == "facecam" and not (s.get("facecam") or (camp or {}).get("facecam")):
        errs.append("layout facecam needs facecam [x, y, w, h]")
    return errs


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "check":
        sys.exit(__doc__)
    problems = validate(json.load(open(sys.argv[2], encoding="utf-8")))
    print("\n".join(problems) if problems else "OK")
    sys.exit(1 if problems else 0)
