"""Project-specific recipes. Copy this file next to your project, rename, and add functions.

Every public function becomes a recipe type usable in events.json:
  python mix.py events.json --recipes my_recipes.py
  python render_sfx.py --recipes my_recipes.py door_slam -o door.wav

Rules that keep recipes composable:
  - return a mono numpy array, peak-normalised with norm(...) * v
  - take v=1.0 plus keyword arguments with sensible defaults (events pass them via "args")
  - get randomness only from noise() / rand() / uniform(), so mix.py can seed each event
  - write the docstring's first line as "what it sounds like: how it is built"
"""
import os, sys
# mix.py and render_sfx.py already put the skill's scripts/ on the path; SFX_SCRIPTS is only for standalone use
sys.path.insert(0,os.environ.get('SFX_SCRIPTS', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts')))
from sfxkit import *                      # primitives: noise, env_exp, bp/lp/hp, sweep, sat, echo, ...
from recipes import thump, clack          # reuse built-in recipes as layers


def door_slam(v=1.0, room=True):
    """Heavy wooden door slamming: latch click + low thump + wood rattle, optional room echo."""
    d = .6; tt = t_(d)
    latch = hp(noise(d), 3500) * env_exp(d, .002)                                   # attack: metal latch
    body = np.pad(thump(1, 60), (0, n_(d) - n_(.35)))                               # body: the mass
    rattle = bp(noise(d), 300, 1400) * env_exp(d, .06) * (1 + .5 * np.sin(2 * np.pi * 31 * tt))  # wood panel
    x = latch * .7 + body + rattle * .5
    if room: x = echo(x, delay=.045, feedback=.3, taps=3, damp=2500)               # tail: small hallway
    return norm(x) * v
