#!/usr/bin/env python3
"""Build CamelMono from Commit Mono OTF sources + camelcase OpenType feature."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from fontTools.feaLib.builder import addOpenTypeFeatures
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor" / "commit-mono"
FONTLAB = VENDOR / "src" / "fonts" / "fontlab"
FEATURES = ROOT / "features" / "camelcase.fea"
DIST = ROOT / "dist"

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


def build_one(weight: int, style: str, out_dir: Path) -> Path:
    source = find_source(weight, style)
    font = TTFont(source)
    addOpenTypeFeatures(font, str(FEATURES), tables=["GPOS"])
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

    if not FEATURES.exists():
        print(f"Missing feature file: {FEATURES}", file=sys.stderr)
        return 1
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
