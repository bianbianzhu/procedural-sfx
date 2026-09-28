#!/usr/bin/env python3
"""Render an event list into a stereo mix: sfx + voice + music + bed, with ducking and limiting.

  python mix.py events.json -o mix.wav
  python mix.py events.json -o mix.wav --recipes my_recipes.py --music score.wav --bed rumble --stems stems/

events.json: {"dur": 14.0, "events": [{"t": 4.6, "type": "gunshot", "args": {"kind": "pistol"}, "gain": 0.7, "pan": 0.3}, ...]}
Field reference: references/event-sync.md section 1. Example: assets/events.example.json.
Anything on the vo bus ducks the music bus. File paths are relative to the events file.
Exit status: 0 = mix written; 1 = input problem, explained on stderr as "error: ... / fix: ...".
"""
import argparse, json, os, re, sys, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sfxkit import SR, np, reseed, add, limit, read_wav, write_wav, db, n_, fail
import recipes

BUSES = ('sfx', 'vo', 'music', 'bed')
BUS_GAIN = {'sfx': .9, 'vo': 1.25, 'music': 1.0, 'bed': 1.0}


def load_json(path, what):
    if not os.path.isfile(path): fail(f'{what} not found: {path}', 'check the path')
    try:
        with open(path) as f: return json.load(f)
    except json.JSONDecodeError as ex:
        fail(f'{what} {path} is not valid JSON: {ex.msg} at line {ex.lineno}, column {ex.colno}',
             'fix that spot (common causes: trailing comma, single quotes, comments)')


def validate(E, table, path):
    """Check the whole event list up front and report every problem at once."""
    if not isinstance(E, dict): fail(f'{path}: top level must be an object like {{"dur": 10, "events": [...]}}')
    events = E.get('events', E.get('ev'))
    if not isinstance(events, list): fail(f'{path}: missing "events" list', 'add "events": [ {"t": 1.0, "type": "click"} ]')
    dur = E.get('dur')
    if dur is not None and (not isinstance(dur, (int, float)) or isinstance(dur, bool) or n_(dur) < 1):
        fail(f'{path}: "dur" must be a positive number of seconds (at least one sample, 1/{SR} s), got {dur!r}',
             'set "dur" to the video length in seconds, e.g. "dur": 14.0')
    problems, unknown = [], {}
    for i, e in enumerate(events):
        at = f'events[{i}]'
        if not isinstance(e, dict): problems.append(f'{at} is not an object'); continue
        at += f' ({e.get("type", "?")} at {e.get("t", "?")}s)'
        if not isinstance(e.get('t'), (int, float)): problems.append(f'{at}: "t" (seconds) is missing or not a number')
        ty = e.get('type')
        if not isinstance(ty, str): problems.append(f'{at}: "type" is missing (a recipe name or "file")'); continue
        if ty == 'file':
            if not isinstance(e.get('file'), str): problems.append(f'{at}: file event needs "file": "path/to/audio.wav"')
            elif not os.path.isfile(os.path.join(os.path.dirname(os.path.abspath(path)), e['file'])):
                problems.append(f'{at}: file not found: {os.path.join(os.path.dirname(os.path.abspath(path)), e["file"])} '
                                '(paths are relative to the events file)')
        elif ty not in table: unknown.setdefault(ty, []).append(i)
        for k, lo, hi in (('gain', 0, 100), ('pan', -1, 1)):
            if k in e and (not isinstance(e[k], (int, float)) or not lo <= e[k] <= hi):
                problems.append(f'{at}: "{k}" must be a number in [{lo}, {hi}], got {e[k]!r}')
        if e.get('bus', 'sfx') not in BUSES: problems.append(f'{at}: "bus" must be one of {list(BUSES)}, got {e.get("bus")!r}')
        if 'seed' in e and not isinstance(e['seed'], int): problems.append(f'{at}: "seed" must be an integer')
        if 'name' in e and not isinstance(e['name'], str): problems.append(f'{at}: "name" must be a string (what the sound is, for the hand-off table)')
        if 'args' in e and not isinstance(e['args'], dict): problems.append(f'{at}: "args" must be an object')
    import difflib
    for ty, idx in unknown.items():
        near = difflib.get_close_matches(ty, table, 3)
        problems.append(f'no recipe named {ty!r} (events {idx})' + (f'; did you mean {" / ".join(near)}?' if near else ''))
    if problems:
        fail(f'{path}: {len(problems)} problem(s)\n  - ' + '\n  - '.join(problems),
             'fix the events file; list recipes with render_sfx.py --list [--recipes FILE]')
    if dur is None:
        if not events: fail(f'{path}: no events and no "dur"', 'add "dur": <video length in seconds>')
        dur = max(e['t'] for e in events) + 3
        print(f'note: no "dur" in {path}; using last event + 3 s = {dur:.2f}s (set it to the video length)')
    return events, float(dur)


def masking_report(placed, mix, min_smr, span=.3, frame=.03):
    """Signal-to-masker ratio per event: its own energy vs everything else in the mix, per channel and band, in
    30 ms frames over two 0.3 s windows: from its start, and from its onset, the first 30 ms frame within 6 dB of its
    own loudest (so a bed that fades in is judged once it is up, and a compound sound whose exposed attack comes well
    before a louder body is still judged on the attack). The best (channel, frame, band) over both counts: the ear
    catches a sound where it is most exposed. Returns (flagged, unassessed)."""
    bands = [('low', 20, 250), ('mid', 250, 4000), ('high', 4000, 20000)]
    F = n_(frame); fq = np.fft.rfftfreq(F, 1 / SR)
    masks = [(name, (fq >= lo) & (fq < hi)) for name, lo, hi in bands]
    flagged, unassessed = [], []
    for label, t, own2 in placed:                  # own2: (len, 2) contribution as mixed
        s = n_(t); e = np.square(own2[:max(0, len(mix) - s)]).sum(1); nf = len(e) // F
        fe = e[:nf * F].reshape(nf, F).sum(1) if nf else e[:1]
        o = int(np.argmax(fe >= fe.max() * .25)) * F if nf and fe.max() > 0 else 0
        L = min(len(own2), len(mix) - s)
        if L <= 0: unassessed.append((label, t)); continue
        starts = sorted({i for w0 in {0, o} for i in range(w0, max(w0 + 1, min(L, w0 + n_(span)) - F + 1), F // 2) if i < L})
        best = (-999.0, '')
        for i in starts:
            j = min(i + F, L); w = np.hanning(j - i)
            for c in (0, 1):
                own = own2[i:j, c]; rest = mix[s + i:s + j, c] - own
                O = np.abs(np.fft.rfft(own * w, F)) ** 2; R = np.abs(np.fft.rfft(rest * w, F)) ** 2
                for name, m in masks:
                    best = max(best, (10 * np.log10((O[m].sum() + 1e-20) / (R[m].sum() + 1e-20)), name))
        if best[0] < min_smr: flagged.append((label, t, best[0], best[1]))
    return flagged, unassessed


def place(buf, x, t, gain=1.0, pan=0.0):
    """Add mono (N,) or stereo (N, 2) x at t seconds; a negative t trims the head. Returns (start, contribution)."""
    if t < 0: x = x[n_(-t):]; t = 0.0
    s = n_(t); k = max(0, min(len(x), len(buf) - s))
    l, r = np.cos((pan + 1) * np.pi / 4) * 1.414, np.sin((pan + 1) * np.pi / 4) * 1.414
    x2 = (np.stack([x, x], 1) if x.ndim == 1 else x.copy())[:k] * gain
    x2[:, 0] *= l; x2[:, 1] *= r
    if x.ndim == 1: add(buf, x[:k], t, gain, pan)   # add() also fades the last 5 ms
    else: buf[s:s + k] += x2                        # stereo files: pan acts as balance
    return s, x2


def plan_audition(unheard, d, protected):
    """One file per unheard (recipe, args): <recipe>.wav, then <recipe>--2.wav ... ('-' cannot occur in a recipe name,
    so no generated name can equal another recipe's). Refuses, before anything is written, a name that is the mix, a
    stem or an input (compared by real path and, for existing files, by device and inode, so links count)."""
    out, used = {}, {}
    for key in unheard:
        n = used[key[0]] = used.get(key[0], 0) + 1
        out[key] = os.path.join(d, f'{key[0]}.wav' if n == 1 else f'{key[0]}--{n}.wav')
    ids = lambda p: {os.path.realpath(p)} | ({(os.stat(p).st_dev, os.stat(p).st_ino)} if os.path.exists(p) else set())
    guard = set().union(*(ids(p) for p in protected))
    clash = [p for p in out.values() if ids(p) & guard]
    if clash: fail(f'--audition {d} would overwrite the mix, a stem or an input: {", ".join(clash)}',
                   'give --audition its own folder, e.g. --audition audition/')
    return out


def audition(unheard, table, paths):
    """Render each unheard (recipe, args) alone, with the seed of its first placement in the mix."""
    for key, r in unheard.items():
        os.makedirs(os.path.dirname(paths[key]) or '.', exist_ok=True)
        reseed(r['seed']); write_wav(paths[key], recipes.call(table, key[0], r['args'], f'--audition {key[0]}'), peak=.8)


def cell(v):
    """A value made safe for one Markdown table cell: no line breaks, pipes escaped."""
    return ' '.join(str(v).split()).replace('|', '\\|')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('events'); ap.add_argument('-o', '--out', default='mix.wav')
    ap.add_argument('--recipes', action='append', default=[], metavar='FILE', help='extra recipe file(s)')
    ap.add_argument('--gains', metavar='JSON', help='{"gunshot": 0.7, ...} default gain per type')
    ap.add_argument('--music', metavar='FILE', help='music track, placed at t=0 (relative to the events file)')
    ap.add_argument('--music-gain', type=float, default=1.0)
    ap.add_argument('--bed', metavar='RECIPE', help='recipe rendered for the whole duration as a background bed')
    ap.add_argument('--bed-gain', type=float, default=.03)
    ap.add_argument('--duck-db', type=float, default=8.0, help='how far music dips under voice (dB)')
    ap.add_argument('--ceiling', type=float, default=-1.0, help='true-peak limiter ceiling in dBTP, -6 .. 0 (default -1)')
    ap.add_argument('--stems', metavar='DIR', help='also write each bus as its own wav')
    ap.add_argument('--min-smr', type=float, default=0.0,
                    help='flag events whose best band is less than this many dB above everything else playing')
    ap.add_argument('--audition', metavar='DIR', help='render each sound nobody has ear-tuned on its own into DIR '
                    '(same args and take as in the mix) and print the hand-off table with those files')
    a = ap.parse_args()
    if not -6 <= a.ceiling <= 0:
        fail(f'--ceiling is a true-peak ceiling in dBTP and must be in [-6, 0], got {a.ceiling}',
             'use -1 (web, streaming, most delivery specs) or -2 (US broadcast); a linear 0.95 is about -0.4 dBTP')

    base = os.path.dirname(os.path.abspath(a.events))
    table = recipes.load(a.recipes)
    events, dur = validate(load_json(a.events, 'events file'), table, a.events)
    gains = load_json(a.gains, 'gains file') if a.gains else {}
    if not isinstance(gains, dict) or not all(isinstance(v, (int, float)) for v in gains.values()):
        fail(f'gains file {a.gains} must map type -> number', 'e.g. {"gunshot": 0.7, "step": 0.3}')
    N = n_(dur)
    bus = {k: np.zeros((N, 2)) for k in BUSES}
    vo_on = np.zeros(N)
    placed, seen = [], {}                          # placed: (label, t, stereo contribution) for the masking report
    unheard, tuned = {}, 0                         # (recipe, args) -> row, for sounds nobody has tuned by ear

    for i, e in enumerate(events):
        ty, t = e['type'], float(e['t'])
        b = e.get('bus', 'vo' if ty == 'file' else 'sfx')
        g = e.get('gain', gains.get(ty, .5)); pan = e.get('pan', 0.0)
        if t >= dur: print(f'warning: events[{i}] {ty} at {t}s starts after dur={dur}s; skipped'); continue
        if ty == 'file':
            x = read_wav(os.path.join(base, e['file'])); label = os.path.basename(e['file'])
        else:
            key = f'{ty}@{t:.4f}:{json.dumps(e.get("args", {}), sort_keys=True)}'
            seen[key] = seen.get(key, 0) + 1       # identical stacked events still get different takes
            seed = e.get('seed', zlib.crc32(f'{key}#{seen[key]}'.encode())); reseed(seed)
            x = recipes.call(table, ty, e.get('args', {}), f'events[{i}] at {t}s'); label = ty
        if t < 0 and len(x) <= n_(-t):
            print(f'warning: events[{i}] {ty} at {t}s ends before 0; skipped'); continue
        s, contrib = place(bus[b], x, t, g, pan)
        if b == 'vo': vo_on[s:s + len(contrib)] = 1
        placed.append((label, max(t, 0.0), contrib * BUS_GAIN[b]))
        if ty != 'file' and (st := recipes.status(table, ty, e.get('args', {}))) != 'tuned':
            row = unheard.setdefault((ty, json.dumps(e.get('args', {}), sort_keys=True)),
                                     dict(name=e.get('name', ''), status=st, args=e.get('args', {}), seed=seed, at=[]))
            row['at'].append(f'{max(t, 0.0):.2f}s')
        elif ty != 'file': tuned += 1

    if a.music:
        m = read_wav(a.music if os.path.isabs(a.music) else os.path.join(base, a.music))
        k = min(len(m), N); bus['music'][:k] += m[:k] * a.music_gain
    if a.bed:
        import inspect
        reseed(1); has_d = a.bed in table and 'd' in inspect.signature(table[a.bed]).parameters
        bargs = {'d': dur} if has_d else {}           # the same args for rendering and for its status
        x = recipes.call(table, a.bed, bargs, '--bed')
        add(bus['bed'], np.resize(x, N), 0, a.bed_gain)
        if (st := recipes.status(table, a.bed, bargs)) != 'tuned':
            unheard[(a.bed, '--bed')] = dict(name='bed', status=st, args=bargs, seed=1, at=['0.00s (--bed)'])
        else: tuned += 1

    # duck music under voice: smooth the on/off mask over 0.25 s so the dip breathes in and out
    if vo_on.any():
        k = min(n_(.25), N); depth = 1 - 10 ** (-a.duck_db / 20)
        duck = 1 - depth * np.clip(np.convolve(vo_on, np.ones(k) / k, 'same')[:N] * 1.5, 0, 1)
        bus['music'] *= duck[:, None]

    mix = sum(bus[k] * BUS_GAIN[k] for k in BUSES)
    if not np.isfinite(mix).all(): fail('mix contains NaN/inf', 'render each recipe alone with render_sfx.py to find the bad one')
    masked, unassessed = masking_report(placed, mix, a.min_smr)
    if a.audition:                                 # settle every output path before anything is written
        protected = [a.out, a.events] + [os.path.join(a.stems, f'{k}.wav') for k in BUSES if a.stems] \
            + ([a.music if os.path.isabs(a.music) else os.path.join(base, a.music)] if a.music else []) \
            + [os.path.join(base, e['file']) for e in events if e.get('type') == 'file']
        apaths = plan_audition(unheard, a.audition, protected)
    mix, tp_in, tp_out = limit(mix, a.ceiling, report=True)
    write_wav(a.out, mix)
    if a.stems:
        for k in BUSES:
            if bus[k].any(): write_wav(os.path.join(a.stems, f'{k}.wav'), bus[k] * BUS_GAIN[k])

    print(f'{a.out}  {dur:.2f}s  {len(placed)} of {len(events)} events placed')
    for k in BUSES:
        if bus[k].any():
            act = np.abs(bus[k]).max(1) > 1e-4
            pk = np.abs(bus[k] * BUS_GAIN[k]).max()          # sample peak: cheap; the true peak is measured on the mix
            print(f'  {k:6s} rms(active) {db(bus[k][act] * BUS_GAIN[k]):6.1f} dB   sample peak {20 * np.log10(pk):+5.1f} dBFS')
    ok = len(placed) - len(masked) - len(unassessed)
    print(f'  masking: {ok}/{len(placed)} events clear the rest of the mix in at least one band')
    for label, t, smr, band in masked:
        print(f'    CHECK {t:7.2f}s {label:14s} best band {band:4s} {smr:+5.1f} dB  -> raise gain, pan apart, or move it off louder sounds')
    for label, t in unassessed:
        print(f'    CHECK {t:7.2f}s {label:14s} not assessed (starts at the very end)')
    took = tp_in - tp_out
    print(f'  true peak {tp_in:+.1f} dBTP -> {tp_out:+.1f} dBTP (ceiling {a.ceiling:+.1f}; '
          + (f'limiter took up to {took:.1f} dB off the loudest transients)' if took > .05 else 'limiter idle)')
          # > 6 dB of peak reduction (the old "peak above 2x the ceiling" rule) audibly flattens hits and can pump
          + ('   limiter working hard: lower gains' if took > 6 else ''))
    if unheard:
        if a.audition: audition(unheard, table, apaths)
        files = apaths if a.audition else {}
        # the table starts at column 0 after a blank line, so it pastes into Markdown as a table, not a code block
        print('  not ear-tuned yet (ask the user to listen)' + ('' if a.audition else
              '; add --audition DIR to render each one and fill in the file column') + ':\n')
        print('| sound | recipe | args | status | at | file to audition |\n| --- | --- | --- | --- | --- | --- |')
        for key, r in unheard.items():
            doc = re.split(r'[:.](\s|$)', ((table[key[0]].__doc__ or '').strip().splitlines() or [''])[0])[0]
            times = sorted(r['at'], key=lambda x: float(x.split('s')[0]))
            at = ', '.join(times[:4]) + (f' (+{len(times) - 4} more)' if len(times) > 4 else '')
            args = ', '.join(f'{k}={v}' for k, v in r['args'].items()) or '—'
            print('| ' + ' | '.join(cell(v) for v in (r['name'] or doc, key[0], args, r['status'], at, files.get(key, '—'))) + ' |')
        print()
    elif tuned:
        print('  every placed recipe is ear-tuned')


if __name__ == '__main__':
    main()
