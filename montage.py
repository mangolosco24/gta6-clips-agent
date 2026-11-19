"""1080x1920 vertical edit of the clip: layout, word captions, hook, credit, loudness."""
import os
import re
import subprocess

W, H, FPS = 1080, 1920, 30
FONT = os.environ.get("CAPTION_FONT", "Arial Black")
CAM_H = 768  # facecam layout: top part height


def _run(args, cwd):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True, cwd=cwd)


def _ts(s):
    s = max(s, 0)
    return f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{s % 60:05.2f}"


PROFANITY = {"fuck": "F*CK", "fucking": "F*CKING", "shit": "SH*T", "bitch": "B*TCH",
             "motherfucker": "MOTHERF*CKER", "fucked": "F*CKED", "dick": "D*CK"}


def _clean(t):
    return re.sub(r"[{}\\]", "", t)


def _censor(t):
    """On-screen captions only (the audio is untouched): TikTok/YouTube push down written swears."""
    return re.sub(r"[A-Za-z]+", lambda m: PROFANITY.get(m.group(0).lower(), m.group(0)), t)


def _chunks(words):
    """Group words into 1-3 word caption chunks: (start, end, [words])."""
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        text = " ".join(x["w"] for x in cur)
        if (len(cur) == 3 or len(text) > 14 or re.search(r"[.,!?;:]$", w["w"])
                or not nxt or nxt["start"] - w["end"] > 0.6):
            end = w["end"] + 0.25
            if nxt:
                end = min(max(end, nxt["start"] - 0.05), nxt["start"])
            out.append((cur[0]["start"], max(end, cur[0]["start"] + 0.3), cur))
            cur = []
    return out


# Visual presets, picked per Short from its slug: platforms push down clips that all look like
# the same template, so colour, caption size/position and hook box vary between posts.
# Colours are ASS &HAABBGGRR.
STYLES = [
    {"accent": "&H0000D7FF", "size": 84, "dy": 0, "hook_back": "&H30000000"},   # yellow
    {"accent": "&H005AFF4C", "size": 88, "dy": -50, "hook_back": "&H00000000"},  # green
    {"accent": "&H00FFE500", "size": 80, "dy": 40, "hook_back": "&H40000000"},   # cyan
    {"accent": "&H00A040FF", "size": 86, "dy": -20, "hook_back": "&H10000000"},  # pink
    {"accent": "&H000096FF", "size": 82, "dy": 25, "hook_back": "&H30000000"},   # orange
]


def style_for(slug):
    import zlib
    return STYLES[zlib.crc32(slug.encode()) % len(STYLES)]


def subtitles(words, hook, highlights, credit, layout, total, path, cta="", style=None):
    st = style or STYLES[0]
    cap_y = (1330 if layout == "blur" else 1180) + st["dy"]
    acc = st["accent"]
    hdr = f"""[Script Info]
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{FONT},{st['size']},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,3,5,70,70,0,1
Style: Hook,{FONT},70,&H00FFFFFF,&H00FFFFFF,&H00000000,{st['hook_back']},-1,0,0,0,100,100,0,0,3,16,0,8,70,70,170,1
Style: Credit,Arial,40,&H30FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,5,60,60,0,1
Style: Cta,{FONT},62,{acc},&H00FFFFFF,&H00000000,&H30000000,-1,0,0,0,100,100,0,0,3,16,0,8,70,70,170,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    if hook:
        ev.append(f"Dialogue: 2,{_ts(0)},{_ts(min(2.6, total))},Hook,,0,0,0,,"
                  f"{{\\fad(120,200)}}{_clean(hook.upper()).replace(chr(10), chr(92) + 'N')}")
    if cta and total > 6:
        ev.append(f"Dialogue: 2,{_ts(total - 3.2)},{_ts(total)},Cta,,0,0,0,,"
                  f"{{\\fad(150,0)}}{_clean(cta.upper()).replace(chr(10), chr(92) + 'N')}")
    if credit:
        ev.append(f"Dialogue: 1,{_ts(0)},{_ts(total)},Credit,,0,0,0,,"
                  f"{{\\pos(540,{cap_y + 150})}}via {_clean(credit)}")
    hl = {x.strip(".,!?").upper() for h in highlights for x in h.split() if x.strip(".,!?")}
    acc = "&H" + acc[4:]  # inline \c takes &HBBGGRR (no alpha byte)
    for a, b, ws in _chunks(words):
        if a >= total:
            break
        # karaoke: the chunk stays on screen, the word being spoken lights up in the accent colour
        texts = [_censor(_clean(w["w"])).upper() for w in ws]
        for j, w in enumerate(ws):
            s = a if j == 0 else w["start"]
            e = ws[j + 1]["start"] if j + 1 < len(ws) else b
            if s >= total or e <= s:
                continue
            parts = []
            for k, t in enumerate(texts):
                if k == j:
                    parts.append(f"{{\\c{acc}&}}{t}{{\\c&HFFFFFF&}}")
                elif t.strip(".,!?") in hl:
                    parts.append(f"{{\\c{acc}&\\alpha&H40&}}{t}{{\\c&HFFFFFF&\\alpha&H00&}}")
                else:
                    parts.append(t)
            pop = "\\fscx88\\fscy88\\t(0,80,\\fscx100\\fscy100)" if j == 0 else ""
            ev.append(f"Dialogue: 0,{_ts(s)},{_ts(min(e, total))},Cap,,0,0,0,,"
                      f"{{\\pos(540,{cap_y}){pop}}}{' '.join(parts)}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(hdr + "\n".join(ev) + "\n")


def _rect(r, default=(0, 0, 1, 1)):
    x, y, w, h = r or default
    return f"crop=iw*{w}:ih*{h}:iw*{x}:ih*{y}"


def video_filter(layout, zoom=1.25, facecam=None, gameplay=None):
    if layout == "facecam":
        game_h = H - CAM_H
        return (f"[0:v]split=2[a][b];"
                f"[a]{_rect(facecam)},scale={W}:{CAM_H}:force_original_aspect_ratio=increase,crop={W}:{CAM_H}[cam];"
                f"[b]{_rect(gameplay)},scale={W}:{game_h}:force_original_aspect_ratio=increase,crop={W}:{game_h}[game];"
                f"[cam][game]vstack=inputs=2")
    fg_h = int(round(W * 9 / 16 * zoom / 2)) * 2
    return (f"[0:v]split=2[a][b];"
            f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"boxblur=24:2,eq=brightness=-0.18:saturation=1.1[bg];"
            f"[b]{_rect(gameplay)},scale={W}:{fg_h}:force_original_aspect_ratio=increase,crop={W}:{fg_h}[fg];"
            f"[bg][fg]overlay=(W-w)/2:{(1250 - fg_h) // 2 + 130}")


def punch_in(times, zoom=1.15, ramp=0.12, hold=1.1):
    """DISABLED (not called): zoompan desynced audio from video. Kept only for reference.
    zoompan filter that punches in on the given seconds, then back to 1x."""
    if not times:
        return ""
    k = zoom - 1
    terms = []
    for t in sorted(float(x) for x in times):
        a, b, c = t, t + ramp, t + ramp + hold
        terms.append(f"if(between(it,{a:.2f},{b:.2f}),{k:.3f}*(it-{a:.2f})/{ramp},"
                     f"if(between(it,{b:.2f},{c:.2f}),{k:.3f},0))")
    z = "1+" + "+".join(terms)
    return (f",fps={FPS},zoompan=z='{z}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":s={W}x{H}:fps={FPS}")


def render(d, src, words, script, campaign, out_name, total):
    layout = script.get("layout") or campaign.get("layout") or "blur"
    facecam = script.get("facecam") or campaign.get("facecam")
    gameplay = script.get("gameplay") or campaign.get("gameplay")
    subtitles(words, script.get("hook_text", ""), script.get("highlight_words", []),
              campaign.get("credit", ""), layout, total, os.path.join(d, "subs.ass"),
              campaign.get("cta_overlay", ""), style_for(script.get("slug", "")))
    vf = video_filter(layout, float(script.get("zoom", 1.25)), facecam, gameplay)
    inputs = ["-i", os.path.basename(src)]
    logo = campaign.get("logo")
    if logo:
        # mandatory streamer logo, visible for the whole video (e.g. KreekCraft campaign)
        here = os.path.dirname(os.path.abspath(__file__))
        inputs += ["-loop", "1", "-i", os.path.join(here, logo["file"])]
        vf = (f"{vf}[base];[1:v]scale={int(logo.get('width', 300))}:-1,format=rgba[lg];"
              f"[base][lg]overlay={logo.get('x', '40')}:{logo.get('y', '40')}:shortest=1")
    fc = (f"{vf},subtitles=subs.ass,fps={FPS},format=yuv420p[v];"
          f"[0:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000,"
          f"afade=t=out:st={max(total - 0.4, 0):.2f}:d=0.4[a]")
    _run([*inputs, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
          "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
          "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out_name], cwd=d)


def frames(d, video, total, n=5):
    """Extract n check frames: frame_1.jpg ... (and the raw source frame for layout checks)."""
    out = []
    for i in range(n):
        t = 0.5 + (total - 1) * i / max(n - 1, 1)
        name = f"frame_{i + 1}.jpg"
        _run(["-ss", f"{t:.2f}", "-i", os.path.basename(video), "-frames:v", "1",
              "-vf", "scale=540:-2", name], cwd=d)
        out.append(os.path.join(d, name))
    return out
