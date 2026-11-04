import threading
import time
import warnings
from collections import deque

import numpy as np

SAMPLE_RATE = 48000
BLOCK = 1024
FFT_SIZE = 2048
BANDS = 24
MIN_FREQ, MAX_FREQ = 40, 12000
BASS_FREQ = (40, 160)
# Levels are shown relative to the recent peak, so the wave looks the same at any system volume.
DYNAMIC_RANGE_DB = 45.0
PEAK_DECAY_DB = 0.05
SILENCE_RMS = 1e-4
BEAT_RATIO = 1.45
BEAT_MIN_INTERVAL = 0.22
DEVICE_CHECK_SECONDS = 3.0
STALE_SECONDS = 0.25
# Tempo is the median gap between recent bass hits, folded into this range (half/double time are the same beat).
TEMPO_RANGE = (70.0, 180.0)
TEMPO_WINDOW_SECONDS = 8.0
TEMPO_MIN_BEATS = 5


class AudioSpectrum:
    """Listens to the audio of one program (process loopback), or to everything the default output
    device plays when `process` is empty, and keeps per-band levels plus the time of the last bass hit."""

    def __init__(self, process=""):
        self._process = process
        self._lock = threading.Lock()
        self._levels = np.zeros(BANDS)
        self._beat_time = 0.0
        self._beats = deque(maxlen=32)
        self._updated = 0.0
        self._running = True

        freqs = np.fft.rfftfreq(FFT_SIZE, 1 / SAMPLE_RATE)
        edges = np.searchsorted(freqs, np.geomspace(MIN_FREQ, MAX_FREQ, BANDS + 1))
        self._ranges = []
        for low, high in zip(edges[:-1], edges[1:]):
            self._ranges.append((low, max(high, low + 1)))
        self._bass = slice(*np.searchsorted(freqs, BASS_FREQ))
        self._window = np.hanning(FFT_SIZE)
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._running = False

    def snapshot(self):
        """(levels 0..1 per band, seconds since the last beat) or None when nothing is playing."""
        with self._lock:
            if time.monotonic() - self._updated > STALE_SECONDS:
                return None
            return self._levels.copy(), time.monotonic() - self._beat_time

    def tempo(self):
        """(beats per minute, monotonic time of the last beat), or None while there is no steady beat."""
        now = time.monotonic()
        with self._lock:
            beats = [b for b in self._beats if now - b < TEMPO_WINDOW_SECONDS]
            last = self._beat_time
        if len(beats) < TEMPO_MIN_BEATS or now - beats[-1] > 2.0:
            return None
        low, high = TEMPO_RANGE
        folded = []
        for gap in np.diff(beats):
            bpm = 60.0 / gap
            while bpm < low:
                bpm *= 2
            while bpm > high:
                bpm /= 2
            folded.append(bpm)
        return float(np.median(folded)), last

    def _run(self):
        import soundcard

        # soundcard warns on every gap in the loopback stream, which happens whenever playback pauses.
        warnings.filterwarnings("ignore", module="soundcard")
        while self._running:
            try:
                if self._process:
                    self._capture_process()
                else:
                    self._capture(soundcard)
            except Exception:
                time.sleep(2)

    def _capture_process(self):
        from modules.process_audio import ProcessLoopback, find_root_process, process_alive

        pid = find_root_process(self._process)
        if pid is None:
            time.sleep(2)
            return
        self._reset_analysis()
        pending = []
        pending_frames = 0
        last_check = time.monotonic()
        with ProcessLoopback(pid, SAMPLE_RATE) as capture:
            while self._running:
                mono = capture.read()
                now = time.monotonic()
                if now - last_check > DEVICE_CHECK_SECONDS:
                    last_check = now
                    if not process_alive(pid):
                        return
                if mono is None or not len(mono):
                    continue
                # Packets are ~10 ms; analysing them in BLOCK-sized portions keeps the smoothing the same as before.
                pending.append(mono)
                pending_frames += len(mono)
                if pending_frames >= BLOCK:
                    self._analyse(np.concatenate(pending), now)
                    pending, pending_frames = [], 0

    def _capture(self, soundcard):
        speaker = soundcard.default_speaker()
        loopback = soundcard.get_microphone(id=str(speaker.name), include_loopback=True)
        self._reset_analysis()
        last_check = time.monotonic()
        with loopback.recorder(samplerate=SAMPLE_RATE, channels=2, blocksize=BLOCK) as recorder:
            while self._running:
                data = recorder.record(numframes=BLOCK)
                now = time.monotonic()
                if now - last_check > DEVICE_CHECK_SECONDS:
                    last_check = now
                    if soundcard.default_speaker().name != speaker.name:
                        return
                self._analyse(data.mean(axis=1) if data.ndim == 2 else data, now)

    def _reset_analysis(self):
        self._samples = np.zeros(FFT_SIZE)
        self._peak_db = -60.0
        self._bass_average = 0.0

    def _analyse(self, mono, now):
        self._samples = np.concatenate((self._samples[len(mono):], mono))[-FFT_SIZE:]
        if np.sqrt(np.mean(mono ** 2)) < SILENCE_RMS:
            levels = np.zeros(BANDS)
        else:
            spectrum = np.abs(np.fft.rfft(self._samples * self._window))
            bands = np.array([spectrum[low:high].mean() for low, high in self._ranges])
            db = 20 * np.log10(bands + 1e-9)
            self._peak_db = max(db.max(), self._peak_db - PEAK_DECAY_DB)
            levels = np.clip((db - (self._peak_db - DYNAMIC_RANGE_DB)) / DYNAMIC_RANGE_DB, 0.0, 1.0) ** 1.6

            bass = float(np.mean(spectrum[self._bass] ** 2))
            if bass > self._bass_average * BEAT_RATIO and now - self._beat_time > BEAT_MIN_INTERVAL:
                with self._lock:
                    self._beat_time = now
                    self._beats.append(now)
            self._bass_average = self._bass_average * 0.93 + bass * 0.07
        with self._lock:
            self._levels = levels
            self._updated = now
