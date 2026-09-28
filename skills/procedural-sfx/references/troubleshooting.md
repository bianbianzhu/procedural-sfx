# Troubleshooting and QA

## Contents
1. Listener complaints → fixes
2. Errors and odd behaviour
3. Final QA checklist

## 1. Listener complaints → fixes

| They say | Likely cause | Fix |
| --- | --- | --- |
| "Too thin / no weight" | No low body | Add a 40–90 Hz sine gliding down; lengthen body tau |
| "Muddy / boomy" | Too much < 250 Hz, or low tails overlapping | High-pass supporting foley at 150–300 Hz; shorten low tails |
| "Harsh / piercing" | Too much 2–5 kHz, or saturation drive too high | Lower the attack level; lower `sat` drive; low-pass at 8–10 kHz |
| "Sounds fake / robotic" on repeats | Identical triggers | Randomise pitch ±5–10%, gain ±20%, pan ±0.2 per event |
| "Sounds like a synth, not a thing" | Pure sines dominate | More noise in the attack, inharmonic partials, shorter taus |
| "Clicks at the end" | Array cut while ringing | Longer array or shorter tail (`add()` already fades 5 ms, so a click means a hard cut *inside* the recipe, e.g. a mask like `(t > .01)`) |
| "Click at the start" of a soft sound | Instant attack | `env_ad(d, .005, tau)` instead of `env_exp` |
| "Out of sync" | Event times not from the animation, or fps mismatch | See `event-sync.md` §4 |
| "Can't hear X" | Masked | The `CHECK` line in the mix report, and `mixing.md` §4 |
| "Everything is loud, nothing hits" | No dynamics: dense sound, no silence | Remove the least important sounds; leave a gap before hero hits; lower the bed |
| "Too cartoony" / "not cartoony enough" | Style mismatch | Cartoony: pure sweeps, exaggerated glides, little saturation. Realistic: noise, inharmonic partials, short reflections |

## 2. Errors and odd behaviour

The scripts exit 1 on input problems and print `error: <what and where>` followed by `fix: <what to do>`. Act on the fix line first. The table covers the remaining cases:

| Symptom | Cause | Fix |
| --- | --- | --- |
| `operands could not be broadcast … (2880,) (2881,)` | Array lengths computed with different rounding | Always build lengths with `n_(d)` / `t_(d)` / `noise(d)` for the same `d` |
| Adding one event changed how others sound | Shared RNG in your own loop | Only through `mix.py` (it reseeds per event); in your own scripts call `reseed(n)` per sound |
| `Digital filter critical frequencies must be 0 < Wn < fs/2` | Raw `butter` with a frequency ≥ 24 kHz | Use `bp/lp/hp` from sfxkit; they clamp below Nyquist |
| `error: … no recipe named 'X'` | Type typo, or `--recipes` missing | Follow the "did you mean" hint; `render_sfx.py --recipes file.py --list` shows what is registered |
| `error: X (…): unknown argument(s)` | An `args` key the recipe doesn't take | The message lists the accepted arguments and their defaults |
| Mix is slow | `compress()` is a per-sample Python loop | Use it on voice files only, once, and cache the result |
| `error: --ceiling is a true-peak ceiling in dBTP` | An old linear value such as `--ceiling 0.95` | Pass dBTP: `-1` (default) or `-2` for US broadcast |
| Sample peak looks safe but the file clips after encoding | Inter-sample (true) peaks: saturated noise bursts overshoot between samples | Trust the report's `true peak … dBTP`, not the sample peak; `mix.py` limits true peak |
| `error: X produced NaN/inf` | Division by zero or `log(0)` in a recipe | Render it alone with `render_sfx.py` and fix the maths |
| Recipe from a custom file not found | Function name starts with `_`, or is imported rather than defined there | Define it in that file; only its own public functions are registered |
| Loudness after delivery is off by ~0.5 LU | `loudnorm` (single- or two-pass) elsewhere in the chain, or normalising twice | Master once with `master.sh` / `mux.sh`; they apply one linear gain measured with `ebur128` |
| `error: … the loudest target a clean gain change can reach is X LUFS` | The loudest events' true peaks leave too little room to raise the rest | Pass X as the LUFS argument, or lower the gains of the loudest events, remix, master again (`mixing.md` §5) |

## 3. Final QA checklist

Run through this before handing over:

- [ ] `check_env.py` passes; every recipe used renders alone without error.
- [ ] Each new or changed recipe has been through `analyze.py --bands` and sits near its row in `design-method.md` §4.
- [ ] Repeated sounds were auditioned with `render_sfx.py … --variants 4` and vary.
- [ ] `mix.py` report: no `warning`, no `CHECK` lines (or each one consciously accepted), no `limiter working hard`; the written true peak is at or under the ceiling.
- [ ] `vo` is the loudest sustained bus when there is dialogue; the bed sits 25 dB or more below it.
- [ ] `master.sh` / `mux.sh` printed a result within ±0.5 LU of the target (or you knowingly accepted the reachable one), with the true peak under the limit.
- [ ] Stills at three or more event times show the matching visual moment.
- [ ] Numbers re-measured after the last change (re-run `analyze.py` on changed recipes and `mix.py` on the final events); nothing above is from an older render.
- [ ] The "not ear-tuned yet" list from the final `mix.py` report is handed to the user as a table (sound · recipe · status · file to audition), each file rendered on its own, with a plain request to listen to every `starting point` and `new` sound.
