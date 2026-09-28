#!/usr/bin/env python3
"""Render an event list into a stereo mix: sfx + voice + music + bed, with ducking and limiting.

  python mix.py events.json -o mix.wav
  python mix.py events.json -o mix.wav --recipes my_recipes.py --music score.wav --bed rumble --stems stems/

events.json (see assets/events.example.json):
  {"dur": 14.0,
   "events": [
     {"t": 4.60, "type": "gunshot", "args": {"kind": "pistol"}, "gain": 0.7, "pan": 0.3},
     {"t": 2.00, "type": "file", "file": "voices/line01.wav", "bus": "vo"}
   ]}

  t      seconds from the start of the video
  type   a recipe name, or "file" to drop in an audio file (voice lines, recorded samples)
  args   keyword arguments for the recipe            (optional)
  gain   linear gain; default from --gains, else 0.5  (optional)
  pan    -1 left .. 1 right                           (optional)
  bus    sfx | vo | music | bed; default sfx, "file" events default vo (optional)
  seed   fixes this event's randomness                (optional; default derived from type + t)

Anything on the vo bus ducks the music bus. File paths are relative to the events file.
"""
import argparse, json, os, sys, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sfxkit import SR, np, reseed, add, limit, read_wav, write_wav, db, n_
import recipes

BUSES = ('sfx', 'vo', 'music', 'bed')
BUS_GAIN = {'sfx': .9, 'vo': 1.25, 'music': 1.0, 'bed': 1.0}


def masking_report(placed, mix_mono, min_smr, span=.3, frame=.03):
    """Signal-to-masker ratio per event: its own energy vs everything else in the mix, per band, in 30 ms frames
    over its first 0.3 s. The best (frame, band) counts: the ear catches a sound where it is most exposed."""
    bands = [('low', 20, 250), ('mid', 250, 4000), ('high', 4000, 20000)]
    F = n_(frame); w = np.hanning(F); fq = np.fft.rfftfreq(F, 1 / SR)
    masks = [(name, (fq >= lo) & (fq < hi)) for name, lo, hi in bands]
    flagged = []
    for label, t, x in placed:
        s = n_(t); k = min(len(x), n_(span), len(mix_mono) - s)
        if k < F: continue
        best = (-999.0, '')
        for i in range(0, k - F + 1, F // 2):
            own = x[i:i + F]; rest = mix_mono[s + i:s + i + F] - own
            O = np.abs(np.fft.rfft(own * w)) ** 2; R = np.abs(np.fft.rfft(rest * w)) ** 2
            for name, m in masks:
                best = max(best, (10 * np.log10((O[m].sum() + 1e-20) / (R[m].sum() + 1e-20)), name))
        if best[0] < min_smr: flagged.append((label, t, best[0], best[1]))
    return flagged


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('events'); ap.add_argument('-o', '--out', default='mix.wav')
    ap.add_argument('--recipes', action='append', default=[], metavar='FILE', help='extra recipe file(s)')
    ap.add_argument('--gains', metavar='JSON', help='{"gunshot": 0.7, ...} default gain per type')
    ap.add_argument('--music', metavar='FILE', help='music track, placed at t=0')
    ap.add_argument('--music-gain', type=float, default=1.0)
    ap.add_argument('--bed', metavar='RECIPE', help='recipe rendered for the whole duration as a background bed')
    ap.add_argument('--bed-gain', type=float, default=.03)
    ap.add_argument('--duck-db', type=float, default=8.0, help='how far music dips under voice (dB)')
    ap.add_argument('--ceiling', type=float, default=.95)
    ap.add_argument('--stems', metavar='DIR', help='also write each bus as its own wav')
    ap.add_argument('--min-smr', type=float, default=0.0,
                    help='flag events whose best band is less than this many dB above everything else playing')
    a = ap.parse_args()

    base = os.path.dirname(os.path.abspath(a.events))
    E = json.load(open(a.events))
    events = E.get('events', E.get('ev', []))
    dur = float(E.get('dur') or max(e['t'] for e in events) + 3)
    N = n_(dur)
    table = recipes.load(a.recipes)
    gains = json.load(open(a.gains)) if a.gains else {}
    bus = {k: np.zeros((N, 2)) for k in BUSES}
    vo_on = np.zeros(N)
    missing = set()
    placed = []                                    # (label, t, mono contribution) for the masking report

    for e in events:
        ty = e['type']; b = e.get('bus', 'vo' if ty == 'file' else 'sfx')
        g = e.get('gain', gains.get(ty, .5)); pan = e.get('pan', 0.0)
        if e['t'] >= dur: print(f'warning: event {ty} at {e["t"]}s is after dur={dur}s'); continue
        if ty == 'file':
            y = read_wav(os.path.join(base, e['file']))
            s = n_(e['t']); k = min(len(y), N - s)
            bus[b][s:s + k] += y[:k] * g
            if b == 'vo': vo_on[s:s + k] = 1
            placed.append((e['file'], e['t'], y[:k].mean(1) * g * BUS_GAIN[b]))
            continue
        if ty not in table: missing.add(ty); continue
        reseed(e.get('seed', zlib.crc32(f'{ty}@{e["t"]:.4f}'.encode())))
        x = table[ty](**e.get('args', {}))
        add(bus[b], x, e['t'], g, pan)
        if b == 'vo': vo_on[n_(e['t']):n_(e['t']) + len(x)] = 1
        placed.append((ty, e['t'], x * g * BUS_GAIN[b]))
    if missing: print('warning: no recipe for', ', '.join(sorted(missing)), '(add one with --recipes)')

    if a.music:
        m = read_wav(os.path.join(base, a.music) if not os.path.isabs(a.music) else a.music)
        k = min(len(m), N); bus['music'][:k] += m[:k] * a.music_gain
    if a.bed:
        reseed(1); fn = table[a.bed]
        try: x = fn(d=dur)
        except TypeError: x = np.resize(fn(), N)
        add(bus['bed'], x[:N], 0, a.bed_gain)

    # duck music under voice: smooth the on/off mask over 0.25 s so the dip breathes in and out
    if vo_on.any():
        k = n_(.25); depth = 1 - 10 ** (-a.duck_db / 20)
        duck = 1 - depth * np.clip(np.convolve(vo_on, np.ones(k) / k, 'same') * 1.5, 0, 1)
        bus['music'] *= duck[:, None]

    mix = sum(bus[k] * BUS_GAIN[k] for k in BUSES)
    masked = masking_report(placed, mix.mean(1), a.min_smr)
    if not np.isfinite(mix).all(): sys.exit('error: mix contains NaN/inf; check your recipes')
    raw_peak = np.abs(mix).max()
    mix = limit(mix, a.ceiling)
    write_wav(a.out, mix)
    if a.stems:
        os.makedirs(a.stems, exist_ok=True)
        for k in BUSES:
            if bus[k].any(): write_wav(os.path.join(a.stems, f'{k}.wav'), bus[k] * BUS_GAIN[k])

    print(f'{a.out}  {dur:.2f}s  {len(events)} events')
    for k in BUSES:
        if bus[k].any():
            act = np.abs(bus[k]).max(1) > 1e-4
            print(f'  {k:6s} rms(active) {db(bus[k][act] * BUS_GAIN[k]):6.1f} dB   peak {np.abs(bus[k] * BUS_GAIN[k]).max():.2f}')
    print(f'  masking: {len(placed) - len(masked)}/{len(placed)} events clear the rest of the mix in at least one band')
    for label, t, smr, band in masked:
        print(f'    CHECK {t:7.2f}s {label:14s} best band {band:4s} {smr:+5.1f} dB  -> raise gain, pan apart, or move it off louder sounds')
    print(f'  pre-limit peak {raw_peak:.2f} -> {np.abs(mix).max():.2f}'
          + ('   (limiter working hard: lower gains)' if raw_peak > 2 * a.ceiling else ''))


if __name__ == '__main__':
    main()
