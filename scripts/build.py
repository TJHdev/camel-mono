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
    Create alternates for both sides of each camelCase boundary.

    Digits (0–9) are treated as uppercase-equivalent so that transitions like
    lowercase→digit and digit→uppercase produce the same gap as letter boundaries.

      - .camelPre  for a-z:   outline shifted LEFT  by gap*0.80
      - .camel     for A-Z/0-9: outline shifted RIGHT by gap*0.20  (start of a word)
      - .camelPreU for A-Z/0-9: outline shifted LEFT  by gap*0.80  (end of an acronym/number run)

    Splitting the gap symmetrically means neither glyph drifts into its neighbour.

    Returns a dict with keys 'lower_orig', 'lower_alt', 'upper_orig', 'upper_alt',
    'upper_pre_alt', 'digit_orig', 'digit_alt', 'digit_pre_alt'.
    """
    cmap = font.getBestCmap()
    glyph_order = font.getGlyphOrder()
    lower_names = sorted(
        (cmap[ord(c)] for c in string.ascii_lowercase if ord(c) in cmap),
        key=glyph_order.index,
    )
    upper_names = sorted(
        (cmap[ord(c)] for c in string.ascii_uppercase if ord(c) in cmap),
        key=glyph_order.index,
    )
    digit_names = sorted(
        (cmap[ord(c)] for c in string.digits if ord(c) in cmap),
        key=glyph_order.index,
    )

    left_shift  = round(gap * 0.80)
    right_shift = gap - left_shift
    # Midpoint shift for glyphs at both sides of two adjacent boundaries (e.g. the 9 in
    # q9Do, or the A in fromAPension). Splits the gap equally: 60 units on each side.
    both_shift  = round((right_shift - left_shift) / 2)

    lower_alts      = make_shifted_alternates(font, lower_names, shift=-left_shift,  suffix=".camelPre")
    upper_alts      = make_shifted_alternates(font, upper_names, shift=right_shift,   suffix=".camel")
    upper_pre_alts  = make_shifted_alternates(font, upper_names, shift=-left_shift,   suffix=".camelPreU")
    upper_both_alts = make_shifted_alternates(font, upper_names, shift=both_shift,    suffix=".camelBoth")
    digit_alts      = make_shifted_alternates(font, digit_names, shift=right_shift,   suffix=".camel")
    digit_pre_alts  = make_shifted_alternates(font, digit_names, shift=-left_shift,   suffix=".camelPreU")
    digit_both_alts = make_shifted_alternates(font, digit_names, shift=both_shift,    suffix=".camelBoth")

    return {
        "lower_orig":     lower_names,
        "lower_alt":      lower_alts,
        "upper_orig":     upper_names,
        "upper_alt":      upper_alts,
        "upper_pre_alt":  upper_pre_alts,
        "upper_both_alt": upper_both_alts,
        "digit_orig":     digit_names,
        "digit_alt":      digit_alts,
        "digit_pre_alt":  digit_pre_alts,
        "digit_both_alt": digit_both_alts,
    }


def build_camel_gsub(font: TTFont, names: dict) -> None:
    """
    Inject substitution lookups and chaining contextual rules for three boundary patterns.
    Digits (0–9) are treated as uppercase-equivalent throughout.

    Lookups are defined in application order (OpenType applies by LookupList index):

    1. camel_lower_upper_upper_chain  [a-z][A-Z0-9][A-Z0-9] lookahead:[a-z]
       e.g. q9Do, fromAPension  — the middle glyph is at BOTH boundaries so gets
       .camelBoth (midpoint shift, ≈60-unit gap on each side).
       • lowercase  → .camelPre  (left shift)
       • first upper/digit → .camelBoth (midpoint shift)
       • second upper/digit → .camel    (right shift)

    2. camel_upper_chain  [A-Z0-9][A-Z0-9] lookahead:[a-z]
       e.g. HTTPSConnection, q19Do  — standard acronym/number-run boundary.
       • first upper/digit → .camelPreU (left shift)
       • second upper/digit → .camel   (right shift)

    3. camel_chain  [a-z][A-Z0-9]
       e.g. getUserName, get2DPoint  — standard camelCase boundary.
       • lowercase  → .camelPre (left shift)
       • upper/digit → .camel   (right shift)

    Feature 'calt' fires automatically; 'ccas' for explicit toggling.
    """
    lower_str     = " ".join(names["lower_orig"])
    lower_alt_str = " ".join(names["lower_alt"])

    # Uppercase letters and digits combined into a single "upper-equivalent" class.
    upper_ext_str      = " ".join(names["upper_orig"]     + names["digit_orig"])
    upper_ext_alt_str  = " ".join(names["upper_alt"]      + names["digit_alt"])
    upper_ext_pre_str  = " ".join(names["upper_pre_alt"]  + names["digit_pre_alt"])
    upper_ext_both_str = " ".join(names["upper_both_alt"] + names["digit_both_alt"])

    fea = f"""
@lower            = [{lower_str}];
@lower_camel      = [{lower_alt_str}];
@upper_ext        = [{upper_ext_str}];
@upper_ext_camel  = [{upper_ext_alt_str}];
@upper_ext_pre    = [{upper_ext_pre_str}];
@upper_ext_both   = [{upper_ext_both_str}];

lookup camel_lower_subst {{
    sub @lower by @lower_camel;
}} camel_lower_subst;

lookup camel_upper_subst {{
    sub @upper_ext by @upper_ext_camel;
}} camel_upper_subst;

lookup camel_upper_pre_subst {{
    sub @upper_ext by @upper_ext_pre;
}} camel_upper_pre_subst;

lookup camel_upper_both_subst {{
    sub @upper_ext by @upper_ext_both;
}} camel_upper_both_subst;

lookup camel_lower_upper_upper_chain {{
    sub @lower' lookup camel_lower_subst @upper_ext' lookup camel_upper_both_subst @upper_ext' lookup camel_upper_subst @lower;
}} camel_lower_upper_upper_chain;

lookup camel_upper_chain {{
    sub @upper_ext' lookup camel_upper_pre_subst @upper_ext' lookup camel_upper_subst @lower;
}} camel_upper_chain;

lookup camel_chain {{
    sub @lower' lookup camel_lower_subst @upper_ext' lookup camel_upper_subst;
}} camel_chain;

feature calt {{
    lookup camel_lower_upper_upper_chain;
    lookup camel_upper_chain;
    lookup camel_chain;
}} calt;

feature ccas {{
    lookup camel_lower_upper_upper_chain;
    lookup camel_upper_chain;
    lookup camel_chain;
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
