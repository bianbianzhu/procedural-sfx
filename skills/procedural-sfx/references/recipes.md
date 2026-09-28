# Built-in recipes

All recipes live in `scripts/recipes.py`. Each returns a mono array normalised to peak `v`. Arguments are passed as `key=value` on the `render_sfx.py` command line, or as `"args": {...}` in events.json. Only the arguments in the Args column exist; a "custom recipe" tuning means copying the recipe into your own file and editing it.

**Provenance.** Recipes marked ✓ have been used and tuned by ear in finished films. Recipes marked ◇ (weapons and sci-fi) are measured and structurally sound but not yet ear-tuned. Audition them and adjust before relying on them, and tell the user they are starting points.

## Contents
- Impacts & objects: click, clack, crash, thump, step, creak
- Motion: whoosh
- UI & signals: ding, pop, beep
- Weapons & sci-fi: gunshot, burst, explosion, laser
- Ambience & drama: rumble, ignite, roar, heartbeat
- Effects applied to existing audio: radio_fx, echo, sat
- Writing your own

## Impacts & objects

| Recipe | Args | Sound and build | Variations |
| --- | --- | --- | --- |
| `click` ✓ | `pitch=1.0` | Hard plastic snap, 60 ms: HP noise transient + 1.5/2.9/4.6 kHz resonances + 190 Hz body | Toy bricks, switches, camera shutters (pitch 0.7), keyboard (pitch 1.2 + `uniform` per key) |
| `clack` ✓ | `pitch=1.0` | Small object on a table, 90 ms: woody mids + plastic highs; pitch randomised ±15% | Coins or keys: pitch 1.6–2; dice: several clacks 40–80 ms apart |
| `crash` ✓ | `pieces=18` | Pile collapsing, 0.9 s: accelerating clacks + low thud | Fewer pieces = a small spill; more = a shelf coming down |
| `thump` ✓ | `f=70` | Soft heavy impact, 350 ms: 70 Hz sine gliding down + LP noise | Body fall f=50; box on carpet f=90; punch f=110 + a `click` on top |
| `step` ✓ hard, ◇ wood/soft | `surface='hard'\|'wood'\|'soft'` | Footstep, 120 ms, pitch randomised ±10% | Heels: hard at higher gain; heavy boots: wood + a `thump` f=80 at 0.3 gain on the same frame |
| `creak` ✓ | — | Wooden creak, 220 ms: wobbling sawtooth, band-passed, stuttering | Doors: chain 2–4 creaks; ship hull: slow them down (edit `d`) and low-pass |

## Motion

| Recipe | Args | Sound and build | Variations |
| --- | --- | --- | --- |
| `whoosh` ✓ | `d=.35, lo=600, hi=3200` | Band-pass noise whose centre rises then falls, sin² envelope | Sword swing d=.2 hi=5000; slow pass-by d=1.2 hi=1500; place it so its peak (the middle) lands on the frame of the pass |

## UI & signals

| Recipe | Args | Sound and build | Variations |
| --- | --- | --- | --- |
| `ding` ✓ | `f=1318` | Bell, 1.6 s: five partials, highs decay first | Success: two dings a fifth apart (f, f*1.5) 120 ms apart; microwave: f=880 |
| `pop` ✓ | `f0=500, f1=1900` | Up-sweep, 180 ms | Disappear: swap f0/f1; bubble cluster: 5 pops with random f0 |
| `beep` ✓ | `f=2525, d=.25` | Clean tone with 5 ms fades | Radio quindar 2525 Hz; error: two beeps at f=466 and 233; countdown: f=1000 d=.1 |

## Weapons & sci-fi (◇ starting points)

| Recipe | Args | Sound and build | Tuning |
| --- | --- | --- | --- |
| `gunshot` | `kind='pistol'\|'rifle'\|'shotgun', drive=3`, overrides `crack`, `boom`, `tail` (decay s), `f` (boom Hz) | Muzzle crack (HP noise) + pressure boom (LP noise + 55–90 Hz sine gliding down) + reflections (BP noise tail), `sat()`. Presets: pistol crack .0015 boom .035 f 90 tail .25; rifle .001/.05/70/.45; shotgun .0025/.09/55/.6 | Crisper: `crack=.0008`; heavier: `boom=.08, f=50`; indoors or canyon: `tail=.9`, or `echo()` in a custom recipe; cartoon: `drive=1.5`; distant (custom recipe): LP 1500 Hz, drop the crack |
| `burst` | `n=6, rate=.08, kind='rifle', drive=3` | n gunshots `rate` s apart, each at a random level (0.8–1.0) and with fresh noise | SMG `rate=.06`; machine gun `rate=.1`; lighter weapon `kind='pistol'` |
| `explosion` | `d=3.0` | Blast (LP noise) + sub sweep 60→25 Hz + brown-noise roar + debris crackle, saturated | Grenade: `d=1.5`; building: add a `crash` event 0.3 s later; distant (custom recipe): LP 400 Hz, drop the blast |
| `laser` | `f0=2400, f1=300, d=.3` | Two detuned down-sweeps | Blaster: `f0=3500, f1=500, d=.15`; charging: `f0=300, f1=2400, d=1.0` |

## Ambience & drama

| Recipe | Args | Sound and build | Use |
| --- | --- | --- | --- |
| `rumble` ✓ | `d=1.5` | LP brown noise < 200 Hz, fades in | Earthquakes, tension; as a whole-film bed: `mix.py --bed rumble` |
| `ignite` ✓ | — | 45 Hz sub drop + LP noise burst | Rocket launch, gas burner, a portal opening |
| `roar` ✓ | `d=3.0` | Brown noise LP 700 Hz + sparse crackle, fades in and out | Engines, fire, crowd murmur (BP 300–2000 Hz instead) |
| `heartbeat` ✓ | — | Two low thumps 0.22 s apart | Tension; repeat every 0.8 s (calm) to 0.45 s (panic) |

## Effects (in `sfxkit.py`; they process audio rather than generate it)

| Function | Does | Use |
| --- | --- | --- |
| `radio_fx(x)` | Band-limit 380–2800 Hz, distort, add hiss | Walkie-talkie, phone, PA voice; works on a TTS line read with `read_wav(path, mono=True)` |
| `echo(x, delay, feedback, taps, damp)` | Damped feedback echo | Slapback (delay .08), hall (.05, fb .5), canyon (.3, fb .4) |
| `sat(x, drive)` | tanh saturation | Density and aggression |

## Writing your own

Copy `assets/recipe_template.py` into the project (e.g. `my_recipes.py`) and add functions. Every public function becomes an event type:

```bash
python scripts/render_sfx.py --recipes my_recipes.py --list
python scripts/mix.py events.json --recipes my_recipes.py -o mix.wav
```

Contract (it is what makes recipes composable):
- Return mono, end with `norm(x) * v`, and take `v=1.0` plus keyword args with defaults.
- Draw randomness only from `noise()`, `rand()`, `uniform()`, so `mix.py` can seed per event.
- Make the docstring's first line "what it sounds like: how it is built". It shows up in `--list`.
- Reuse built-ins as layers (`from recipes import thump`) and pad them to your length with `np.pad`.
