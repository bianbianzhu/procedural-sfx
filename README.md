# procedural-sfx

An agent skill for making sound effects from code (numpy + scipy, no sample libraries) and mixing them frame-accurately under a video or animation.

- 18 built-in recipes: impacts, footsteps, whooshes, UI sounds, gunshots, explosions, sci-fi, ambience beds
- Event-driven mixer: `events.json` → stereo mix with voice ducking, limiter, stems, and a per-event masking report
- Analysis tools so an agent that cannot listen can still check its sounds by numbers
- Two-pass loudness normalisation and muxing with ffmpeg

## Install

```bash
npx skills add bianbianzhu/procedural-sfx
```

Or copy `skills/procedural-sfx/` into your agent's skills directory (for Claude Code: `~/.claude/skills/` or `.claude/skills/` in a project).

Runtime dependencies: Python ≥ 3.9 with `numpy`, `scipy`, `soundfile` (`pip install -r skills/procedural-sfx/scripts/requirements.txt`). `ffmpeg` is optional, for muxing and loudness normalisation.

## Layout

```
skills/procedural-sfx/
├── SKILL.md        entry point: when to use, workflow, script index
├── scripts/        runnable tools (synthesis library, recipes, render, analyze, mix, mux)
├── references/     loaded on demand: sound design, recipe catalog, sync, mixing, troubleshooting
└── assets/         example events file and a custom-recipe template
```

## License

MIT
