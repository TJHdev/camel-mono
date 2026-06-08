# Camel Mono

![Camel Mono example](example.gif)

`snake_case` is easier to read than `camelCase` — the underscores act as visible word separators, so your eye doesn't have to hunt for case transitions. But you can't always choose: the language, the codebase, or the team already uses camelCase, and you're not going to rename everything.

Camel Mono is a derivative of [Commit Mono](https://github.com/eigilnikolajsen/commit-mono) that adds subtle gaps at camelCase word boundaries, so `getUserName` reads more like `get User Name`. You get the visual clarity of snake_case without touching the code.

Column alignment stays monospace: glyphs shift inside their fixed-width cells using GSUB contextual substitution — pre-shifted alternate glyphs are selected at each boundary.

## Quick start

Pre-built fonts are in `fonts/`. Install the `.otf` files on your system like any other font (Windows, macOS, Linux).

To build from source:

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

## Enable camelCase spacing

The feature fires automatically via `calt` (contextual alternates), which most editors enable by default — no configuration needed.

For explicit control, use feature tag `ccas`. To keep both:

```json
"editor.fontLigatures": "'ss05', 'ccas'"
```

**VS Code**

```json
{
  "editor.fontFamily": "Camel Mono",
  "editor.fontLigatures": "'ccas'"
}
```

**JetBrains IDEs** — Settings → Editor → Font → Enable font features → add `ccas`.

**Neovim (Kitty)** — `font_features CamelMonoV1 +ccas`

**CSS**

```css
font-family: "Camel Mono", monospace;
font-feature-settings: "ccas" 1;
```

## Boundary patterns

Three boundary types are recognised:

| Pattern | Example | Description |
|---------|---------|-------------|
| `[a-z][A-Z0-9]` | `getUserName`, `get2DPoint` | Standard camelCase |
| `[A-Z0-9][A-Z0-9]…[a-z]` | `HTTPSConnection` | Acronym/number run into lowercase |
| `[a-z][A-Z0-9][A-Z0-9]…[a-z]` | `fromAPension`, `q9Do` | Lowercase into acronym start |

Digits are treated as uppercase-equivalent, so `get2DPoint` and `q19Do` produce the same gap as letter boundaries.

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

## License

Font software: SIL Open Font License 1.1 (`LICENSE-FONT`).

Based on Commit Mono by Eigil Nikolajsen. This derivative uses the name **Camel Mono** / **CamelMono**, not Commit Mono.
