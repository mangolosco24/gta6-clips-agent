#!/usr/bin/env python3
"""Publisher agent: takes Shorts made by agent.py and publishes them on YouTube.

  python publisher.py --auth                      # once: get the YouTube refresh token
  python publisher.py output/barings              # publish one Short
  python publisher.py --all                       # publish every Short not yet published
  python publisher.py output/barings --dry-run    # only write/print title, description, tags
  python publisher.py output/barings --privacy private --at 2026-11-18T17:00:00Z
  python publisher.py output/<slug> --slot auto   # next free slot: 17:00, 20:00 or 23:00 Rome time
  python publisher.py output/<slug> --slot 20:00  # next 20:00 Rome time (scheduled)

Needs YT_CLIENT_ID, YT_CLIENT_SECRET and (after --auth) YT_REFRESH_TOKEN.
Writes output/<slug>/youtube.json with the video id, so a Short is never uploaded twice.
"""
import argparse
import datetime as dt
import glob
import http.server
import json
import os
import re
import sys
import urllib.parse
import webbrowser

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
# upload + comments (engager.py). Changing scopes needs a new --auth.
SCOPE = ("https://www.googleapis.com/auth/youtube.upload "
         "https://www.googleapis.com/auth/youtube.force-ssl "
         "https://www.googleapis.com/auth/calendar.events")  # publish-time reminder events
CALENDAR_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
CATEGORY_GAMING = "20"
TOKEN_FILE = os.path.join(HERE, "youtube_token.json")
# Daily publishing slots (local time). Shorts are uploaded as scheduled and go public then.
SLOTS = ["17:00", "20:00", "23:00"]  # same slots as the scheduled tasks (US-friendly)
SLOT_TZ = "Europe/Rome"
MIN_LEAD = dt.timedelta(minutes=20)  # YouTube needs publishAt a bit in the future

# Channel-wide hashtags: always present, after the clip-specific ones.
BASE_TAGS = ["shorts", "gta6", "gtavi", "gaming", "gta"]
CTA = "Follow for the best GTA 6 stream moments every day."
# Hidden YouTube tags, 3 levels ("viral tags formula"): post-specific (script "tags"),
# niche (GTA 6 / streamer clips + the streamer's name) and broad.
NICHE_TAGS = ["gta 6", "gta 6 funny moments", "gta 6 gameplay", "gta 6 streamer clips"]
BROAD_TAGS = ["viral", "shorts", "viral shorts", "fyp"]


def log(msg):
    print(f"[publisher] {msg}", flush=True)


# ---------- description & hashtags ----------

def _clean_tag(t):
    """Keeps the case given (e.g. campaign tags like GrandTheftAutoVI); dedupe is case-insensitive."""
    return re.sub(r"[^0-9A-Za-z]", "", t.lstrip("#"))


def campaign(script):
    from writer import campaigns
    return campaigns()[script["campaign"]]


def build_hashtags(script, limit=12):
    """Campaign-required hashtags first, then clip ones, then channel ones. No duplicates.
    YouTube ignores all hashtags if there are more than 15."""
    out = []
    required = campaign(script).get("required_hashtags", [])
    for t in list(required) + list(script.get("hashtags", [])) + BASE_TAGS:
        t = _clean_tag(t)
        if t and t.lower() not in (x.lower() for x in out):
            out.append(t)
    # keep #shorts in the first three so YouTube files it as a Short
    out = [x for x in out if x.lower() != "shorts"]
    out.insert(0, "shorts")
    return out[:limit]


def build_metadata(script):
    tags = build_hashtags(script)
    title = script["title"].strip()
    if "#shorts" not in title.lower() and len(title) + 8 <= 100:
        title += " #shorts"
    camp = campaign(script)
    desc = script["description"].strip()
    parts = []
    if camp.get("disclosure"):
        parts.append(camp["disclosure"].strip())
    parts.append(desc)
    if camp.get("no_links") or not camp.get("channel_url"):
        parts.append(f"🎮 Clip from {camp['streamer']} ({camp['credit']}).")
    else:
        parts.append(f"🎮 Clip from {camp['streamer']} ({camp['credit']}). "
                     f"{camp.get('watch_more', 'Watch the full video & subscribe:')} {camp['channel_url']}")
    if camp.get("required_text"):
        parts.append(camp["required_text"].strip())
    parts.append(CTA)
    hashtag_line = " ".join("#" + t for t in tags)
    description = "\n\n".join(parts) + f"\n\n{hashtag_line}"
    # "tags" field: hidden keywords (max 500 chars total), post-specific > niche > broad
    post = [t.strip().lower() for t in script.get("tags", []) if t.strip()][:4]
    streamer = camp.get("streamer", "").lower()
    niche = NICHE_TAGS + ([f"{streamer} gta 6", f"{streamer} clips"] if streamer else [])
    keywords = post + niche + BROAD_TAGS + [t.lower() for t in tags if t.lower() != "shorts"]
    keywords, total = list(dict.fromkeys(keywords)), 0
    kept = []
    for k in keywords:
        total += len(k) + 1
        if total > 480:
            break
        kept.append(k)
    return {"title": title[:100], "description": description[:5000], "tags": kept}


# ---------- OAuth ----------

def _from_files(name):
    """Fallback for running on a PC: client_secret*.json downloaded from Google Cloud,
    and youtube_token.json written by --auth (both git-ignored)."""
    if name in ("YT_CLIENT_ID", "YT_CLIENT_SECRET"):
        files = sorted(glob.glob(os.path.join(HERE, "client_secret*.json")))
        if files:
            c = json.load(open(files[0]))
            c = c.get("installed") or c.get("web") or {}
            return c.get("client_id" if name == "YT_CLIENT_ID" else "client_secret")
    if name == "YT_REFRESH_TOKEN" and os.path.exists(TOKEN_FILE):
        return json.load(open(TOKEN_FILE)).get("refresh_token")


def env(name):
    v = os.environ.get(name) or _from_files(name)
    if not v:
        sys.exit(f"missing environment variable {name} (see README, section YouTube)")
    return v


def auth_flow():
    """Desktop OAuth flow on localhost: prints the refresh token to save as YT_REFRESH_TOKEN."""
    cid, secret = env("YT_CLIENT_ID"), env("YT_CLIENT_SECRET")
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": "REDIRECT", "response_type": "code",
        "scope": SCOPE, "access_type": "offline", "prompt": "consent"})
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" in q or "error" in q:  # ignore e.g. /favicon.ico
                got["code"] = (q.get("code") or [None])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK, you can close this tab.")

        def log_message(self, *a):
            pass

    # free port picked by the OS on 127.0.0.1, so it never clashes with other local apps
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    redirect = f"http://127.0.0.1:{srv.server_address[1]}"
    url = url.replace("REDIRECT", urllib.parse.quote(redirect, safe=""))
    print("Open this link and allow access (choose your YouTube channel):\n" + url)
    webbrowser.open(url)
    while "code" not in got:
        srv.handle_request()
    if not got["code"]:
        sys.exit("authorization denied")
    r = requests.post(TOKEN_URL, data={
        "code": got["code"], "client_id": cid, "client_secret": secret,
        "redirect_uri": redirect, "grant_type": "authorization_code"}, timeout=30)
    r.raise_for_status()
    tok = r.json()["refresh_token"]
    json.dump({"refresh_token": tok}, open(TOKEN_FILE, "w"))
    print(f"\nSaved to {TOKEN_FILE}: publisher.py on this PC is ready.")
    print("For the cloud environment, add this as YT_REFRESH_TOKEN:\n" + tok)


def access_token():
    r = requests.post(TOKEN_URL, data={
        "client_id": env("YT_CLIENT_ID"), "client_secret": env("YT_CLIENT_SECRET"),
        "refresh_token": env("YT_REFRESH_TOKEN"), "grant_type": "refresh_token"}, timeout=30)
    if r.status_code != 200:
        sys.exit(f"token refresh failed: {r.status_code} {r.text}")
    return r.json()["access_token"]


# ---------- slots ----------

def _utc(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def taken_times(token):
    """Times (UTC) of the channel's recent uploads: scheduled publishAt or actual publish time.
    Covers Shorts made from other accounts too, since it reads the channel itself."""
    h = {"Authorization": f"Bearer {token}"}
    api = "https://www.googleapis.com/youtube/v3"
    r = requests.get(f"{api}/channels", params={"part": "contentDetails", "mine": "true"},
                     headers=h, timeout=30)
    r.raise_for_status()
    uploads = r.json()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    r = requests.get(f"{api}/playlistItems", params={
        "part": "contentDetails", "playlistId": uploads, "maxResults": 20}, headers=h, timeout=30)
    r.raise_for_status()
    ids = [i["contentDetails"]["videoId"] for i in r.json()["items"]]
    if not ids:
        return []
    r = requests.get(f"{api}/videos", params={"part": "status,snippet", "id": ",".join(ids)},
                     headers=h, timeout=30)
    r.raise_for_status()
    out = []
    for v in r.json()["items"]:
        st = v["status"]
        if st.get("publishAt"):
            out.append(_utc(st["publishAt"]))
        elif st.get("privacyStatus") == "public":
            out.append(_utc(v["snippet"]["publishedAt"]))
    return out


def next_slot(taken, now=None):
    """First slot (UTC, RFC3339) at least MIN_LEAD from now with no video within 90 min of it."""
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(SLOT_TZ)
    now = now or dt.datetime.now(dt.timezone.utc)
    day = now.astimezone(tz).date()
    for d in range(14):
        for s in SLOTS:
            hh, mm = map(int, s.split(":"))
            t = dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz) + dt.timedelta(days=d)
            t = t.astimezone(dt.timezone.utc)
            if t - now < MIN_LEAD:
                continue
            if all(abs(t - x) > dt.timedelta(minutes=90) for x in taken):
                return t.strftime("%Y-%m-%dT%H:%M:%SZ")
    sys.exit("no free slot in the next 14 days")


def slot_taken(at, taken, window=dt.timedelta(minutes=60)):
    t = _utc(at)
    return any(abs(t - x) < window for x in taken)


def slot_at(hhmm, now=None):
    """Next occurrence (UTC, RFC3339) of HH:MM Rome time, at least MIN_LEAD from now."""
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(SLOT_TZ)
    now = now or dt.datetime.now(dt.timezone.utc)
    hh, mm = map(int, hhmm.split(":"))
    day = now.astimezone(tz).date()
    for d in range(2):
        t = dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz) + dt.timedelta(days=d)
        if t.astimezone(dt.timezone.utc) - now >= MIN_LEAD:
            return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sys.exit(f"cannot schedule {hhmm}")


# ---------- upload ----------

def upload(video, meta, privacy, publish_at, token):
    status = {"privacyStatus": privacy, "selfDeclaredMadeForKids": False,
              "containsSyntheticMedia": False}  # real stream footage, no AI-generated media
    if publish_at:
        status["privacyStatus"] = "private"  # required by the API for scheduled videos
        status["publishAt"] = publish_at
    body = {"snippet": {**meta, "categoryId": CATEGORY_GAMING,
                        "defaultLanguage": "en", "defaultAudioLanguage": "en"},
            "status": status}
    size = os.path.getsize(video)
    h = {"Authorization": f"Bearer {token}"}
    r = requests.post(UPLOAD_URL, params={"uploadType": "resumable", "part": "snippet,status"},
                      headers={**h, "Content-Type": "application/json; charset=UTF-8",
                               "X-Upload-Content-Type": "video/mp4",
                               "X-Upload-Content-Length": str(size)},
                      data=json.dumps(body), timeout=60)
    if r.status_code != 200:
        sys.exit(f"upload init failed: {r.status_code} {r.text}")
    session = r.headers["Location"]
    with open(video, "rb") as f:
        r = requests.put(session, headers={**h, "Content-Type": "video/mp4"}, data=f, timeout=600)
    if r.status_code not in (200, 201):
        sys.exit(f"upload failed: {r.status_code} {r.text}")
    return r.json()["id"]


def calendar_reminder(script, url, publish_at, token):
    """Google Calendar event at the moment the Short goes public, with a phone pop-up, so the
    owner submits the link to the campaign within 30 minutes. Never blocks publishing."""
    cfg = os.path.join(HERE, "settings.json")
    if not (os.path.exists(cfg) and json.load(open(cfg, encoding="utf-8")).get("calendar_reminders")):
        return
    try:
        camp = campaign(script)
        start = _utc(publish_at)
        within = camp.get("submit_within_minutes", 30)
        body = {
            "summary": f"Invia link Short ({camp.get('streamer', '')}) entro {within} min",
            "description": (f"YouTube: {url}\n\nInvia qui: {camp.get('campaign_url', '')}\n\n"
                            f"TikTok/Instagram: testi nel file _upload.txt su Drive.\n{script['title']}"),
            "start": {"dateTime": start.strftime("%Y-%m-%dT%H:%M:%SZ")},
            "end": {"dateTime": (start + dt.timedelta(minutes=within)).strftime("%Y-%m-%dT%H:%M:%SZ")},
            "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 0}]},
        }
        r = requests.post(CALENDAR_URL, json=body, timeout=30,
                          headers={"Authorization": f"Bearer {token}"})
        if r.status_code >= 300:
            log(f"calendar reminder not created: {r.status_code} {r.text[:200]}")
        else:
            log("calendar reminder created")
    except Exception as e:  # noqa: BLE001 - a reminder must never break the upload
        log(f"calendar reminder failed: {e}")


def publish(d, a, token=None):
    d = os.path.abspath(d)
    script = json.load(open(os.path.join(d, "script.json"), encoding="utf-8"))
    slug = script["slug"]
    video = os.path.join(d, f"short_{slug}.mp4")
    done = os.path.join(d, "youtube.json")
    if not os.path.exists(video):
        log(f"skip {slug}: no video")
        return
    if os.path.exists(done) and not a.dry_run:
        log(f"skip {slug}: already published ({json.load(open(done))['url']})")
        return
    meta = build_metadata(script)
    with open(os.path.join(d, "youtube_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1, ensure_ascii=False)
    if a.dry_run:
        print(f"\nTITLE: {meta['title']}\n\n{meta['description']}\n\nTAGS: {', '.join(meta['tags'])}\n")
        return
    token = token or access_token()
    if a.slot == "auto" and not a.at:
        a.at = next_slot(taken_times(token))
        log(f"slot: {a.at}")
    elif a.slot and not a.at:
        a.at = slot_at(a.slot)
        log(f"slot {a.slot} Rome: {a.at}")
        if slot_taken(a.at, taken_times(token)):
            sys.exit(f"SLOT TAKEN: a Short is already scheduled/published around {a.at}; not uploading")
    log(f"uploading {slug} ({os.path.getsize(video) / 1e6:.1f} MB, "
        f"{'scheduled ' + a.at if a.at else a.privacy})")
    vid = upload(video, meta, a.privacy, a.at, token)
    url = f"https://youtube.com/shorts/{vid}"
    json.dump({"id": vid, "url": url, "privacy": a.privacy, "publish_at": a.at,
               "title": meta["title"]}, open(done, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    log(f"scheduled for {a.at}: {url}" if a.at else f"published: {url}")
    if a.at:
        calendar_reminder(script, url, a.at, token)
    return url


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?", help="output/<slug> folder made by agent.py")
    ap.add_argument("--all", action="store_true", help="publish every unpublished Short in output/")
    ap.add_argument("--auth", action="store_true", help="one-time login, prints YT_REFRESH_TOKEN")
    ap.add_argument("--privacy", default="public", choices=["public", "unlisted", "private"])
    ap.add_argument("--at", help="schedule, RFC3339 UTC e.g. 2026-11-18T17:00:00Z")
    ap.add_argument("--slot", help="'auto' = next free daily slot (SLOTS), or 'HH:MM' Rome time "
                                   "(e.g. 20:00 = next 20:00 Rome)")
    ap.add_argument("--dry-run", action="store_true", help="only build title/description/tags")
    ap.add_argument("--check-slot", metavar="HH:MM",
                    help="print FREE or TAKEN for the next HH:MM Rome slot, then exit")
    ap.add_argument("--test-calendar", action="store_true",
                    help="create a test reminder event 3 minutes from now")
    a = ap.parse_args()

    if a.auth:
        return auth_flow()
    if a.check_slot:
        at = slot_at(a.check_slot)
        taken = slot_taken(at, taken_times(access_token()))
        local = _utc(at).astimezone(__import__("zoneinfo").ZoneInfo(SLOT_TZ)).strftime("%Y-%m-%d %H:%M")
        print(f"{'TAKEN' if taken else 'FREE'} {local} Rome ({at})")
        return
    if a.test_calendar:
        at = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        test = {"campaign": next(iter(__import__("writer").campaigns())), "title": "TEST promemoria"}
        return calendar_reminder(test, "https://youtube.com/shorts/TEST", at, access_token())
    if a.all:
        folders = sorted(glob.glob(os.path.join(HERE, "output", "*", "script.json")))
        token = None if a.dry_run else access_token()
        for s in folders:
            publish(os.path.dirname(s), a, token)
            if a.slot:
                a.at = None  # each Short gets its own slot
    elif a.folder:
        publish(a.folder, a)
    else:
        ap.error("give a folder, --all or --auth")


if __name__ == "__main__":
    main()
