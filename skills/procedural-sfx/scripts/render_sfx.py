#!/usr/bin/env python3
"""Render recipes to wav files for auditioning and analysis.

  python render_sfx.py --list                               # every recipe: one-line description [status]
  python render_sfx.py gunshot kind=rifle -o gun.wav        # one sound, keyword args as key=value
  python render_sfx.py --all out_dir/                       # every recipe at default settings
  python render_sfx.py --recipes my_recipes.py door_slam -o door.wav
  python render_sfx.py step surface=wood --variants 4 -o steps.wav   # 4 takes in a row, >= 0.5 s apart
"""
import argparse, ast, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sfxkit import SR, np, reseed, write_wav, n_, fail
import recipes


def parse_kv(items):
    out = {}
    for it in items:
        k, eq, v = it.partition('=')
        if not eq or not k: fail(f'argument {it!r} is not key=value', 'e.g. kind=rifle d=0.5 surface=wood')
        try: out[k] = ast.literal_eval(v)
        except (ValueError, SyntaxError): out[k] = v   # bare words become strings: kind=rifle
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('name', nargs='?'); ap.add_argument('kwargs', nargs='*', help='key=value arguments for the recipe')
    ap.add_argument('-o', '--out'); ap.add_argument('--all', metavar='DIR')
    ap.add_argument('--list', action='store_true'); ap.add_argument('--recipes', action='append', default=[], metavar='FILE')
    ap.add_argument('--variants', type=int, default=1, help='render N takes back to back (checks variation)')
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


if __name__ == '__main__':
    main()
