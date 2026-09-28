# Designing a new sound

Read this before writing a recipe that the built-ins don't cover.

## Contents
1. The three-layer model
2. From a description to a recipe
3. Which number changes what you hear
4. Rough metric targets (for `analyze.py`)
5. Worked example: a heavy door slam

## 1. The three-layer model

Almost every effect is three layers added together, followed by optional saturation and a normalise:

| Layer | Duration | Job | Usual ingredient |
| --- | --- | --- | --- |
| **Attack** (transient) | 1–10 ms | Tells the ear *what material* is hitting | High-passed noise × very short `env_exp` (tau 0.001–0.004) |
| **Body** | 10–150 ms | Pitch, weight, size | Sines at resonant frequencies (often gliding down), or low/band-passed noise, tau 0.01–0.1 |
| **Tail** | 0.2–2 s | Space and distance | Band-passed noise with a long envelope at 10–30% level, or `echo()` |

```python
x = attack * a + body * b + tail * c
x = sat(x, drive)        # only for sounds that should feel forceful (guns, explosions, distorted radio)
return norm(x) * v
```

Build and check one layer at a time: return just the attack, render it, then add the body, and so on. Most "sounds wrong" problems come from one layer being too loud.

## 2. From a description to a recipe

1. Write one sentence: *what is hitting what, how big, where*. For example: "a heavy wooden door slams shut in a narrow hallway".
2. Split it into layers: latch click (metal attack), door mass (low body), panel rattle (wood body), hallway (short echo tail).
3. Pick ingredients for each layer from the table below.
4. Set durations: the whole sound should be only as long as its tail. Longer arrays waste time and hide clicks at the end.
5. Render, `analyze.py --bands`, compare against section 4, and adjust.

| Material or source | Ingredient |
| --- | --- |
| Hard plastic | HP noise > 2.5 kHz attack + 2–3 sines 1.5–5 kHz, tau ~10 ms |
| Wood | BP noise 300–2500 Hz + one sine 150–400 Hz, tau 10–30 ms |
| Metal (small) | Several inharmonic sines 2–8 kHz, long tau (0.1–0.5 s), highs decay first |
| Metal (large: bell, gong) | Partials at non-integer ratios (e.g. 1, 1.5, 2, 3, 4), tau 0.3–2 s |
| Glass | Very high sines (4–10 kHz), bright and short attack, a scatter of tiny clicks for shards |
| Soft (cloth, carpet, flesh) | LP noise < 1 kHz, a 5–10 ms linear attack (`env_ad`), no HF attack layer |
| Air (whoosh, wind, breath) | BP noise with a moving centre frequency; sin² fade in/out |
| Pressure (boom, blast) | LP noise < 600 Hz + sine 40–90 Hz gliding down, then `sat()` |
| Electricity / sci-fi | Sine or saw sweeps, detuned pairs, fast amplitude modulation (30–80 Hz) |
| Engines / fire | Brown noise LP 200–700 Hz, slow amplitude wobble, sparse HF crackle |
| Creaks / friction | Sawtooth with wobbling frequency, band-passed, amplitude stutter |

## 3. Which number changes what you hear

| To make it… | Change |
| --- | --- |
| Crisper, harder | Shorter attack tau; raise the attack's high-pass (2.5 → 4 kHz) |
| Duller, softer, further away | Low-pass everything (300–800 Hz); drop the attack layer; lower level |
| Heavier, bigger | Add or lower a 40–90 Hz sine in the body and make it glide down (`f*t*(1-0.3*t)` or `sweep(60, 25, d)`) |
| More "pitched" / material-like | Replace body noise with 2–5 sines at non-integer ratios |
| Bigger space (room, hall, canyon) | Longer, louder tail; `echo(delay=.05–.3, feedback=.3–.5)`; more damping for far walls |
| More aggressive | More `sat()` drive (2 → 5); more attack |
| Cartoonier | Less noise, more pure sweeps (`pop`-style); exaggerated pitch glides; less saturation |
| More motion | Sweep a band-pass centre (`whoosh`), pan from −1 → 1 across the event |
| Less synthetic on repeats | Randomise pitch ±5–10%, level ±20%, pan ±0.2 per trigger; `uniform()` inside the recipe |

## 4. Rough metric targets

These are heuristics for catching mistakes, not rules. Compare `analyze.py --bands` output against them (the built-in recipes fall inside these ranges). The last column uses the band names `--bands` prints: sub < 60 Hz, low 60–250, lowmid 250–1k, mid 1–4k, high 4–10k, air > 10k.

| Sound | attack | t-20 | centroid | Energy mostly in |
| --- | --- | --- | --- | --- |
| UI click / tick | < 2 ms | 10–60 ms | 1.5–5 kHz | mid, high |
| Footstep (hard) | < 2 ms | 10–60 ms | 2–6 kHz | mid, high |
| Soft impact / thump | 2–10 ms | 100–300 ms | 50–200 Hz | sub, low |
| Gunshot | < 3 ms | 100–400 ms | 800–3000 Hz | low, lowmid, mid |
| Explosion | 5–30 ms | 0.8–2 s | 40–300 Hz | sub, low |
| Whoosh | 80–250 ms (it swells) | ≈ a third of its length | 1–4 kHz | mid, high |
| Bell / ding | < 2 ms | > 800 ms | 1–3 kHz | mid |
| Rumble bed | slow | continuous | < 100 Hz | sub, low |

Red flags:
- **t-20 shows `>end`** on a one-shot sound: it is still loud when the array stops. `add()` fades the last 5 ms so it won't click, but it will stop abruptly. Make the array longer or the tail's tau shorter. (`>end` on t-40 alone is normal for short sounds.)
- **Centroid far outside the row**: a layer is too loud (e.g. a "gunshot" at 300 Hz is all boom and no crack).
- **Peak much higher than RMS (> 25 dB)** on a sustained sound: it is spiky. Smooth the envelope or lower the transient.

## 5. Worked example: a heavy door slam

`assets/recipe_template.py` contains `door_slam`, built with the method above:

- **Attack**: `hp(noise(d), 3500) * env_exp(d, .002)` is the metal latch.
- **Body**: the built-in `thump(1, 60)` supplies the door's mass, padded to the shared length with `np.pad`. Reusing a recipe as a layer is normal.
- **Body texture**: band-passed noise with a 31 Hz amplitude wobble is the wooden panel rattling.
- **Tail**: `echo(x, delay=.045, feedback=.3, taps=3)` is a small hallway, switched by a `room=True` argument so one recipe covers two scenes.

Render it with `python scripts/render_sfx.py --recipes assets/recipe_template.py door_slam -o door.wav`.
