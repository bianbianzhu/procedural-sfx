# Syncing sounds to picture

Put sounds on the timeline where the animation says things happen, never where it looks about right. If the event times come from the same source as the motion, sync takes care of itself whenever the animation is re-timed.

## Contents
1. events.json schema
2. Getting event times out of an animation stack
3. Anticipation and offsets
4. Checking sync

## 1. events.json schema

```json
{
  "dur": 14.0,
  "events": [
    {"t": 4.60, "type": "gunshot", "args": {"kind": "pistol"}, "gain": 0.7, "pan": 0.3},
    {"t": 2.00, "type": "file", "file": "voices/line01.wav", "bus": "vo"}
  ]
}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `dur` | recommended | Mix length in seconds. Use the video's duration exactly. |
| `t` | yes | Seconds from the start. From frames: `t = frame / fps`. |
| `type` | yes | Recipe name (built-in or from `--recipes`), or `"file"` for an audio file. |
| `args` | no | Keyword arguments for the recipe. |
| `gain` | no | Linear gain. Default: `--gains` map by type, else 0.5. |
| `pan` | no | −1 left … 1 right. Follow the on-screen position: `pan = (x / width) * 2 - 1`, scaled by ~0.6 so nothing sits hard left or right. |
| `bus` | no | `sfx` (default) · `vo` (ducks music; default for files) · `music` · `bed`. |
| `seed` | no | Pin this event's randomness. Default is derived from type + t, so events are independent of each other. |
| `file` | for `"file"` | Path relative to the events file. |

`"ev"` is accepted as an alias for `"events"`.

## 2. Getting event times out of an animation stack

The rule is the same everywhere: **the code that decides when something moves also writes the event.**

**Deterministic web animation (a `render(t)` page rendered frame by frame).** Expose the list on the page and read it out with a headless browser:

```js
const HIT = 4.6;                                    // the constant that drives the muzzle flash
window.EV = [
  { t: HIT, type: 'gunshot', args: { kind: 'pistol' }, pan: 0.3 },
  { t: HIT + 0.35, type: 'clack', args: { pitch: 1.6 } },   // shell casing lands
];
window.DUR = 14;
```

```js
// export-events.mjs — npm i playwright-core; uses the local Chrome
import { chromium } from 'playwright-core'; import fs from 'fs';
const b = await chromium.launch({ channel: 'chrome' }); const p = await b.newPage();
await p.goto(process.argv[2]); await p.waitForFunction(() => window.DUR);
fs.writeFileSync('events.json', JSON.stringify(await p.evaluate(() => ({ dur: window.DUR, events: window.EV || [] }))));
await b.close();
```

**Python animation (matplotlib, manim, PIL frame loops, pygame).** Append events wherever the animation code triggers a change, then `json.dump` at the end of the render. With manim, record `self.renderer.time` right before `self.play(...)`.

**Remotion / React video.** Keep a `sfx.ts` array of `{frame, type, ...}` imported by both the composition and a small node script that writes events.json (`t = frame / fps`).

**Game engines (Unity, Godot, Bevy) or simulations.** Log `{t: sim_time, type}` to a file whenever a collision, shot or pickup happens during a deterministic replay. Physics collisions are the best source of impact timing there is.

**Existing video you did not make.** There is no source of truth, so step through frames (`ffmpeg -ss T -i in.mp4 -frames:v 1 f.png`) and note the first frame of each contact, flash or cut. Write those down as `frame / fps`.

## 3. Anticipation and offsets

The event time is when the *sound's reference point* should land, and that is not always the sound's first sample:

| Sound | Put `t` at | Why |
| --- | --- | --- |
| Impacts, gunshots, clicks, footsteps | The contact or flash frame exactly | The attack is the sound's reference point |
| `whoosh` (length d) | Pass-by frame − d/2 | Its loudest point is the middle |
| Risers, charge-ups, `laser` charging | Payoff frame − their length | They should resolve on the payoff |
| Explosions | The flash frame; distant ones later by distance / 343 m/s | Sound is slower than light, and audiences read the delay as scale |
| Voice lines | 2–4 frames before the mouth opens, if lip-sync is visible | Speech onsets are soft |

Layered moments are several events on nearby times, e.g. gunshot at T, casing clack at T + 0.35, a distant echo at T + 0.4 on the `bed` bus.

## 4. Checking sync

- `mix.py` places samples at `round(t * 48000)`, so a sound is never off by more than a sample. Visible drift means the event times are wrong.
- Render stills at a few event times (`ffmpeg -ss <t> -i out.mp4 -frames:v 1 check.png`) and confirm the visual event is on screen.
- If the video's fps and the times disagree (e.g. frames exported at 24 fps but times computed at 30), every event drifts proportionally. Recompute from frames.
