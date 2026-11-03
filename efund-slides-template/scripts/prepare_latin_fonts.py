# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "fonttools[woff]==4.60.1",
# ]
# ///
"""Prepare complete, fixed Arial faces for portable E Fund HTML slides.

Font sources are read-only. WOFF2 conversion retains every glyph and all names,
and validates character mappings, outlines and horizontal metrics before output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def names(font: TTFont) -> list[str]:
    return sorted({record.toUnicode() for record in font["name"].names
                   if record.nameID in (1, 2, 4, 6, 16, 17) and record.toUnicode()})


def name_records(font: TTFont) -> list[tuple]:
    return sorted((record.nameID, record.platformID, record.platEncID,
                   record.langID, record.toUnicode()) for record in font["name"].names)


def convert_face(source: Path, destination: Path, expected_weight: int) -> dict:
    if source.resolve() == destination.resolve():
        raise ValueError("Source font must differ from the generated WOFF2.")
    source_hash = digest(source)
    with TTFont(source, recalcTimestamp=False) as original:
        family_names = {record.toUnicode() for record in original["name"].names
                        if record.nameID in (1, 16)}
        if "Arial" not in family_names:
            raise ValueError(f"{source.name}: expected the Arial font family.")
        weight = original["OS/2"].usWeightClass
        if weight != expected_weight:
            raise ValueError(f"{source.name}: expected weight {expected_weight}, found {weight}.")
        original.flavor = "woff2"
        original.save(destination)
        with TTFont(source, recalcTimestamp=False) as baseline, TTFont(destination) as converted:
            if (baseline.getBestCmap() != converted.getBestCmap()
                    or baseline.getGlyphOrder() != converted.getGlyphOrder()
                    or baseline["hmtx"].metrics != converted["hmtx"].metrics
                    or name_records(baseline) != name_records(converted)
                    or converted["OS/2"].usWeightClass != weight):
                raise ValueError(f"{source.name}: conversion changed mappings, metrics or names.")
            original_glyphs, converted_glyphs = baseline.getGlyphSet(), converted.getGlyphSet()
            for glyph_name in baseline.getGlyphOrder():
                before, after = RecordingPen(), RecordingPen()
                original_glyphs[glyph_name].draw(before)
                converted_glyphs[glyph_name].draw(after)
                if before.value != after.value:
                    raise ValueError(f"{source.name}: conversion changed glyph {glyph_name}.")
        metadata = {
            "file": destination.name,
            "sourceFile": source.name,
            "sourceSha256": source_hash,
            "sha256": digest(destination),
            "names": names(original),
            "weight": weight,
            "glyphCount": len(original.getGlyphOrder()),
            "characterCount": len(original.getBestCmap()),
        }
    if digest(source) != source_hash:
        raise ValueError(f"{source.name}: source font unexpectedly changed.")
    return metadata


def main() -> None:
    skill_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regular", type=Path, required=True, help="Arial regular source font")
    parser.add_argument("--bold", type=Path, required=True, help="Arial bold source font")
    parser.add_argument("--out", type=Path, default=skill_dir / "assets/fonts")
    args = parser.parse_args()
    sources = [("regular", args.regular.resolve(), 400), ("bold", args.bold.resolve(), 700)]
    for _, source, _ in sources:
        if not source.is_file():
            parser.error(f"Font source does not exist: {source.name}")
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"formatVersion": 1, "fonts": {}}
    with tempfile.TemporaryDirectory(prefix=".arial-", dir=output) as directory:
        work = Path(directory)
        for face, source, weight in sources:
            filename = f"arial-{face}.woff2"
            manifest["fonts"][face] = convert_face(source, work / filename, weight)
        manifest_file = work / "latin-font-manifest.json"
        manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for item in work.iterdir():
            item.replace(output / item.name)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from None
