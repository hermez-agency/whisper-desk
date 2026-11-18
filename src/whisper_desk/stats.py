"""Usage statistics drawn from the history: words, speed, days in a row, top apps.

Wispr Flow counts on its servers; here the history already holds every
dictation, so the figures are worked out from it on the spot, and nothing is
stored besides. What the history no longer holds — purged, deleted, or never
written with `history = false` — is not counted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from . import focus
from .history import Entry

# A mark said aloud ("?", "«", "—") stands alone between spaces, and is no word.
WORD = re.compile(r"\w")
WEEK = 7
TOP_APPS = 3


@dataclass
class AppUsage:
    name: str                       # as the latest dictation into it wrote it
    dictations: int = 0
    words: int = 0


@dataclass
class Usage:
    dictations: int = 0
    words: int = 0
    words_today: int = 0
    words_week: int = 0             # today and the six days before
    days: int = 0                   # days with at least one dictation
    first: date | None = None
    listened: float = 0.0           # seconds, over the dictations that recorded it
    timed_words: int = 0            # the words of those dictations
    streak: int = 0                 # days in a row, up to today or yesterday
    best_streak: int = 0
    # Most words first; only the dictations whose app the desktop named.
    apps: list[AppUsage] = field(default_factory=list)
    app_words: int = 0              # the words of those dictations

    @property
    def words_per_minute(self) -> int | None:
        if self.listened <= 0 or not self.timed_words:
            return None
        return round(self.timed_words / (self.listened / 60))


def count_words(text: str) -> int:
    return sum(1 for token in text.split() if WORD.search(token))


def _streaks(days: set[date], today: date) -> tuple[int, int]:
    """The current run of days, and the longest one.

    A run that reached yesterday still holds: the day is not over, and a
    first dictation in the evening carries it on.
    """
    best = run = 0
    previous = None
    for day in sorted(days):
        run = run + 1 if previous is not None and day - previous == timedelta(days=1) else 1
        best = max(best, run)
        previous = day
    current = run if previous is not None and today - previous <= timedelta(days=1) else 0
    return current, best


def compute(entries: list[Entry], now: datetime | None = None) -> Usage:
    today = (now or datetime.now()).date()
    week_start = today - timedelta(days=WEEK - 1)
    usage = Usage()
    days: set[date] = set()
    apps: dict[str, AppUsage] = {}
    for entry in entries:
        words = count_words(entry.text)
        usage.dictations += 1
        usage.words += words
        if entry.app and focus.key(entry.app):
            # "Slack" and "slack" are one app, under the name it was last seen by.
            app = apps.setdefault(focus.key(entry.app), AppUsage(entry.app))
            app.name = entry.app
            app.dictations += 1
            app.words += words
            usage.app_words += words
        if entry.duration is not None and entry.duration > 0:
            usage.listened += entry.duration
            usage.timed_words += words
        when = entry.when
        if when is None:
            continue
        day = when.date()
        days.add(day)
        if day == today:
            usage.words_today += words
        if week_start <= day <= today:
            usage.words_week += words
    usage.days = len(days)
    usage.first = min(days) if days else None
    usage.streak, usage.best_streak = _streaks(days, today)
    # sorted() is stable: a tie goes to the app first dictated into.
    usage.apps = sorted(apps.values(), key=lambda app: (-app.words, -app.dictations))
    return usage


def _duration(seconds: float) -> str:
    minutes = round(seconds / 60)
    if minutes < 1:
        return f"{round(seconds)} s"
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60:02d} min"


def _days(count: int) -> str:
    return f"{count} day" if count == 1 else f"{count} days"


def report(usage: Usage) -> list[str]:
    """The figures as `whisper-desk stats` prints them, one line each."""
    since = f", since {usage.first.isoformat()}" if usage.first else ""
    lines = [
        f"Dictations  {usage.dictations:,} over {_days(usage.days)}{since}",
        f"Words       {usage.words:,} — {usage.words_today:,} today, "
        f"{usage.words_week:,} these {WEEK} days",
    ]
    speed = usage.words_per_minute
    if speed is None:
        lines.append("Speed       — (no listening time recorded)")
    else:
        lines.append(f"Speed       {speed:,} words per minute, "
                     f"over {_duration(usage.listened)} of dictation")
    lines.append(f"Streak      {_days(usage.streak)} in a row (best: {_days(usage.best_streak)})")
    if usage.apps:
        shares = ", ".join(
            f"{app.name} {_share(app.words, usage.app_words)}" for app in usage.apps[:TOP_APPS]
        )
        lines.append(f"Top apps    {shares}")
    return lines


def _share(part: int, whole: int) -> str:
    return f"{round(100 * part / whole)} %" if whole else "—"


def as_dict(usage: Usage) -> dict:
    """The same figures for a script or a status bar."""
    return {
        "dictations": usage.dictations,
        "words": usage.words,
        "words_today": usage.words_today,
        "words_week": usage.words_week,
        "days": usage.days,
        "first": usage.first.isoformat() if usage.first else None,
        "seconds": round(usage.listened, 1),
        "words_per_minute": usage.words_per_minute,
        "streak": usage.streak,
        "best_streak": usage.best_streak,
        "apps": [
            {"app": app.name, "dictations": app.dictations, "words": app.words}
            for app in usage.apps
        ],
    }
