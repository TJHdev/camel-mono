# Camel Mono

A derivative of [Commit Mono](https://github.com/eigilnikolajsen/commit-mono) with an optional OpenType feature that adds subtle gaps at camelCase word boundaries (`getUserName` reads more like `get User Name`).

Column alignment stays monospace: glyphs shift inside their fixed-width cells, using the same GPOS technique as Commit Mono smart kerning.

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

- `CamelMono-400-Regular.otf`
- `CamelMono-400-Italic.otf`
- `CamelMono-700-Regular.otf`
- `CamelMono-700-Italic.otf`

Install the `.otf` files on your system like any other font (Windows, macOS, Linux).

## Enable camelCase spacing

The feature tag is `ccas`. Commit Mono’s smart kerning (`ss05`) is preserved — enable both if you want:

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

**Neovim (Kitty)** — `font_features CamelMono +ccas`

**CSS**

```css
font-family: "Camel Mono", monospace;
font-feature-settings: "ccas" 1;
```

## Project layout

```text
features/camelcase.fea   # OpenType rules (edit gap size here)
scripts/build.py         # Merge feature into Commit Mono OTFs
scripts/fetch_sources.sh # Clone upstream Commit Mono
tests/fixtures/          # Sample identifiers for visual checks
vendor/commit-mono/      # Upstream sources (not committed)
dist/                    # Built fonts (not committed)
```

## Tuning the gap

Edit `features/camelcase.fea`. The current values split a ~30 unit gap across the pair:

- lowercase shifts left by 12 units before an uppercase letter
- uppercase shifts right by 18 units after a lowercase letter

Rebuild with `python scripts/build.py`.

## Build options

```bash
# Only regular 400
python scripts/build.py --weight 400 --style Regular

# Custom output directory
python scripts/build.py --output /tmp/camelmono
```

## License

Font software: SIL Open Font License 1.1 (`LICENSE-FONT`).

Based on Commit Mono by Eigil Nikolajsen. This derivative uses the name **Camel Mono** / **CamelMono**, not Commit Mono.
