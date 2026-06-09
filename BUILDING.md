# Building Camel Mono

## Quick start

```bash
# 1. Fetch Commit Mono sources (cloned into vendor/, gitignored)
bash scripts/fetch_sources.sh

# 2. Create a virtualenv and install FontTools
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Build fonts
python scripts/build.py
```

Built fonts land in `dist/`:

- `CamelMonoV1-400Regular.otf`
- `CamelMonoV1-400Italic.otf`
- `CamelMonoV1-700Regular.otf`
- `CamelMonoV1-700Italic.otf`
- … (all weights 200–700 in steps of 25 by default)

## Build options

```bash
# Only regular 400
python scripts/build.py --weight 400 --style Regular

# Specific weights and styles (flags are repeatable)
python scripts/build.py --weight 400 --weight 700 --style Regular --style Italic

# Custom output directory
python scripts/build.py --output /tmp/camelmono
```

With no flags, all 22 weights (200–700 in steps of 25) × 2 styles = 44 fonts are built.

## Project layout

```text
features/camelcase.fea   # Reference GPOS implementation (not used by build)
scripts/build.py         # Generates GSUB alternates and merges into Commit Mono OTFs
scripts/fetch_sources.sh # Clone upstream Commit Mono
tests/fixtures/          # Sample identifiers for visual checks
fonts/                   # Pre-built released fonts (committed)
```

## Tuning the gap

Edit `CAMEL_GAP` in `scripts/build.py`. The default is 120 font units (UPM=1000, cell=600 — roughly 1.7px at 13px display size on a Retina screen).

The gap is split across the boundary pair:

- The glyph **before** the boundary shifts left by ~77 units (64%)
- The glyph **at the start** of the new word shifts right by ~43 units (36%)
- Glyphs at both sides of two adjacent boundaries (e.g. the `A` in `fromAPension`) get a midpoint shift to split both gaps evenly

Rebuild with `python scripts/build.py`.
