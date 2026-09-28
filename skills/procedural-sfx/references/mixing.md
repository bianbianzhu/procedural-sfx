# Mixing and delivery

## Contents
1. Bus layout and what mix.py does
2. Gain staging
3. Reading the mix report
4. Fixing masking
5. Loudness targets, mastering and muxing
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
  sfx    rms(active)  -14.1 dB   sample peak  -2.4 dBFS
  masking: 8/8 events clear the rest of the mix in at least one band
  true peak +2.2 dBTP -> -1.0 dBTP (ceiling -1.0; limiter took up to 3.2 dB off the loudest transients)
  not ear-tuned yet (ask the user to listen):
    gunshot        [starting point] at 4.60s
    burst          [starting point] at 6.00s
    step           [starting point] at 9.00s, 9.45s
    explosion      [starting point] at 11.50s
```

- **N of M events placed**: events starting after `dur` or ending before 0 are skipped with a warning.
- **rms(active)** is loudness while the bus is actually sounding. In dialogue-driven pieces, keep `vo` the loudest of `vo`, `music` and the steady parts of `sfx`. Short hero hits may exceed it. The bus lines show sample peaks (cheap); the true peak is measured once, on the summed mix, in the line below.
- **masking** gives, for each event, its best signal-to-masker ratio across both channels and three bands (low/mid/high) in its most exposed 30 ms frame within two 0.3 s windows: from the event's start, and from its onset (the first 30 ms frame within 6 dB of its own loudest frame). A bed or roar that fades in is thus judged once it is up rather than only on its first near-silent frames, and a compound sound whose exposed attack comes well before a louder body is still judged on the attack. It is compared against everything else playing at that moment, so panning apart counts. Below `--min-smr` (default 0 dB) gets a `CHECK` line. Its limits: it only looks at those 0.3 s (a tail buried later is not checked), and one exposed band in one frame is enough to pass. So no `CHECK` means "probably not lost", not "clearly audible"; a sound that matters to the story still needs a listen.
- **true peak** before and after the limiter, in dBTP. "Limiter took up to X dB" is how far the loudest transient was pulled down. Above 6 dB the report adds `limiter working hard: lower gains`: that much peak reduction audibly flattens hits and can pump, so lower the gains of the loudest events instead of relying on it. A few dB on the odd gunshot crack is normal.
- **not ear-tuned yet** is a Markdown table of every placed recipe event (and the `--bed`) whose status is `starting point` or `new`, one row per recipe and argument set, with its times (the first four, then a count); `file` events are not listed. The sound column is the events' `"name"`, else the recipe's one-line description. With `--audition DIR`, `mix.py` renders each row on its own into DIR (`<recipe>.wav`, then `<recipe>--2.wav` for a second argument set), with the args and the take (seed) of its first placement, and fills in the file column. After writing the mix and stems, and before writing any audition file, it refuses an audition path that is the mix, a stem or an input (by real path and by file identity, so links and case variants count), so give `--audition` its own folder. The table is printed at column 0 after a blank line, with pipes escaped and line breaks flattened in every cell, so it pastes into Markdown as a table. These are the sounds nobody has approved by ear: paste the table into the hand-off (SKILL.md step 7). When there are none it says `every placed recipe is ear-tuned`.

## 4. Fixing masking

A `CHECK` line means that sound will probably not be heard. In order of preference:

1. **Move it in time.** Shift it a few frames off a louder hit if the picture allows, or shorten the masker's tail.
2. **Separate it in frequency.** Give it energy where the masker has none, e.g. a high-passed click layer on a step buried under a bass-heavy explosion.
3. **Pan it apart.** Put it on the other side from the masker (±0.3–0.5).
4. **Raise its gain.** This is the last resort, because it makes everything else relatively quieter.
5. **Cut it.** If it doesn't matter to the story, cut it. Fewer, clearer sounds read better than many buried ones.

## 5. Loudness targets, mastering and muxing

| Delivery | Command |
| --- | --- |
| Audio only | `sh scripts/master.sh mix.wav final.wav [LUFS=-14] [dBTP=-1]` |
| Under a video | `sh scripts/mux.sh video.mp4 mix.wav out.mp4 [LUFS=-14] [dBTP=-1]` |

| Destination | Integrated | True peak |
| --- | --- | --- |
| YouTube, social, web embeds | −14 LUFS | −1 dBTP |
| Podcasts, Apple platforms | −16 LUFS | −1 dBTP |
| EU broadcast (EBU R128) | −23 LUFS | −1 dBTP |
| US broadcast (ATSC A/85) | −24 LKFS | −2 dBTP |

**Linear gain only.** `master.sh` measures integrated loudness and true peak (ffmpeg `ebur128`, the BS.1770 meter), computes `gain = target − measured`, and applies exactly that with ffmpeg's `volume` filter. Nothing else touches the audio, so the dynamics you mixed are the dynamics that ship. ffmpeg's `loudnorm` is not used: when a target is out of reach its "linear" mode silently switches to dynamic processing, which compresses and can pump, and its own first-pass measurement read sparse SFX mixes about 0.6 LU loud. `master.sh` writes 24-bit PCM wav at the mix's sample rate: it plays everywhere, and with the true peak under the limit nothing can clip in fixed point. It renders to a temp file next to the output, re-measures it and only then moves it into place, so a failed or interrupted run leaves no partial file; it refuses an output that is the input, including through a symlink or hard link. The re-measured loudness must land within 0.15 LU of the target (0.1 plus the meter's one-decimal rounding). Integrated loudness is gated (blocks under −70 LUFS, and more than 10 LU under the ungated level, are left out), so for a very quiet target a gain change can move blocks across a gate and the first gain can miss; `master.sh` then corrects the gain, always re-applied to the original, up to three more times, and says so in its result line. The scripts set `LC_ALL=C`, so a comma-decimal locale cannot break their arithmetic.

`mux.sh` copies the video stream and encodes the audio as AAC 256k into an `.mp4`, `.m4v`, `.mov` or `.mkv` (other containers such as `.webm` cannot hold AAC; H.264/HEVC go in any of them, VP8/VP9 in `.mkv`). The video is the timeline: its span is read from its packet timestamps (not from container durations, which an `.mkv` does not give per stream and which can include a longer original audio track), every video packet is kept (it does not use `-shortest`, which drops the last frames of a copied B-frame video when the audio ends at the same instant), and the mix is padded with silence or trimmed to the video's span *before* `master.sh` runs, so the loudness target applies to exactly the audio that ships; a warning says so when the mix length differs by more than 50 ms. A video shorter than 0.4 s is refused, since loudness can't be measured there. It needs ffmpeg 4.2 or newer (for `apad=whole_dur`) and checks for it. The mix **replaces** any audio the video already has, with a warning; to keep it, extract it and pass it to `mix.py --music`. Before the mp4 replaces anything at the output path it is built in a private temp folder next to it (`mktemp -d`, so nothing can be planted at its paths) and verified: the same video packet count as the source and the same span to half a frame (containers round timestamps, `.mkv` to 1 ms), audio ending with the video, loudness within 0.5 LU of the target and true peak at or under the limit after AAC. AAC can add a few tenths of a dB of overs to a master that sits right at the limit; if that crosses it, nothing is written and the error names the quieter target that fits.

**When the target is out of reach.** If the gain would put the true peak over the limit, nothing is written and the error names the loudest target that fits, e.g. `The loudest target a clean gain change can reach is -15.6 LUFS.`. Either accept it (pass it as the LUFS argument; being a dB or two under a platform target just plays a little quieter there) or make the mix denser: lower the gain of the few loudest events (usually gunshots, explosions, hard impacts) in events.json, remix, and master again. Their peaks cap the whole mix, so taking 3 dB off them buys up to 3 dB of loudness for everything else. Sparse SFX-only tracks (a few loud hits over near-silence) often can't reach −14 LUFS by gain alone; delivering them a little quieter, around −15 to −16 LUFS, is the intended trade-off that keeps their transients intact. Both scripts also refuse silent or sub-0.4 s audio with an explanation, since loudness can't be measured there.

Don't normalise the mix itself. Leave it at its natural level (the limiter keeps its true peak under the ceiling) and master once at delivery.

## 6. Hybrid mixes with recorded audio

Any audio file can be an event: `{"t": 3.2, "type": "file", "file": "sfx/real_glass.wav", "bus": "sfx", "gain": 0.5}`. Use this for voice lines (TTS or recorded), licensed samples, or music stems. Files are resampled to 48 kHz. Voice lines on the `vo` bus duck the music automatically. To give a recorded voice a radio or phone sound, process it with `radio_fx(read_wav(path, mono=True))` inside a custom recipe and trigger that recipe instead.
