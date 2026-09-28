#!/usr/bin/env python3
"""Check that the dependencies are present. Exit code 0 = ready for synthesis and mixing."""
import importlib, shutil, sys

ok = True
print(f'python     {sys.version.split()[0]}' + ('' if sys.version_info >= (3, 9) else '   NEED >= 3.9'))
ok &= sys.version_info >= (3, 9)
for mod in ('numpy', 'scipy', 'soundfile'):
    try:
        m = importlib.import_module(mod); print(f'{mod:10s} {getattr(m, "__version__", "?")}')
    except ImportError:
        print(f'{mod:10s} MISSING   -> pip install -r requirements.txt'); ok = False
ff = shutil.which('ffmpeg')
print(f'ffmpeg     {ff or "missing (optional: only needed for mux.sh / loudness)"}')
sys.exit(0 if ok else 1)
