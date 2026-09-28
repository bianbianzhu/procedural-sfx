"""Recipe library: each function returns a mono sound peak-normalised to v (default 1.0).

Recipes are starting points. Copy one into your own recipes file and change the numbers
(see references/design-method.md for which number changes what).
"""
from sfxkit import *


# ============ impacts & objects ============
def click(pitch=1.0, v=1.0):
    """Hard plastic snap: short HF noise transient + three HF resonances + a little body."""
    d = .06; tt = t_(d)
    tr = hp(noise(d), 2500) * env_exp(d, .0015)
    res = sum(a * np.sin(2 * np.pi * f * pitch * tt + rand() * 6) * env_exp(d, tau)
              for f, a, tau in [(2900, .6, .012), (4600, .4, .008), (1500, .35, .018)])
    body = np.sin(2 * np.pi * 190 * pitch * tt) * env_exp(d, .01) * .5
    return norm(tr * .8 + res + body) * v


def clack(pitch=1.0, v=1.0):
    """Small object hitting a table: woody mids + plastic highs."""
    d = .09; tt = t_(d); p = pitch * uniform(.85, 1.15)
    x = hp(noise(d), 1200) * env_exp(d, .004) + sum(a * np.sin(2 * np.pi * f * p * tt) * env_exp(d, tau)
        for f, a, tau in [(1200, .6, .02), (2300, .5, .012), (380, .5, .03)])
    return norm(x) * v


def crash(v=1.0, pieces=18):
    """Pile of small objects collapsing: many clacks, accelerating, plus a low thud."""
    d = .9; out = np.zeros(n_(d))
    for k in range(pieces):
        s = int((k / pieces) ** 1.4 * .6 * SR); c = clack(uniform(.8, 1.4), uniform(.4, 1.0))
        out[s:s + len(c)] += c[:len(out) - s]
    out[:n_(.2)] += lp(noise(.2), 400) * env_exp(.2, .05) * .8
    return norm(out) * v


def thump(v=1.0, f=70):
    """Soft heavy impact / landing: low sine sliding down + low-passed noise."""
    d = .35; tt = t_(d)
    return norm(np.sin(2 * np.pi * f * tt * (1 - .3 * tt)) * env_exp(d, .07) + lp(noise(d), 300) * env_exp(d, .02) * .5) * v


def step(v=1.0, surface='hard'):
    """Footstep. surface: 'hard' (tile/stone), 'wood', 'soft' (carpet/grass)."""
    if surface not in ('hard', 'wood', 'soft'): raise ValueError(f"surface must be 'hard', 'wood' or 'soft', got {surface!r}")
    d = .12; tt = t_(d); p = uniform(.9, 1.1)
    if surface == 'soft':
        x = lp(noise(d), 900 * p) * env_ad(d, .006, .025)
    elif surface == 'wood':
        x = bp(noise(d), 300, 2500) * env_exp(d, .01) + np.sin(2 * np.pi * 180 * p * tt) * env_exp(d, .02) * .6
    else:
        x = hp(noise(d), 1800) * env_exp(d, .004) + np.sin(2 * np.pi * 2200 * p * tt) * env_exp(d, .006) * .5 \
            + lp(noise(d), 250) * env_exp(d, .015) * .4
    return norm(x) * v


def creak(v=1.0):
    """Door hinge / wooden creak: frequency-wobbling sawtooth, band-passed, stuttering."""
    d = .22; tt = t_(d); f0 = uniform(70, 110)
    saw = 2 * ((tt * f0 * (1 + .3 * np.sin(2 * np.pi * 9 * tt))) % 1) - 1
    return norm(bp(saw, 400, 3000) * (np.abs(np.sin(2 * np.pi * 23 * tt)) ** 3) * np.sin(np.pi * tt / d)) * v


# ============ motion ============
def whoosh(d=.35, v=1.0, lo=600, hi=3200):
    """Something flying past / a swing: band-pass noise whose centre rises then falls."""
    n = noise(d); tt = t_(d); out = np.zeros_like(n)
    for i in range(0, len(n), 480):                 # 10 ms blocks, each filtered with 2000 samples of run-in
        j = min(i + 480, len(n)); f = lo + (hi - lo) * np.sin(np.pi * i / len(n))
        out[i:j] = bp(n[max(0, i - 2000):j], f * .7, f * 1.3)[-(j - i):]
    return norm(out * np.sin(np.pi * tt / d) ** 2) * v


# ============ UI & signals ============
def ding(v=1.0, f=1318):
    """Bell / notification: five partials, highs decay first."""
    d = 1.6; tt = t_(d); k = f / 1318
    x = sum(a * np.sin(2 * np.pi * fr * k * tt) * env_exp(d, tau)
            for fr, a, tau in [(1318, 1, .6), (2637, .5, .35), (3951, .3, .2), (1976, .25, .5), (5274, .15, .1)])
    return norm(x) * v


def pop(v=1.0, f0=500, f1=1900):
    """Bubble / appear: short upward sine sweep."""
    d = .18
    return norm(sweep(f0, f1, d) * env_exp(d, .05)) * v


def beep(v=1.0, f=2525, d=.25):
    """Clean tone with 5 ms fades (radio quindar tone, cursor, timer)."""
    x = np.sin(2 * np.pi * f * t_(d)); k = min(n_(.005), len(x) // 2)
    if k: x[:k] *= np.linspace(0, 1, k); x[-k:] *= np.linspace(1, 0, k)
    return x * v


# ============ weapons & sci-fi (starting points: tune by ear) ============
_GUNS = {'pistol':  dict(crack=.0015, boom=.035, f=90, tail=.25),
         'rifle':   dict(crack=.0010, boom=.050, f=70, tail=.45),
         'shotgun': dict(crack=.0025, boom=.090, f=55, tail=.60)}


def gunshot(v=1.0, kind='pistol', drive=3.0, crack=None, boom=None, f=None, tail=None):
    """Gunshot: muzzle crack + pressure boom + reflections, saturated. kind: pistol | rifle | shotgun.

    crack / boom / tail (decay seconds) and f (boom Hz) override the kind's preset."""
    if kind not in _GUNS: raise ValueError(f'kind must be one of {list(_GUNS)}, got {kind!r}')
    P = dict(_GUNS[kind]); P.update({k: v_ for k, v_ in dict(crack=crack, boom=boom, f=f, tail=tail).items() if v_ is not None})
    d = max(1.2, P['tail'] * 5); tt = t_(d)
    crack_ = hp(noise(d), 3000) * env_exp(d, P['crack'])
    boom_ = lp(noise(d), 600) * env_exp(d, P['boom']) + np.sin(2 * np.pi * P['f'] * tt * (1 - .4 * np.minimum(tt, 1.2))) * env_exp(d, P['boom'] * 1.6)
    tail_ = bp(noise(d), 250, 2500) * env_exp(d, P['tail']) * .12
    return norm(sat(crack_ * 1.3 + boom_ + tail_, drive)) * v


def burst(v=1.0, n=6, rate=.08, kind='rifle', drive=3.0):
    """Automatic fire: n gunshots `rate` seconds apart, each at a random level and with fresh noise."""
    if n < 1 or rate <= 0: raise ValueError(f'need n >= 1 and rate > 0, got n={n}, rate={rate}')
    shots = [gunshot(uniform(.8, 1.0), kind, drive) for _ in range(n)]
    out = np.zeros(n_((n - 1) * rate) + max(len(g) for g in shots))
    for k, g in enumerate(shots):
        s = n_(k * rate)
        out[s:s + len(g)] += g[:len(out) - s]
    return norm(out) * v


def explosion(v=1.0, d=3.0):
    """Explosion: blast wave + sub drop 60->25 Hz + brown-noise roar + debris crackle."""
    tt = t_(d)
    blast = lp(noise(d), 1500) * env_exp(d, .08)
    sub = sweep(60, 25, d) * env_exp(d, .6)
    body = lp(brown(d), 400) * env_exp(d, .9)
    debris = hp(noise(d), 2500) * (rand(len(tt)) > .997) * env_exp(d, .7) * 4
    return norm(sat(blast * 1.2 + sub + body * .8 + lp(debris, 7000) * .3, 2.5)) * v


def laser(v=1.0, f0=2400, f1=300, d=.3):
    """Sci-fi zap: two slightly detuned downward sweeps."""
    return norm(sweep(f0, f1, d) * env_exp(d, d * .3) + sweep(f0 * 1.004, f1 * 1.016, d) * env_exp(d, d * .3)) * v


# ============ ambience & drama ============
def rumble(v=1.0, d=1.5):
    """Low rumble bed that fades in (earthquake, engine room, distant thunder)."""
    return norm(lp(brown(d), 200) * np.sin(np.pi * t_(d) / d / 2) ** 2) * v


def ignite(v=1.0):
    """Rocket / burner ignition: 45 Hz sub drop + low-passed noise burst."""
    d = 1.8; tt = t_(d)
    return norm(np.sin(2 * np.pi * 45 * tt * (1 - .25 * tt)) * env_exp(d, .5) * .9 + lp(noise(d), 1200) * env_exp(d, .35)) * v


def roar(v=1.0, d=3.0):
    """Sustained engine / fire roar with crackle, fades in and out."""
    tt = t_(d); b = lp(brown(d), 700); crack = hp(noise(d), 3000) * (rand(len(tt)) > .995) * 3
    e = np.minimum(1, tt / .4) * np.minimum(1, (d - tt) / .6)
    return norm((b + lp(crack, 6000) * .3) * e) * v


def heartbeat(v=1.0):
    """Lub-dub: two low thumps 0.22 s apart."""
    a = thump(1, 55); b = np.pad(thump(.7, 50), (n_(.22), 0))
    a = np.pad(a, (0, len(b) - len(a)))
    return norm(a + b) * v


RECIPES = {f.__name__: f for f in [click, clack, crash, thump, step, creak, whoosh, ding, pop, beep,
                                   gunshot, burst, explosion, laser, rumble, ignite, roar, heartbeat]}


def call(table, name, args, where=''):
    """Render recipe `name` with `args`; turn every mistake into an actionable error (see sfxkit.fail)."""
    import inspect
    at = f' ({where})' if where else ''
    if name not in table:
        import difflib
        near = difflib.get_close_matches(name, table, 3)
        fail(f'no recipe named {name!r}{at}', (f'did you mean {" / ".join(near)}? ' if near else '')
             + 'list recipes with render_sfx.py --list; add your own with --recipes FILE')
    fn = table[name]; sig = inspect.signature(fn)
    if not isinstance(args, dict): fail(f'"args" for {name}{at} must be an object, got {args!r}', f'e.g. "args": {{"v": 1.0}}')
    bad = [k for k in args if k not in sig.parameters]
    if bad:
        fail(f'{name}{at}: unknown argument(s) {bad}',
             f'accepted: {", ".join(f"{p.name}={p.default!r}" for p in sig.parameters.values())}')
    try:
        x = np.asarray(fn(**args), dtype=float)
    except Exception as ex:
        fail(f'{name}{at} raised {type(ex).__name__}: {ex}', 'check the argument values; render it alone with render_sfx.py to debug')
    if x.ndim != 1 or not len(x): fail(f'{name}{at} returned shape {x.shape}', 'a recipe must return a non-empty mono 1-D array')
    if not np.isfinite(x).all(): fail(f'{name}{at} produced NaN/inf', 'look for division by zero or log(0) in the recipe')
    return x


def load(extra=()):
    """Built-in recipes plus every public function in each extra .py file (later files win on name clashes)."""
    import importlib.util, inspect, os, traceback
    table = dict(RECIPES)
    for path in extra or ():
        if not os.path.isfile(path): fail(f'recipe file not found: {path}', 'pass the path to a .py file (see assets/recipe_template.py)')
        spec = importlib.util.spec_from_file_location(os.path.splitext(os.path.basename(path))[0], path)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception as ex:
            line = ex.lineno if isinstance(ex, SyntaxError) else next(
                (f.lineno for f in reversed(traceback.extract_tb(ex.__traceback__)) if f.filename == os.path.abspath(path)), '?')
            fail(f'recipe file {path} failed to import at line {line}: {type(ex).__name__}: {ex}',
                 'fix that line; recipe files should start with `from sfxkit import *`')
        for name, fn in inspect.getmembers(mod, inspect.isfunction):
            if not name.startswith('_') and fn.__module__ == mod.__name__:
                table[name] = fn
    return table
