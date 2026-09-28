#!/usr/bin/env python3
"""Render recipes to wav files for auditioning and analysis.

  python render_sfx.py --list                               # every recipe: one-line description [status]
  python render_sfx.py gunshot kind=rifle -o gun.wav        # one sound, keyword args as key=value
  python render_sfx.py --all out_dir/                       # every recipe at default settings
  python render_sfx.py --recipes my_recipes.py door_slam -o door.wav
  python render_sfx.py step surface=wood --variants 4 -o steps.wav   # 4 takes in a row, >= 0.5 s apart

--variants N (N >= 2) also prints analyze.py metrics per take and their spread, with a verdict:
  CHECK: takes are identical   every take is the same sample for sample: the recipe draws no randomness
  note: takes barely differ    RMS range < 1 dB and centroid range < 2% (only fine noise detail changes), or the most
                               alike pair has waveform similarity > 0.98 (peak normalised cross-correlation within
                               +-5 ms: the same waveform up to level, which the spreads cannot see)
  takes vary                   anything more
"""
import argparse, ast, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sfxkit import SR, np, reseed, write_wav, n_, fail
import recipes
from analyze import describe

SMALL_RMS_DB, SMALL_CENTROID_PCT = 1.0, 2.0   # below both = "barely differ" (built-in thump, heartbeat, creak)
SIMILAR = .98                                  # waveform similarity above this = "barely differ", whatever the spreads


def parse_kv(items):
    out = {}
    for it in items:
        k, eq, v = it.partition('=')
        if not eq or not k: fail(f'argument {it!r} is not key=value', 'e.g. kind=rifle d=0.5 surface=wood')
        try: out[k] = ast.literal_eval(v)
        except (ValueError, SyntaxError): out[k] = v   # bare words become strings: kind=rifle
    return out


def similarity(a, b, lag=.005):
    """Peak normalised cross-correlation of two takes within +-5 ms: 1.0 = same waveform up to level and a small
    shift (which RMS and centroid spreads cannot see), ~0 = unrelated noise."""
    n = len(a) + len(b); F = 1 << (n - 1).bit_length()
    x = np.fft.irfft(np.fft.rfft(a, F) * np.conj(np.fft.rfft(b, F)), F); L = n_(lag)
    return float(np.abs(np.concatenate([x[:L + 1], x[-L:]])).max() / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-20))


def variant_report(takes, scale):
    """Metrics per take (as written, i.e. times the file's normalising gain) and a verdict on how much they differ."""
    ms = lambda v: '>end' if np.isnan(v) else f'{v:.0f}ms'
    d = [describe(t * scale) for t in takes]
    for i, m in enumerate(d):
        print(f'  take {i + 1}  peak {m["peak"]:5.1f}  rms {m["rms"]:5.1f}  centroid {m["centroid"]:6.0f}Hz  t-20 {ms(m["t20"])}')
    r = [m['rms'] for m in d]; c = [m['centroid'] for m in d]
    rms_db, cen_pct = max(r) - min(r), 100 * (max(c) - min(c)) / max(np.mean(c), 1e-9)
    sim = max(similarity(takes[i], takes[j]) for i in range(len(takes)) for j in range(i + 1, len(takes)))
    print(f'  spread: rms {rms_db:.2f} dB, centroid {cen_pct:.1f}%, waveform similarity {sim:.3f} (most alike pair)')
    if all(len(t) == len(takes[0]) and np.array_equal(t, takes[0]) for t in takes[1:]):
        print('  CHECK: takes are identical — draw randomness from noise()/rand()/uniform() '
              '(fine for a UI tone meant to repeat exactly)')
    elif (rms_db < SMALL_RMS_DB and cen_pct < SMALL_CENTROID_PCT) or sim > SIMILAR:
        why = f'waveform similarity {sim:.3f} > {SIMILAR:g}' if sim > SIMILAR else f'rms < {SMALL_RMS_DB:g} dB, centroid < {SMALL_CENTROID_PCT:g}%'
        print(f'  note: takes barely differ ({why}); if it repeats close '
              'together, randomise pitch ±5-10% with uniform() in the recipe or vary args and gain per event')
    else:
        print('  takes vary')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('name', nargs='?'); ap.add_argument('kwargs', nargs='*', help='key=value arguments for the recipe')
    ap.add_argument('-o', '--out'); ap.add_argument('--all', metavar='DIR')
    ap.add_argument('--list', action='store_true'); ap.add_argument('--recipes', action='append', default=[], metavar='FILE')
    ap.add_argument('--variants', type=int, default=1, help='render N takes back to back and print how much they differ')
    ap.add_argument('--seed', type=int, default=0)
    a = ap.parse_args()
    table = recipes.load(a.recipes)

    if a.list:
        # status: tuned = ear-tuned in finished work; starting point = never ear-tuned; new = from a --recipes file
        for name, fn in table.items():
            doc = (fn.__doc__ or '').strip().splitlines()[0] if (fn.__doc__ or '').strip() else ''
            print(f'{name:12s} {doc}  [{recipes.status_summary(table, name)}]')
        return
    if a.all:
        for i, name in enumerate(table):
            reseed(a.seed + i); write_wav(os.path.join(a.all, f'{name}.wav'), recipes.call(table, name, {}) * .8)
        print(f'{len(table)} files -> {a.all}'); return
    if not a.name: fail('no recipe name given', 'e.g. render_sfx.py gunshot kind=rifle -o gun.wav  (or --list / --all DIR)')
    if a.variants < 1: fail(f'--variants must be >= 1, got {a.variants}')

    kw = parse_kv(a.kwargs); takes = []
    for i in range(a.variants):
        reseed(a.seed + i); takes.append(recipes.call(table, a.name, kw))
    L = max(len(t) for t in takes); gap = max(n_(.5), L + n_(.15))
    x = np.zeros(gap * (len(takes) - 1) + L) if a.variants > 1 else takes[0]
    if a.variants > 1:
        for i, t in enumerate(takes): x[i * gap:i * gap + len(t)] += t
    out = a.out or f'{a.name}.wav'
    write_wav(out, x, peak=.8); print(out, f'{len(x) / SR:.2f}s')
    if a.variants > 1: variant_report(takes, .8 / max(np.abs(x).max(), 1e-12))


if __name__ == '__main__':
    main()
