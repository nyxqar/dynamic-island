import bisect
import hashlib
import json
import math
import os
import re
import threading
import time
import unicodedata
from dataclasses import dataclass

import httpx
from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from config import BASE_DIR
from modules.romaja import romanize_text
from ui.theme import base_font

LRCLIB_URL = "https://lrclib.net/api/get"
LRCLIB_SEARCH_URL = "https://lrclib.net/api/search"
SPICY_URL = "https://api.spicylyrics.org/v1/lyrics/{}"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_SEARCH_URL = "https://api.spotify.com/v1/search"
CACHE_DIR = BASE_DIR / "cache" / "lyrics"
# 3: tracks that only had plain lyrics were cached as empty before, so they must be fetched again.
CACHE_VERSION = 3
CACHE_LIMIT = 25 * 1024 * 1024
# "No lyrics" is only trusted for a day: lrclib gets new uploads all the time.
EMPTY_CACHE_SECONDS = 24 * 3600
REQUEST_TIMEOUT = 5.0
# lrclib.net regularly answers 503 "ServerOverloaded"; without retries a track would stay without lyrics.
RETRY_DELAYS = (5, 15, 30, 60)
# A Spotify search hit whose length differs more than this is a different recording (live, remix, edit).
DURATION_TOLERANCE = 3.0
LAST_LINE_SECONDS = 5.0
INTERLUDE_MIN_SECONDS = 3.0
TIMESTAMP = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
# Plain lyrics without a known duration scroll at this pace.
PLAIN_LINE_SECONDS = 4.0
_TITLE_NOISE = r"feat|ft|with|remaster(?:ed)?|live|version|edit|mix|mono|stereo|deluxe|bonus|explicit|acoustic"
TITLE_BRACKETS = re.compile(rf"\s*[(\[][^)\]]*\b(?:{_TITLE_NOISE})\b[^)\]]*[)\]]", re.IGNORECASE)
TITLE_SUFFIX = re.compile(rf"\s+-\s+[^-]*\b(?:{_TITLE_NOISE})\b.*$", re.IGNORECASE)
# "&" and " x " are left alone: they are part of many band names (Simon & Garfunkel).
ARTIST_SEPARATOR = re.compile(r",|;|\s(?:feat\.?|ft\.?|with)\s", re.IGNORECASE)


@dataclass
class Line:
    start: float
    end: float
    # (start, end, text, joined): joined means the syllable continues into the next one without a space.
    words: list
    word_synced: bool
    # False for plain lyrics: start/end only spread the lines over the track for scrolling.
    timed: bool = True


def line_from_text(start, end, text, timed=True):
    return Line(start, end, [(start, end, word, False) for word in text.split()], False, timed)


def plain_lines(text, duration):
    rows = [row.strip() for row in text.splitlines() if row.strip()]
    if not rows:
        return []
    step = (duration if duration > 0 else len(rows) * PLAIN_LINE_SECONDS) / len(rows)
    return [line_from_text(i * step, (i + 1) * step, row, timed=False) for i, row in enumerate(rows)]


def clean_title(title):
    """Drops "(feat. X)", "- Remastered 2011" and the like, which make exact lookups miss."""
    return TITLE_SUFFIX.sub("", TITLE_BRACKETS.sub("", title)).strip() or title


def main_artist(artist):
    return ARTIST_SEPARATOR.split(artist, 1)[0].strip() or artist


def parse_lrc(text):
    stamps = []
    for raw in text.splitlines():
        lyric = TIMESTAMP.sub("", raw).strip()
        for minutes, seconds in TIMESTAMP.findall(raw):
            stamps.append((int(minutes) * 60 + float(seconds), lyric))
    stamps.sort(key=lambda stamp: stamp[0])
    lines = []
    for i, (start, lyric) in enumerate(stamps):
        if not lyric:
            continue
        end = stamps[i + 1][0] if i + 1 < len(stamps) else start + LAST_LINE_SECONDS
        lines.append(line_from_text(start, end, lyric))
    return lines


def parse_spicy(body):
    kind = body.get("Type")
    lines = []
    for item in body.get("Content") or []:
        if item.get("Type") != "Vocal":
            continue
        if kind == "Syllable":
            words = [
                (float(s["StartTime"]), float(s["EndTime"]), s["Text"], bool(s.get("IsPartOfWord")))
                for s in (item.get("Lead") or {}).get("Syllables") or []
                if s.get("Text", "").strip()
            ]
            if words:
                lines.append(Line(words[0][0], max(w[1] for w in words), words, True))
        elif kind == "Line":
            text = (item.get("Text") or "").strip()
            if text:
                lines.append(line_from_text(float(item["StartTime"]), float(item["EndTime"]), text))
    return lines


def track_key(title, artist, album, duration):
    return f"v{CACHE_VERSION}\n{artist}\n{title}\n{album}\n{round(duration)}"


def _normalize(text):
    text = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in text if c.isalnum())


def load_env_file(path):
    values = {}
    if not path:
        return values
    try:
        with open(path, encoding="utf-8-sig") as f:
            for raw in f:
                raw = raw.strip()
                if not raw or raw.startswith("#") or "=" not in raw:
                    continue
                name, value = raw.split("=", 1)
                values[name.strip()] = value.strip().strip("\"'")
    except OSError:
        pass
    return values


class SpotifySearch:
    """Finds the Spotify track id for what SMTC reports; Spicy Lyrics is keyed by that id."""

    def __init__(self, client_id, client_secret):
        self._auth = (client_id, client_secret)
        self._lock = threading.Lock()
        self._token = None
        self._expires = 0.0

    def _access_token(self):
        with self._lock:
            if self._token and time.monotonic() < self._expires - 60:
                return self._token
            response = httpx.post(
                SPOTIFY_TOKEN_URL, data={"grant_type": "client_credentials"}, auth=self._auth,
                timeout=REQUEST_TIMEOUT, trust_env=False,
            )
            response.raise_for_status()
            data = response.json()
            self._token = data["access_token"]
            self._expires = time.monotonic() + float(data.get("expires_in", 3600))
            return self._token

    def find(self, title, artist, duration):
        """Track id, "" when Spotify has no such track, None on a network/API error."""
        clean = lambda text: text.replace('"', " ").strip()
        query = f"track:{clean(title)}"
        if artist:
            query += f" artist:{clean(artist.split(',')[0])}"
        try:
            response = httpx.get(
                SPOTIFY_SEARCH_URL, params={"q": query, "type": "track", "limit": 5},
                headers={"Authorization": f"Bearer {self._access_token()}"},
                timeout=REQUEST_TIMEOUT, trust_env=False,
            )
            if response.status_code == 401:
                self._token = None
            response.raise_for_status()
            items = response.json()["tracks"]["items"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return None
        return self._pick(items, title, duration)

    @staticmethod
    def _pick(items, title, duration):
        wanted = _normalize(title)
        best, best_diff = "", None
        for item in items:
            name = _normalize(item.get("name", ""))
            diff = abs(item.get("duration_ms", 0) / 1000 - duration) if duration > 0 else 0.0
            name_ok = bool(name) and (name.startswith(wanted) or wanted.startswith(name))
            if diff > DURATION_TOLERANCE or not (name_ok or diff <= 1.0):
                continue
            if best_diff is None or diff < best_diff:
                best, best_diff = item["id"], diff
        return best


class LyricsProvider(QObject):
    loaded = Signal(str, object)

    def __init__(self, settings):
        super().__init__()
        self._cache_lock = threading.Lock()
        self._current_key = None
        env = load_env_file(settings.get("env_file") or BASE_DIR / ".env")
        secret = lambda name: os.environ.get(name) or env.get(name) or ""
        self._spicy_key = secret("SPICY_LYRICS_SECRET_KEY")
        client_id, client_secret = secret("SPOTIFY_CLIENT_ID"), secret("SPOTIFY_CLIENT_SECRET")
        self._spotify = SpotifySearch(client_id, client_secret) if client_id and client_secret else None

    def request(self, title, artist, album, duration):
        key = track_key(title, artist, album, duration)
        self._current_key = key
        threading.Thread(
            target=self._fetch, args=(key, title, artist, album, duration), daemon=True
        ).start()
        return key

    def _fetch(self, key, title, artist, album, duration):
        lines = self._read_cache(key)
        delays = iter(RETRY_DELAYS)
        while lines is None:
            lines, complete = self._download(title, artist, album, duration)
            if lines is not None:
                if complete:
                    self._write_cache(key, lines)
                break
            delay = next(delays, None)
            if delay is None:
                break
            time.sleep(delay)
            if key != self._current_key:
                return
        self.loaded.emit(key, lines or [])

    def _download(self, title, artist, album, duration):
        """(lines, complete): lines is None when nothing was found but a source failed;
        complete is False when a better source failed, so the result must not be cached."""
        complete = True
        if self._spicy_key and self._spotify:
            track_id = self._spotify.find(title, artist, duration)
            if track_id is None:
                complete = False
            elif track_id:
                lines = self._spicy(track_id)
                if lines is None:
                    complete = False
                elif lines:
                    return lines, True
        result = self._lrclib(title, artist, album, duration)
        if result is None:
            return None, False
        synced, plain, lrclib_complete = result
        complete = complete and lrclib_complete
        lines = synced or plain
        if lines:
            return lines, complete
        if not complete:
            return None, False
        return [], True

    def _spicy(self, track_id):
        try:
            response = httpx.get(
                SPICY_URL.format(track_id), headers={"Authorization": f"Bearer {self._spicy_key}"},
                timeout=REQUEST_TIMEOUT * 2, trust_env=False,
            )
        except httpx.HTTPError:
            return None
        if response.status_code == 404:
            return []
        if response.status_code != 200:
            return None
        try:
            return parse_spicy(response.json()["Body"])
        except (ValueError, KeyError, TypeError, AttributeError):
            return None

    @classmethod
    def _lrclib(cls, title, artist, album, duration):
        """(synced lines, plain lines, complete); None when lrclib could not be reached at all.
        The exact lookup misses on any difference in title, album or length, so a search
        by the cleaned-up title follows when it has no synced lyrics."""
        params = {"track_name": title, "artist_name": artist}
        if album:
            params["album_name"] = album
        if duration > 0:
            params["duration"] = round(duration)
        record = cls._lrclib_call(LRCLIB_URL, params)
        if isinstance(record, dict) and isinstance(record.get("syncedLyrics"), str) and record["syncedLyrics"]:
            return parse_lrc(record["syncedLyrics"]), [], True

        found = cls._lrclib_call(
            LRCLIB_SEARCH_URL, {"track_name": clean_title(title), "artist_name": main_artist(artist)}
        )
        candidates = [(0.0, record)] if isinstance(record, dict) and record else []
        candidates += cls._lrclib_matches(found, title, duration)
        complete = record is not None and found is not None
        synced = plain = []
        for diff, item in candidates:
            if item.get("instrumental"):
                continue
            text = item.get("syncedLyrics")
            if not synced and diff <= DURATION_TOLERANCE and isinstance(text, str) and text:
                synced = parse_lrc(text)
            text = item.get("plainLyrics")
            if not plain and isinstance(text, str) and text:
                plain = plain_lines(text, duration)
        if not (synced or plain) and not complete:
            return None
        return synced, plain, complete

    @staticmethod
    def _lrclib_call(url, params):
        """Parsed JSON, {} for 404, None on a network/API error."""
        try:
            # trust_env=False: ignore proxy/certificate settings from environment variables,
            # so the request can only go directly to the API host.
            response = httpx.get(url, params=params, timeout=REQUEST_TIMEOUT, trust_env=False)
        except httpx.HTTPError:
            return None
        if response.status_code == 404:
            return {}
        if response.status_code != 200:
            return None
        try:
            return response.json()
        except ValueError:
            return None

    @staticmethod
    def _lrclib_matches(found, title, duration):
        """Search results with the same title as (length difference, record), closest length first."""
        if not isinstance(found, list):
            return []
        wanted = _normalize(clean_title(title))
        matches = []
        for item in found:
            if not isinstance(item, dict):
                continue
            name = _normalize(clean_title(item.get("trackName") or ""))
            if not name or not (name.startswith(wanted) or wanted.startswith(name)):
                continue
            length = item.get("duration") or 0
            diff = abs(length - duration) if duration > 0 and length else 0.0
            matches.append((diff, item))
        matches.sort(key=lambda match: match[0])
        return matches

    @staticmethod
    def _cache_path(key):
        return CACHE_DIR / (hashlib.sha256(key.encode("utf-8")).hexdigest()[:32] + ".json")

    def _read_cache(self, key):
        path = self._cache_path(key)
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
            # The file mtime is refreshed on every read for the LRU trim, so the age is stored inside.
            if not data["lines"] and time.time() - data.get("saved", 0) > EMPTY_CACHE_SECONDS:
                return None
            os.utime(path)
            return [
                Line(s, e, [tuple(w) for w in words], synced, *rest)
                for s, e, words, synced, *rest in data["lines"]
            ]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None

    def _write_cache(self, key, lines):
        data = {"key": key, "saved": time.time(), "lines":[[l.start, l.end, l.words, l.word_synced, l.timed] for l in lines]}
        with self._cache_lock:
            try:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                with self._cache_path(key).open("w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                self._trim_cache()
            except OSError:
                pass

    @staticmethod
    def _trim_cache():
        files = []
        for path in CACHE_DIR.glob("*.json"):
            stat = path.stat()
            files.append((stat.st_mtime, stat.st_size, path))
        files.sort()
        total = sum(size for _, size, _ in files)
        for _, size, path in files:
            if total <= CACHE_LIMIT:
                break
            path.unlink(missing_ok=True)
            total -= size


class ElidedLabel(QLabel):
    def __init__(self, pixel_size, weight=QFont.Normal, color="white", alignment=Qt.AlignLeft | Qt.AlignVCenter):
        super().__init__(alignment=alignment)
        font = base_font()
        font.setPixelSize(pixel_size)
        font.setWeight(weight)
        self.setFont(font)
        self.setStyleSheet(f"color: {color}; background: transparent;")
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._full_text = ""

    def set_full_text(self, text):
        if text != self._full_text:
            self._full_text = text
            self._elide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def _elide(self):
        self.setText(self.fontMetrics().elidedText(self._full_text, Qt.ElideRight, self.width()))


@dataclass
class _Item:
    start: float
    end: float
    line: Line | None  # None for an instrumental break, drawn as three dots
    glyphs: list = None  # (word index, x, row, width)
    y: float = 0.0
    height: float = 0.0


def _ease(value):
    return 1 - (1 - value) ** 3


def _clamp(value):
    return min(max(value, 0.0), 1.0)


class LyricsView(QWidget):
    """Karaoke view in the style of Spicy Lyrics / Beautiful Lyrics: the current line is scrolled
    to the middle, syllables fill with a soft edge and lift slightly while sung, long notes swell."""

    DIM_ALPHA = 85
    PLAIN_ALPHA = 200

    def __init__(self, scale, offset_ms, centered=True, parent=None):
        super().__init__(parent)
        self.scale = scale
        self.centered = centered
        self.offset = offset_ms / 1000
        self.font = base_font()
        self.font.setPixelSize(round(15 * scale))
        self.font.setWeight(QFont.Bold)
        self.metrics = QFontMetricsF(self.font)
        self.row_height = self.metrics.lineSpacing()
        self.gap = 5 * scale
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.setMinimumHeight(round(60 * scale))

        self.items = []
        self.starts = []
        self.fallback = ""
        self.plain = False
        self._lines = []
        self.romaja = False
        self._laid_out_width = None
        self._position = 0.0
        self._position_time = time.monotonic()
        self._playing = False
        self._scroll = None
        self._activeness = {}
        self._last_frame = time.monotonic()
        self.timer = QTimer(self, interval=16, timeout=self._frame)
        self.timer.setTimerType(Qt.PreciseTimer)

    def set_lines(self, lines, fallback):
        self._lines = lines
        self.fallback = fallback
        self._rebuild()

    def set_romaja(self, enabled):
        self.romaja = enabled
        self._rebuild()

    def _rebuild(self):
        items = []
        previous_end = 0.0
        self.plain = bool(self._lines) and not self._lines[0].timed
        for line in self._lines:
            shown = self._romanized(line) if self.romaja else line
            if not self.plain and line.start - previous_end >= INTERLUDE_MIN_SECONDS:
                items.append(_Item(previous_end, line.start, None))
            items.append(_Item(line.start, line.end, shown))
            previous_end = max(previous_end, line.end)
        self.items = items
        self.starts = [item.start for item in items]
        self._laid_out_width = None
        self._scroll = None
        self._activeness = {}
        self._sync_timer()
        self.update()

    @staticmethod
    def _romanized(line):
        words = [(start, end, romanize_text(text), joined) for start, end, text, joined in line.words]
        return Line(line.start, line.end, words, line.word_synced, line.timed)

    def update_position(self, position, playing):
        self._position = position
        self._position_time = time.monotonic()
        self._playing = playing

    def _now(self):
        elapsed = time.monotonic() - self._position_time if self._playing else 0.0
        return self._position + elapsed + self.offset

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_timer()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.timer.stop()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._laid_out_width = None

    def _sync_timer(self):
        if self.items and self.isVisible():
            if not self.timer.isActive():
                self._last_frame = time.monotonic()
                self.timer.start()
        else:
            self.timer.stop()

    def _layout(self):
        width = self.width()
        if width == self._laid_out_width:
            return
        self._laid_out_width = width
        space = self.metrics.horizontalAdvance(" ")
        y = 0.0
        for item in self.items:
            if item.line is None:
                item.glyphs, item.height = [], self.row_height * 0.8
            else:
                item.glyphs, rows = self._wrap(item.line.words, width, space)
                item.height = rows * self.row_height
            item.y = y
            y += item.height + self.gap

    def _wrap(self, words, width, space):
        # Syllables are grouped into words so a line only breaks between words.
        groups, current = [], []
        for index, word in enumerate(words):
            current.append(index)
            if not word[3]:
                groups.append(current)
                current = []
        if current:
            groups.append(current)

        rows, row, row_width = [], [], 0.0
        for group in groups:
            widths = [self.metrics.horizontalAdvance(words[i][2]) for i in group]
            group_width = sum(widths)
            if row and row_width + space + group_width > width:
                rows.append((row, row_width))
                row, row_width = [], 0.0
            if row:
                row_width += space
            for i, w in zip(group, widths):
                row.append((i, row_width, w))
                row_width += w
        if row:
            rows.append((row, row_width))

        glyphs = []
        for row_index, (row, row_width) in enumerate(rows):
            left = (width - row_width) / 2 if self.centered else 0.0
            glyphs.extend((i, left + x, row_index, w) for i, x, w in row)
        return glyphs, max(len(rows), 1)

    def _current_index(self, now):
        return bisect.bisect_right(self.starts, now) - 1

    def _frame(self):
        if not self.items:
            return
        self._layout()
        frame_time = time.monotonic()
        dt = min(frame_time - self._last_frame, 0.1)
        self._last_frame = frame_time
        now = self._now()
        index = self._current_index(now)
        target_item = self.items[max(index, 0)]
        target = target_item.y + target_item.height / 2
        if self.plain:
            # Untimed lyrics glide through the text in proportion to the playback position.
            share = _clamp((now - target_item.start) / max(target_item.end - target_item.start, 0.001))
            target = target_item.y + (target_item.height + self.gap) * share
        if self._scroll is None or abs(target - self._scroll) > self.height() * 4:
            self._scroll = target
        self._scroll += (target - self._scroll) * (1 - math.exp(-dt * 9))

        settled = abs(target - self._scroll) < 0.05
        if self.plain:
            if self._playing or not settled:
                self.update()
            return
        follow = 1 - math.exp(-dt * 10)
        for i in set(self._activeness) | {index}:
            goal = 1.0 if i == index else 0.0
            value = self._activeness.get(i, 0.0)
            value += (goal - value) * follow
            if abs(goal - value) < 0.002:
                value = goal
            else:
                settled = False
            if value == 0.0:
                self._activeness.pop(i, None)
            else:
                self._activeness[i] = value
        if self._playing or not settled:
            self.update()

    def paintEvent(self, event):
        if not self.items:
            self._paint_fallback()
            return
        self._layout()
        if self._scroll is None:
            self._frame()
        ratio = self.devicePixelRatioF()
        image = QImage(round(self.width() * ratio), round(self.height() * ratio), QImage.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(ratio)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setFont(self.font)

        now = self._now()
        index = self._current_index(now)
        origin = self.height() / 2 - self._scroll
        for i, item in enumerate(self.items):
            top = origin + item.y
            if top > self.height() or top + item.height < 0:
                continue
            if self.plain:
                self._paint_plain(painter, item, top)
                continue
            active = self._activeness.get(i, 0.0)
            painter.save()
            center = QPointF(self.width() / 2 if self.centered else 0.0, top + item.height / 2)
            painter.translate(center)
            zoom = 0.9 + 0.1 * active
            painter.scale(zoom, zoom)
            painter.translate(-center)
            if item.line is None:
                self._paint_interlude(painter, item, top, now, active)
            else:
                self._paint_line(painter, item, top, now, active, i == index)
            painter.restore()

        # Lines fade out towards the top and bottom edges instead of being cut off.
        fade = min(self.height() * 0.3, 22 * self.scale)
        mask = QLinearGradient(0, 0, 0, self.height())
        edge = fade / max(self.height(), 1)
        mask.setColorAt(0, QColor(0, 0, 0, 0))
        mask.setColorAt(edge, QColor(0, 0, 0, 255))
        mask.setColorAt(1 - edge, QColor(0, 0, 0, 255))
        mask.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        painter.fillRect(QRectF(0, 0, self.width(), self.height()), mask)
        painter.end()
        QPainter(self).drawImage(0, 0, image)

    def _paint_line(self, painter, item, top, now, active, is_current):
        line = item.line
        dim = self.DIM_ALPHA
        bright = round(dim + (255 - dim) * active)
        ascent = self.metrics.ascent()
        lift = 1.6 * self.scale
        soft_edge = 8 * self.scale
        for word_index, x, row, width in item.glyphs:
            start, end, text, _ = line.words[word_index]
            if not is_current and active == 0.0:
                progress = 0.0
            elif not line.word_synced:
                progress = 1.0
            else:
                progress = _clamp((now - start) / max(end - start, 0.001))
            baseline = top + row * self.row_height + ascent
            painter.save()
            if line.word_synced and active > 0:
                baseline -= lift * _ease(progress) * active
                # A long note swells while it is held, like the emphasis in Beautiful Lyrics.
                if end - start >= 1.0 and 0 < progress < 1:
                    swell = 1 + 0.07 * math.sin(math.pi * progress) * active
                    pivot = QPointF(x + width / 2, baseline - ascent / 2)
                    painter.translate(pivot)
                    painter.scale(swell, swell)
                    painter.translate(-pivot)
            if progress <= 0:
                brush = QColor(255, 255, 255, dim)
            elif progress >= 1:
                brush = QColor(255, 255, 255, bright)
            else:
                brush = QLinearGradient(x, 0, x + width, 0)
                edge = min(soft_edge / max(width, 1), 0.45)
                head = progress * (1 + 2 * edge) - edge
                lit, unlit = _clamp(head - edge), _clamp(head + edge)
                if unlit <= lit:
                    lit, unlit = max(lit - 0.001, 0.0), min(lit + 0.001, 1.0)
                brush.setColorAt(0, QColor(255, 255, 255, bright))
                brush.setColorAt(lit, QColor(255, 255, 255, bright))
                brush.setColorAt(unlit, QColor(255, 255, 255, dim))
                brush.setColorAt(1, QColor(255, 255, 255, dim))
            painter.setPen(QPen(brush, 0))
            painter.drawText(QPointF(x, baseline), text)
            painter.restore()

    def _paint_plain(self, painter, item, top):
        painter.setPen(QColor(255, 255, 255, self.PLAIN_ALPHA))
        ascent = self.metrics.ascent()
        for word_index, x, row, _ in item.glyphs:
            painter.drawText(QPointF(x, top + row * self.row_height + ascent), item.line.words[word_index][2])

    def _paint_interlude(self, painter, item, top, now, active):
        if active <= 0:
            return
        s = self.scale
        progress = _clamp((now - item.start) / max(item.end - item.start, 0.001))
        breath = 1 + 0.12 * math.sin(now * math.tau / 1.6)
        # The dots shrink away in the last moment before the next line starts.
        ending = _clamp((item.end - now) / 0.4)
        radius = 2.6 * s * breath * ending
        cy = top + item.height / 2
        painter.setPen(Qt.NoPen)
        for i in range(3):
            fill = _clamp(progress * 3 - i)
            alpha = round((self.DIM_ALPHA + (255 - self.DIM_ALPHA) * fill) * active)
            painter.setBrush(QColor(255, 255, 255, alpha))
            cx = self.width() / 2 + (i - 1) * 9 * s if self.centered else (4 + i * 9) * s
            painter.drawEllipse(QPointF(cx, cy), radius, radius)

    def _paint_fallback(self):
        if not self.fallback:
            return
        painter = QPainter(self)
        font = QFont(self.font)
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255, 200))
        text = painter.fontMetrics().elidedText(self.fallback, Qt.ElideRight, self.width())
        alignment = Qt.AlignCenter if self.centered else Qt.AlignLeft | Qt.AlignVCenter
        painter.drawText(self.rect(), alignment, text)
