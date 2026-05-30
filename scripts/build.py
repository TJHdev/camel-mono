#!/usr/bin/env python3
"""Build CamelMono from Commit Mono OTF sources + camelcase OpenType feature."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import string
import tempfile

from fontTools.feaLib.builder import addOpenTypeFeatures
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor" / "commit-mono"
FONTLAB = VENDOR / "src" / "fonts" / "fontlab"
DIST = ROOT / "dist"

# Gap in font units (UPM=1000, cell=600). ~70 units ≈ 1px at 13px display size.
CAMEL_GAP = 120

FONT_NAME = "CamelMono"
FAMILY_NAME = "Camel Mono"

WEIGHTS = range(200, 725, 25)  # 200, 225, 250, … 700

DEFAULT_STYLES = tuple(
    (w, s) for w in WEIGHTS for s in ("Regular", "Italic")
)


def find_source(weight: int, style: str) -> Path:
    pattern = re.compile(rf"CommitMonoV\d+-{weight}{style}\.otf$")
    matches = sorted(FONTLAB.glob(f"CommitMono*-{weight}{style}.otf"))
    matches = [path for path in matches if pattern.search(path.name)]
    if not matches:
        raise FileNotFoundError(
            f"No Commit Mono source for {weight} {style} under {FONTLAB}. "
            "Run scripts/fetch_sources.sh first."
        )
    return matches[-1]


def style_names(weight: int, style: str) -> tuple[str, str, str]:
    # Each weight lives in its own preferred family so editors list them all.
    weight_family = f"{FAMILY_NAME} {weight}"
    subfamily = "Italic" if style == "Italic" else "Regular"
    full_name = f"{weight_family} {subfamily}" if style == "Italic" else weight_family
    postscript_name = f"{FONT_NAME}-{weight}{style}"
    return subfamily, full_name, postscript_name, weight_family


def rename_font(font: TTFont, weight: int, style: str) -> None:
    subfamily, full_name, postscript_name, weight_family = style_names(weight, style)
    name_table = font["name"]

    replacements = {
        1:  weight_family,   # Family name (legacy; one entry per weight)
        2:  subfamily,       # Subfamily (Regular / Italic)
        4:  full_name,       # Full name
        6:  postscript_name, # PostScript name
        16: weight_family,   # Preferred family (lets editors group by weight)
        17: subfamily,       # Preferred subfamily
    }

    for name_id, value in replacements.items():
        name_table.setName(value, name_id, 3, 1, 0x409)
        name_table.setName(value, name_id, 1, 0, 0)

    font["OS/2"].usWeightClass = weight

    selection = 0
    if style == "Italic":
        selection |= 1
    font["OS/2"].fsSelection = selection

    if "head" in font:
        mac_style = 0
        if style == "Italic":
            mac_style |= 1 << 1
        font["head"].macStyle = mac_style

    if "CFF " in font:
        top_dict = font["CFF "].cff.topDictIndex[0]
        top_dict.FullName = full_name
        top_dict.FamilyName = weight_family
        top_dict.Weight = str(weight)


def make_shifted_alternates(
    font: TTFont,
    glyph_names: list[str],
    shift: int,
    suffix: str,
) -> list[str]:
    """
    For each glyph in glyph_names, create a <name><suffix> alternate whose
    outline is shifted horizontally by `shift` font units (positive = right,
    negative = left). Advance width is unchanged.

    Returns the list of alternate glyph names in the same order.
    """
    top_dict = font["CFF "].cff.topDictIndex[0]
    cs = top_dict.CharStrings
    glyph_order = font.getGlyphOrder()
    alt_names: list[str] = []

    for gname in glyph_names:
        alt = f"{gname}{suffix}"
        adv_w = font["hmtx"].metrics[gname][0]

        rec = RecordingPen()
        cs[gname].draw(rec)

        t2 = T2CharStringPen(adv_w, cs)
        xpen = TransformPen(t2, (1, 0, 0, 1, shift, 0))
        rec.replay(xpen)

        new_cs = t2.getCharString(private=cs[gname].private)

        idx = cs.charStringsIndex
        cs.charStrings[alt] = len(idx.items)
        idx.items.append(new_cs)

        glyph_order.append(alt)
        font["hmtx"].metrics[alt] = font["hmtx"].metrics[gname]
        alt_names.append(alt)

    return alt_names


def create_camel_alternates(font: TTFont, gap: int) -> dict:
    """
    Create alternates for both sides of each camelCase boundary:
      - .camelPre  for a-z: outline shifted LEFT  by gap*0.80  (lowercase before uppercase)
      - .camel     for A-Z: outline shifted RIGHT by gap*0.20  (uppercase starting a word)
      - .camelPreU for A-Z: outline shifted LEFT  by gap*0.80  (uppercase ending an acronym,
                                                                 e.g. the S in HTTPSConnection)

    Splitting the gap symmetrically across the boundary means neither
    letter looks like it's drifting into its neighbour.

    Returns a dict with keys 'lower_orig', 'lower_alt', 'upper_orig', 'upper_alt',
    'upper_pre_alt'.
    """
    cmap = font.getBestCmap()
    lower_names = sorted(
        (cmap[ord(c)] for c in string.ascii_lowercase if ord(c) in cmap),
        key=font.getGlyphOrder().index,
    )
    upper_names = sorted(
        (cmap[ord(c)] for c in string.ascii_uppercase if ord(c) in cmap),
        key=font.getGlyphOrder().index,
    )

    left_shift  = round(gap * 0.80)
    right_shift = gap - left_shift
    lower_alts     = make_shifted_alternates(font, lower_names, shift=-left_shift, suffix=".camelPre")
    upper_alts     = make_shifted_alternates(font, upper_names, shift=right_shift,  suffix=".camel")
    upper_pre_alts = make_shifted_alternates(font, upper_names, shift=-left_shift,  suffix=".camelPreU")

    return {
        "lower_orig":    lower_names,
        "lower_alt":     lower_alts,
        "upper_orig":    upper_names,
        "upper_alt":     upper_alts,
        "upper_pre_alt": upper_pre_alts,
    }


def build_camel_gsub(font: TTFont, names: dict) -> None:
    """
    Inject substitution lookups and chaining contextual rules for two boundary patterns:

    1. [a-z] immediately followed by [A-Z]  (e.g. camelCase, getUserName)
       • the lowercase gets its .camelPre  alternate (shifted left)
       • the uppercase gets its .camel     alternate (shifted right)

    2. [A-Z] followed by [A-Z] followed by [a-z]  (e.g. HTTPSConnection → gap between S and C)
       • the first uppercase gets its .camelPreU alternate (shifted left)
       • the second uppercase gets its .camel    alternate (shifted right)

    Both replacements happen in one pass — no GPOS, no pixel snapping.
    Feature 'calt' fires automatically; 'ccas' for explicit toggling.
    """
    lower_str         = " ".join(names["lower_orig"])
    lower_alt_str     = " ".join(names["lower_alt"])
    upper_str         = " ".join(names["upper_orig"])
    upper_alt_str     = " ".join(names["upper_alt"])
    upper_pre_alt_str = " ".join(names["upper_pre_alt"])

    fea = f"""
@lower            = [{lower_str}];
@lower_camel      = [{lower_alt_str}];
@upper            = [{upper_str}];
@upper_camel      = [{upper_alt_str}];
@upper_camel_pre  = [{upper_pre_alt_str}];

lookup camel_lower_subst {{
    sub @lower by @lower_camel;
}} camel_lower_subst;

lookup camel_upper_subst {{
    sub @upper by @upper_camel;
}} camel_upper_subst;

lookup camel_upper_pre_subst {{
    sub @upper by @upper_camel_pre;
}} camel_upper_pre_subst;

lookup camel_chain {{
    sub @lower' lookup camel_lower_subst @upper' lookup camel_upper_subst;
}} camel_chain;

lookup camel_upper_chain {{
    sub @upper' lookup camel_upper_pre_subst @upper' lookup camel_upper_subst @lower;
}} camel_upper_chain;

feature calt {{
    lookup camel_chain;
    lookup camel_upper_chain;
}} calt;

feature ccas {{
    lookup camel_chain;
    lookup camel_upper_chain;
}} ccas;
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".fea", delete=False) as f:
        f.write(fea)
        fea_path = f.name

    addOpenTypeFeatures(font, fea_path, tables=["GSUB"])


def build_one(weight: int, style: str, out_dir: Path) -> Path:
    source = find_source(weight, style)
    font = TTFont(source)
    names = create_camel_alternates(font, CAMEL_GAP)
    build_camel_gsub(font, names)
    rename_font(font, weight, style)

    output = out_dir / f"{FONT_NAME}-{weight}-{style}.otf"
    font.save(output)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DIST,
        help="Output directory (default: dist/)",
    )
    parser.add_argument(
        "--weight",
        type=int,
        action="append",
        help="Weight to build (repeatable). Default: 400 and 700.",
    )
    parser.add_argument(
        "--style",
        choices=("Regular", "Italic"),
        action="append",
        help="Style to build (repeatable). Default: Regular and Italic.",
    )
    return parser.parse_args()


def selected_styles(args: argparse.Namespace) -> list[tuple[int, str]]:
    if not args.weight and not args.style:
        return list(DEFAULT_STYLES)

    weights = args.weight or [400, 700]
    styles = args.style or ["Regular", "Italic"]
    return [(weight, style) for weight in weights for style in styles]


def main() -> int:
    args = parse_args()

    if not FONTLAB.exists():
        print(
            f"Missing Commit Mono sources under {FONTLAB}.\n"
            "Run: bash scripts/fetch_sources.sh",
            file=sys.stderr,
        )
        return 1

    args.output.mkdir(parents=True, exist_ok=True)

    built: list[Path] = []
    for weight, style in selected_styles(args):
        output = build_one(weight, style, args.output)
        built.append(output)
        print(f"Built {output.relative_to(ROOT)}")

    print(f"\nDone. {len(built)} font(s) in {args.output.relative_to(ROOT)}/")
    print("Enable camelCase spacing: \"editor.fontLigatures\": \"'ccas'\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
