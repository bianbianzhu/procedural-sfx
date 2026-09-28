#!/usr/bin/env python3
"""Describe sounds in numbers, so an agent that cannot listen can still check its work.

  python analyze.py gun.wav thump.wav            # one line of metrics per file
  python analyze.py sfx_dir/*.wav --bands        # plus energy per frequency band

Metrics
  dur      length (s)                    peak    peak level (dBFS)
  attack   first sound -> peak (ms)      rms     loudness of the audible part (dBFS)
  t-20/-40 peak -> envelope 20/40 dB down (ms): how long it rings; ">end" = still ringing when the file stops
  (attack on a multi-hit sound such as a burst measures to the loudest hit, not the first)
  centroid spectral centre of mass (Hz): <500 dark/boomy, 500-2000 warm/mid, >3000 bright/crisp
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sfxkit import SR, np, read_wav

BANDS = [('sub', 20, 60), ('low', 60, 250), ('lowmid', 250, 1000), ('mid', 1000, 4000), ('high', 4000, 10000), ('air', 10000, 24000)]
HOP = 480                                  # 10 ms frames


def envelope_db(x):
    n = len(x) // HOP
    fr = x[:n * HOP].reshape(n, HOP)
    return 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-12)


def describe(x):
    if len(x) < HOP: x = np.pad(x, (0, HOP - len(x)))      # shorter than one 10 ms frame
    peak_i = int(np.abs(x).argmax()); peak = np.abs(x).max()
    pk_db = 20 * np.log10(peak + 1e-12)
    above = np.nonzero(np.abs(x) > peak * .01)[0]            # -40 dB relative
    start = above[0] if len(above) else 0
    env = envelope_db(x); pf = peak_i // HOP
    ref = env[pf] if pf < len(env) else env.max()

    def fall(dbdown):
        after = np.nonzero(env[pf:] < ref - dbdown)[0]
        return (after[0] * HOP / SR * 1000) if len(after) else float('nan')

    act = x[np.abs(x) > peak * .01] if peak > 0 else x
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2; fq = np.fft.rfftfreq(len(x), 1 / SR)
    tot = spec.sum() + 1e-20
    return dict(dur=len(x) / SR, peak=pk_db, rms=20 * np.log10(np.sqrt(np.mean(act ** 2)) + 1e-12),
                attack=(peak_i - start) / SR * 1000, t20=fall(20), t40=fall(40),
                centroid=(spec * fq).sum() / tot,
                bands={n: 100 * spec[(fq >= lo) & (fq < hi)].sum() / tot for n, lo, hi in BANDS})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('files', nargs='+'); ap.add_argument('--bands', action='store_true')
    a = ap.parse_args()

    ms = lambda v: '   >end' if np.isnan(v) else f'{v:5.0f}ms'     # >end: still ringing when the file stops
    print(f'{"file":22s} {"dur":>6s} {"peak":>6s} {"rms":>6s} {"attack":>7s} {"t-20":>7s} {"t-40":>7s} {"centroid":>9s}')
    for f in a.files:
        x = read_wav(f, mono=True)
        if not np.abs(x).max() > 0: print(f'{os.path.basename(f)[:22]:22s} silent (all zeros)'); continue
        d = describe(x)
        print(f'{os.path.basename(f)[:22]:22s} {d["dur"]:6.2f} {d["peak"]:6.1f} {d["rms"]:6.1f} '
              f'{d["attack"]:5.1f}ms {ms(d["t20"])} {ms(d["t40"])} {d["centroid"]:7.0f}Hz')
        if a.bands:
            print('    ' + '  '.join(f'{n} {v:4.1f}%' for n, v in d['bands'].items()))


if __name__ == '__main__':
    main()
