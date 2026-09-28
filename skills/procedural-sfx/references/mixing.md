# Mixing and delivery

## Contents
1. Bus layout and what mix.py does
2. Gain staging
3. Reading the mix report
4. Fixing masking
5. Loudness targets and muxing
6. Hybrid mixes with recorded audio

## 1. Bus layout and what mix.py does

| Bus | Holds | Bus gain | Notes |
| --- | --- | --- | --- |
| `vo` | Voice, dialogue | 1.25 | The loudest element. Anything on it ducks `music`. |
| `sfx` | Every recipe event (default) | 0.9 | |
| `music` | `--music` file, `bus: music` events | 1.0 | Ducked by `--duck-db` (default 8 dB) under voice, with 0.25 s smoothing |
| `bed` | `--bed RECIPE`, `bus: bed` events | 1.0 | Room tone, rumble, wind; `--bed-gain` default 0.03 (about −30 dB) |

After summing the buses, `mix.py` checks for NaN, applies a linked stereo look-ahead **true-peak** limiter at `--ceiling` (default −1.0 dBTP, allowed −6 … 0), writes a 32-bit float wav at 48 kHz, and optionally writes each bus to `--stems DIR` (unlimited, also float, so a hot bus is not clipped on disk) for inspection or for someone else to remix.

Why true peak: the waveform a DAC or an AAC/MP3 decoder rebuilds between samples can rise well above the samples themselves. A saturated noise burst is the worst case: the built-in `gunshot` peaks at −1.9 dBFS by samples but +2.2 dBTP, so a mix that looked safe clipped once transcoded. The limiter detects peaks on oversampled copies (`sfxkit.true_peak`: 8x for accuracy, plus a 4x meter-style filter that matches ffmpeg's `ebur128` to within 0.05 dB), re-measures its own output and trims any smoothing overshoot, so the written file honours the ceiling on both. A mix whose true peak is already under the ceiling is written untouched, sample for sample.

## 2. Gain staging

Recipes are all normalised to peak 1, so `gain` in events.json sets the balance on its own. Sensible starting gains:

| Role | gain |
| --- | --- |
| Hero hits (gunshot, explosion, key impact) | 0.6–0.8 |
| Supporting foley (steps, clicks, cloth, casings) | 0.2–0.4 |
| UI feedback over narration | 0.2–0.35 |
| Whooshes and transitions | 0.25–0.4 |
| Beds and ambience | 0.02–0.05 |

Put type defaults in a `--gains gains.json` map (`{"step": 0.3, "gunshot": 0.7}`) and override per event only when a moment needs it.

## 3. Reading the mix report

```
mix.wav  14.00s  8 of 8 events placed
  sfx    rms(active)  -14.1 dB   true peak  +2.2 dBTP
  masking: 8/8 events clear the rest of the mix in at least one band
  true peak +2.2 dBTP -> -1.0 dBTP (ceiling -1.0; limiter took up to 3.2 dB off the loudest transients)
```

- **N of M events placed**: events starting after `dur` or ending before 0 are skipped with a warning.
- **rms(active)** is loudness while the bus is actually sounding. In dialogue-driven pieces, keep `vo` the loudest of `vo`, `music` and the steady parts of `sfx`. Short hero hits may exceed it.
- **masking** gives, for each event, its best signal-to-masker ratio across both channels and three bands (low/mid/high) in its most exposed 30 ms frame within its first 0.3 s. It is compared against everything else playing at that moment, so panning apart counts. Below `--min-smr` (default 0 dB) gets a `CHECK` line. Its limits: it only looks at the first 0.3 s (a tail buried later is not checked), and one exposed band in one frame is enough to pass. So no `CHECK` means "probably not lost", not "clearly audible"; a sound that matters to the story still needs a listen.
- **true peak** before and after the limiter, in dBTP. "Limiter took up to X dB" is how far the loudest transient was pulled down. Above 6 dB the report adds `limiter working hard: lower gains`: that much peak reduction audibly flattens hits and can pump, so lower the gains of the loudest events instead of relying on it. A few dB on the odd gunshot crack is normal.

## 4. Fixing masking

A `CHECK` line means that sound will probably not be heard. In order of preference:

1. **Move it in time.** Shift it a few frames off a louder hit if the picture allows, or shorten the masker's tail.
2. **Separate it in frequency.** Give it energy where the masker has none, e.g. a high-passed click layer on a step buried under a bass-heavy explosion.
3. **Pan it apart.** Put it on the other side from the masker (±0.3–0.5).
4. **Raise its gain.** This is the last resort, because it makes everything else relatively quieter.
5. **Cut it.** If it doesn't matter to the story, cut it. Fewer, clearer sounds read better than many buried ones.

## 5. Loudness targets and muxing

`sh scripts/mux.sh video.mp4 mix.wav out.mp4 [LUFS] [dBTP]` measures in a first pass, then normalises in a second (lands within about ±0.5 LU of the target; a single pass drifts further). It refuses silent or sub-0.4 s audio with an explanation, since loudness can't be measured there. It copies the video stream, encodes AAC 256k, and prints the measured integrated loudness and peak of the result.

| Destination | Integrated | True peak |
| --- | --- | --- |
| YouTube, social, web embeds | −14 LUFS | −1 dBTP |
| Podcasts, Apple platforms | −16 LUFS | −1 dBTP |
| EU broadcast (EBU R128) | −23 LUFS | −1 dBTP |
| US broadcast (ATSC A/85) | −24 LKFS | −2 dBTP |

Don't normalise the mix itself. Leave it at its natural level (the limiter keeps it safe) and normalise once at delivery.

## 6. Hybrid mixes with recorded audio

Any audio file can be an event: `{"t": 3.2, "type": "file", "file": "sfx/real_glass.wav", "bus": "sfx", "gain": 0.5}`. Use this for voice lines (TTS or recorded), licensed samples, or music stems. Files are resampled to 48 kHz. Voice lines on the `vo` bus duck the music automatically. To give a recorded voice a radio or phone sound, process it with `radio_fx(read_wav(path, mono=True))` inside a custom recipe and trigger that recipe instead.
