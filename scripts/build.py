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
CAMEL_GAP = 80

FONT_NAME = "CamelMono"
FAMILY_NAME = "Camel Mono"

DEFAULT_STYLES = (
    (400, "Regular"),
    (400, "Italic"),
    (700, "Regular"),
    (700, "Italic"),
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
    if weight >= 700 and style == "Italic":
        subfamily = "Bold Italic"
    elif weight >= 700:
        subfamily = "Bold"
    elif style == "Italic":
        subfamily = "Italic"
    else:
        subfamily = "Regular"

    full_name = FAMILY_NAME if subfamily == "Regular" else f"{FAMILY_NAME} {subfamily}"
    postscript_name = f"{FONT_NAME}-{subfamily.replace(' ', '')}"
    return subfamily, full_name, postscript_name


def rename_font(font: TTFont, weight: int, style: str) -> None:
    subfamily, full_name, postscript_name = style_names(weight, style)
    name_table = font["name"]

    replacements = {
        1: FAMILY_NAME,
        2: subfamily,
        4: full_name,
        6: postscript_name,
        16: FAMILY_NAME,
        17: subfamily,
    }

    for name_id, value in replacements.items():
        name_table.setName(value, name_id, 3, 1, 0x409)
        name_table.setName(value, name_id, 1, 0, 0)

    font["OS/2"].usWeightClass = weight

    selection = 0
    if "Italic" in subfamily:
        selection |= 1
    if "Bold" in subfamily:
        selection |= 1 << 5
    font["OS/2"].fsSelection = selection

    if "head" in font:
        mac_style = 0
        if "Bold" in subfamily:
            mac_style |= 1 << 0
        if "Italic" in subfamily:
            mac_style |= 1 << 1
        font["head"].macStyle = mac_style

    if "CFF " in font:
        top_dict = font["CFF "].cff.topDictIndex[0]
        top_dict.FullName = full_name
        top_dict.FamilyName = FAMILY_NAME
        if weight >= 700:
            top_dict.Weight = "Bold"
        elif style == "Italic":
            top_dict.Weight = "Italic"
        else:
            top_dict.Weight = "Regular"


def create_camel_alternates(font: TTFont, gap: int) -> tuple[list[str], list[str]]:
    """
    For each A-Z glyph, create a .camel alternate whose outline is shifted
    right by `gap` font units (same advance width — the gap is baked into the
    glyph shape, not applied at render time via GPOS).

    Returns (original_names, alternate_names) sorted in the same order.
    """
    cmap = font.getBestCmap()
    upper_names = sorted(
        (cmap[ord(c)] for c in string.ascii_uppercase if ord(c) in cmap),
        key=font.getGlyphOrder().index,
    )

    top_dict = font["CFF "].cff.topDictIndex[0]
    cs = top_dict.CharStrings
    glyph_order = font.getGlyphOrder()
    alt_names: list[str] = []

    for gname in upper_names:
        alt = f"{gname}.camel"
        adv_w = font["hmtx"].metrics[gname][0]

        # Draw original glyph through a horizontal-shift transform into a new
        # T2 charstring. RecordingPen inlines all subroutine calls first.
        rec = RecordingPen()
        cs[gname].draw(rec)

        t2 = T2CharStringPen(adv_w, cs)
        xpen = TransformPen(t2, (1, 0, 0, 1, gap, 0))
        rec.replay(xpen)

        new_cs = t2.getCharString(private=cs[gname].private)

        # Register in CFF: add name→index in the charStrings dict,
        # then append the T2CharString to the underlying index.
        idx = cs.charStringsIndex
        cs.charStrings[alt] = len(idx.items)
        idx.items.append(new_cs)

        glyph_order.append(alt)
        font["hmtx"].metrics[alt] = font["hmtx"].metrics[gname]
        alt_names.append(alt)

    return upper_names, alt_names


def build_camel_gsub(font: TTFont, upper_names: list[str], alt_names: list[str]) -> None:
    """
    Inject a GSUB contextual substitution: when [a-z] precedes [A-Z],
    substitute the uppercase with its .camel alternate.

    Because the gap is in the glyph outline (not a GPOS XPlacement),
    pixel snapping cannot cause inconsistency.

    Feature 'calt' fires automatically; 'ccas' for explicit toggling.
    """
    cmap = font.getBestCmap()
    lower_names = sorted(
        (cmap[ord(c)] for c in string.ascii_lowercase if ord(c) in cmap),
        key=font.getGlyphOrder().index,
    )

    lower_str = " ".join(lower_names)
    upper_str = " ".join(upper_names)
    alt_str = " ".join(alt_names)

    fea = f"""
@lower = [{lower_str}];
@upper = [{upper_str}];
@upper_camel = [{alt_str}];

lookup camel_subst {{
    sub @lower @upper' by @upper_camel;
}} camel_subst;

feature calt {{
    lookup camel_subst;
}} calt;

feature ccas {{
    lookup camel_subst;
}} ccas;
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".fea", delete=False) as f:
        f.write(fea)
        fea_path = f.name

    addOpenTypeFeatures(font, fea_path, tables=["GSUB"])


def build_one(weight: int, style: str, out_dir: Path) -> Path:
    source = find_source(weight, style)
    font = TTFont(source)
    upper_names, alt_names = create_camel_alternates(font, CAMEL_GAP)
    build_camel_gsub(font, upper_names, alt_names)
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
