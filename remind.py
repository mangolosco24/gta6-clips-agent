#!/usr/bin/env python3
"""Reminder at publish time: prints the phone notification text for Shorts that went public on
YouTube in the last N minutes (scheduled by publisher.py), so the owner can submit the link to the
campaign within 30 minutes.

  python remind.py               # Shorts that went public in the last 20 minutes
  python remind.py --minutes 60

Prints one line per Short (< 200 chars, ready for a push notification), or nothing.
"""
import argparse
import datetime as dt
import glob
import json
import os

from writer import campaigns

HERE = os.path.dirname(os.path.abspath(__file__))


def due(minutes):
    now = dt.datetime.now(dt.timezone.utc)
    out = []
    for f in glob.glob(os.path.join(HERE, "output", "*", "youtube.json")):
        yt = json.load(open(f, encoding="utf-8-sig"))
        if not yt.get("publish_at"):
            continue
        t = dt.datetime.fromisoformat(yt["publish_at"].replace("Z", "+00:00"))
        if dt.timedelta(0) <= now - t <= dt.timedelta(minutes=minutes):
            script = json.load(open(os.path.join(os.path.dirname(f), "script.json"), encoding="utf-8"))
            out.append((t, yt["url"], campaigns().get(script["campaign"], {})))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=int, default=20)
    a = ap.parse_args()
    for t, url, camp in sorted(due(a.minutes), key=lambda x: x[0]):
        from zoneinfo import ZoneInfo
        deadline = (t + dt.timedelta(minutes=30)).astimezone(ZoneInfo("Europe/Rome")).strftime("%H:%M")
        print(f"Invia entro le {deadline} ({camp.get('streamer', '?')}): {url} -> "
              f"{camp.get('campaign_url', '')}")
