import threading
import time
import warnings

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


class AudioSpectrum:
    """Listens to whatever the default output device plays (WASAPI loopback) and keeps
    per-band levels plus the time of the last bass hit."""

    def __init__(self):
        self._lock = threading.Lock()
        self._levels = np.zeros(BANDS)
        self._beat_time = 0.0
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

    def _run(self):
        import soundcard

        # soundcard warns on every gap in the loopback stream, which happens whenever playback pauses.
        warnings.filterwarnings("ignore", module="soundcard")
        while self._running:
            try:
                self._capture(soundcard)
            except Exception:
                time.sleep(2)

    def _capture(self, soundcard):
        speaker = soundcard.default_speaker()
        loopback = soundcard.get_microphone(id=str(speaker.name), include_loopback=True)
        samples = np.zeros(FFT_SIZE)
        peak_db = -60.0
        bass_average = 0.0
        last_check = time.monotonic()
        with loopback.recorder(samplerate=SAMPLE_RATE, channels=2, blocksize=BLOCK) as recorder:
            while self._running:
                data = recorder.record(numframes=BLOCK)
                now = time.monotonic()
                if now - last_check > DEVICE_CHECK_SECONDS:
                    last_check = now
                    if soundcard.default_speaker().name != speaker.name:
                        return
                mono = data.mean(axis=1) if data.ndim == 2 else data
                samples = np.concatenate((samples[len(mono):], mono))[-FFT_SIZE:]
                if np.sqrt(np.mean(mono ** 2)) < SILENCE_RMS:
                    levels = np.zeros(BANDS)
                else:
                    spectrum = np.abs(np.fft.rfft(samples * self._window))
                    bands = np.array([spectrum[low:high].mean() for low, high in self._ranges])
                    db = 20 * np.log10(bands + 1e-9)
                    peak_db = max(db.max(), peak_db - PEAK_DECAY_DB)
                    levels = np.clip((db - (peak_db - DYNAMIC_RANGE_DB)) / DYNAMIC_RANGE_DB, 0.0, 1.0) ** 1.6

                    bass = float(np.mean(spectrum[self._bass] ** 2))
                    if bass > bass_average * BEAT_RATIO and now - self._beat_time > BEAT_MIN_INTERVAL:
                        self._beat_time = now
                    bass_average = bass_average * 0.93 + bass * 0.07
                with self._lock:
                    self._levels = levels
                    self._updated = now
