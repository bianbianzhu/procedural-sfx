"""sfxkit — building blocks for procedural sound effects (numpy + scipy).

Every generator returns a mono float64 array at SR. Stereo buffers are shaped (N, 2).
Import from any script:  sys.path.insert(0, "<skill>/scripts"); from sfxkit import *
"""
import numpy as np
from scipy.signal import butter, sosfilt, resample_poly, firwin
from scipy.ndimage import maximum_filter1d, minimum_filter1d, uniform_filter1d

SR = 48000

_rng = np.random.default_rng(7)

__all__ = ['SR', 'np', 'reseed', 'rand', 'uniform', 't_', 'n_', 'noise', 'brown', 'env_exp', 'env_ad',
           'bp', 'lp', 'hp', 'sweep', 'norm', 'sat', 'echo', 'radio_fx', 'compress', 'limit',
           'true_peak', 'true_peak_db', 'add', 'db', 'read_wav', 'write_wav', 'fail']


def fail(msg, fix=None, code=1):
    """Print an actionable error (what went wrong + how to fix it) and exit non-zero."""
    import sys
    print(f'error: {msg}' + (f'\n  fix: {fix}' if fix else ''), file=sys.stderr)
    sys.exit(code)


# ---------- randomness (seeded, so every render is identical) ----------
def reseed(seed):
    """Reset the shared generator. Call once per event so adding an event never changes the others."""
    global _rng
    _rng = np.random.default_rng(seed)


def rand(n=None):         return _rng.random(n)
def uniform(a, b, n=None): return _rng.uniform(a, b, n)


# ---------- time, noise, envelopes ----------
def n_(d):  return int(round(d * SR))             # one rounding rule everywhere avoids off-by-one length errors
def t_(d):  return np.arange(n_(d)) / SR
def noise(d): return _rng.standard_normal(n_(d))


def brown(d):
    """Brown noise: energy piled into the lows. Rumbles, wind, air pressure."""
    w = np.cumsum(noise(d)); w -= np.linspace(w[0], w[-1], len(w))
    return norm(hp(w, 20))


def env_exp(d, tau):
    """Exponential decay. tau 0.001-0.004 s = crisp, 0.02-0.1 s = body, 0.3 s+ = tail."""
    return np.exp(-t_(d) / tau)


def env_ad(d, attack, tau):
    """Linear attack, then exponential decay. Softens clicks at the start of a sound."""
    t = t_(d)
    return np.minimum(1, t / max(attack, 1e-6)) * np.exp(-np.maximum(0, t - attack) / tau)


# ---------- filters (frequencies are clamped below Nyquist, so pitch-shifted recipes never crash) ----------
def _f(f, top=.98): return float(np.clip(f, 1, SR / 2 * top))
def bp(x, lo, hi, o=2): return sosfilt(butter(o, [_f(lo, .96), max(_f(hi), _f(lo, .96) * 1.01)], 'band', fs=SR, output='sos'), x)
def lp(x, f, o=2):      return sosfilt(butter(o, _f(f), 'low', fs=SR, output='sos'), x)
def hp(x, f, o=2):      return sosfilt(butter(o, _f(f), 'high', fs=SR, output='sos'), x)


# ---------- oscillators and shaping ----------
def sweep(f0, f1, d, curve=1.0):
    """Sine gliding from f0 to f1 Hz (phase-accumulated, no clicks). curve > 1 = glide late."""
    f = f0 + (f1 - f0) * np.linspace(0, 1, n_(d)) ** curve
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


def norm(x, peak=1.0):
    m = np.abs(x).max() if len(x) else 0
    return x * (peak / m) if m > 0 else x


def sat(x, drive=3.0):
    """Soft saturation. Higher drive = louder, denser, more 'explosive'."""
    return np.tanh(x * drive) / np.tanh(drive)


def echo(x, delay=.12, feedback=.35, taps=4, damp=3000):
    """Feedback-style echo with high-frequency damping on each repeat. Rooms, canyons, slapback."""
    k = n_(delay); out = np.concatenate([x, np.zeros(k * taps)]); rep = x.copy()
    for i in range(1, taps + 1):
        rep = lp(rep, damp) * feedback
        out[i * k:i * k + len(rep)] += rep
    return out


def radio_fx(x, lo=380, hi=2800, drive=3.0, hiss=.02):
    """Walkie-talkie / phone voice: band-limit, distort, add hiss."""
    y = sat(bp(x, lo, hi, 3), drive)
    return norm(y + bp(_rng.standard_normal(len(y)), 1000, 4000) * hiss) * .9


# ---------- dynamics ----------
def compress(x, thr=.25, ratio=3.5, att=.004, rel=.08):
    """Per-sample compressor (pure Python loop: slow, use on voice tracks only)."""
    env = np.zeros_like(x); a, r = np.exp(-1 / (att * SR)), np.exp(-1 / (rel * SR)); e = 0.0; ax = np.abs(x)
    for i in range(len(x)):
        c = ax[i]; e = a * e + (1 - a) * c if c > e else r * e + (1 - r) * c; env[i] = e
    g = np.where(env > thr, (thr + (env - thr) / ratio) / np.maximum(env, 1e-9), 1.0)
    return x * g


# Loudness meters interpolate with short filters that over-read sharp HF transients (a saturated gunshot crack) by up
# to ~0.2 dB versus the ideal reconstruction. This 4x, 16-taps-per-phase Kaiser FIR reproduces ffmpeg's ebur128
# true-peak readings to within 0.05 dB (mostly 0.01) on the built-in recipes, so a file limited here passes that meter.
_METER_FIR = firwin(129, 1 / 4, window=('kaiser', 9))


def true_peak(x):
    """Per-sample true-peak envelope of mono (N,) or stereo (N, 2) audio, max across channels: the peak between each
    sample and the next, as a DAC or an AAC/MP3 decoder reconstructs it. Sample peaks miss these inter-sample overs
    (a built-in gunshot reads -1.9 dBFS by samples but +2.2 dBTP). Oversampled two ways and the larger taken:
    8x with a long filter (close to the ideal waveform; a 4x grid can miss a peak by ~0.2 dB) and 4x with a short
    meter-style filter (BS.1770 is 4x; see _METER_FIR)."""
    x2 = np.asarray(x, dtype=float).reshape(len(x), -1); n = len(x2)
    if not n: return np.zeros(0)
    fine = np.abs(resample_poly(x2, 8, 1, axis=0)).reshape(n, 8, -1).max(axis=(1, 2))
    meter = np.abs(resample_poly(x2, 4, 1, axis=0, window=_METER_FIR)).reshape(n, 4, -1).max(axis=(1, 2))
    return np.maximum(np.maximum(fine, meter), np.abs(x2).max(axis=1))


def true_peak_db(x):
    """True peak in dBTP (0 dBTP = full scale). Use this wherever a peak is reported against a delivery limit."""
    return 20 * np.log10(true_peak(x).max(initial=0) + 1e-12)


def _limit_pass(x, c, n):
    pk = true_peak(x)
    g_raw = np.minimum(1, c / np.maximum(maximum_filter1d(pk, 2 * n + 1), 1e-12))   # look-ahead: dip before the peak
    g = uniform_filter1d(g_raw, n)                                                   # smoothing: no zipper noise
    g[minimum_filter1d(g_raw, n) >= 1] = 1.0     # exact unity wherever nothing nearby is over: untouched, bit for bit
    return x * (g[:, None] if x.ndim == 2 else g)


def limit(x, ceil=-1.0, look=.005):
    """Look-ahead true-peak limiter; `ceil` is in dBTP. Accepts mono (N,) or stereo (N, 2); stereo channels are linked.
    Audio whose true peak is already under the ceiling comes back unchanged (same samples, not just close). Smoothing
    can leave a hair of overshoot, so the result is re-measured: a second pass, then (if still over) a tiny static
    trim, guarantee the returned audio honours the ceiling. Deterministic: same input, same output."""
    c = 10 ** (ceil / 20); n = max(1, n_(look))
    y = _limit_pass(np.asarray(x, dtype=float), c, n)
    if true_peak(y).max(initial=0) > c: y = _limit_pass(y, c, n)
    tp = true_peak(y).max(initial=0)
    return y * (c / tp) if tp > c else y


# ---------- placing sounds ----------
def add(buf, x, at, gain=1.0, pan=0.0):
    """Mix mono x into stereo buf (N, 2) at `at` seconds. pan -1 (left) .. 1 (right), equal-power, centre = unity.
    The last 5 ms are faded out, so a recipe cut off mid-ring never clicks."""
    x = np.asarray(x, dtype=float).copy(); k = min(len(x), n_(.005))
    if k: x[-k:] *= np.linspace(1, 0, k)
    s = n_(at)
    if s >= len(buf) or s + len(x) <= 0: return
    if s < 0: x = x[-s:]; s = 0
    e = min(len(buf), s + len(x))
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    buf[s:e, 0] += x[:e - s] * gain * l * 1.414
    buf[s:e, 1] += x[:e - s] * gain * r * 1.414


def db(x):     return 20 * np.log10(np.sqrt(np.mean(np.square(x))) + 1e-12)


# ---------- files ----------
def read_wav(path, mono=False):
    """Read any wav/flac/ogg, resampled to SR. Returns (N,) if mono else (N, 2); 3+ channels are downmixed."""
    import os, soundfile as sf
    if not os.path.isfile(path):
        fail(f'audio file not found: {path}', 'check the path (event "file" paths are relative to the events file)')
    try:
        y, sr = sf.read(path, always_2d=True)
    except Exception as ex:
        fail(f'cannot read audio file {path}: {ex}', 'convert it to wav/flac/ogg, e.g. ffmpeg -i in.mp3 out.wav')
    if sr != SR: y = resample_poly(y, SR, sr, axis=0)
    if mono or y.shape[1] != 2:
        m = y.mean(1)
        return m if mono else np.stack([m, m], 1)
    return y


def write_wav(path, x, peak=None):
    """Write a 32-bit float wav (peaks above 1.0 survive, nothing clips on disk; no timestamped header chunks, so
    identical audio gives identical bytes). Creates the folder if needed."""
    import os
    from scipy.io import wavfile
    if peak: x = norm(x, peak)
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        wavfile.write(path, SR, np.asarray(x, dtype=np.float32))
    except OSError as ex:
        fail(f'cannot write {path}: {ex.strerror}', 'choose a writable output path')
