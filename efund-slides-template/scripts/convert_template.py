# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pymupdf==1.26.5",
#     "fonttools[woff]==4.60.1",
# ]
# ///
"""Rebuild the web template's fixed artwork from the supplied PowerPoint.

LibreOffice renders inherited brand furniture, then PDF glyphs become SVG paths.
New slide content remains HTML; these SVGs contain only fixed brand artwork.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import posixpath
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

import pymupdf
from fontTools.ttLib import TTFont

NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)

TEMPLATES = {
    "cover-cn": 2,
    "cover-en": 4,
    "toc": 14,
    "content": 10,
    "ending-cn": 45,
    "ending-en": 46,
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def xml_bytes(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def strip_layout_placeholders(root: ET.Element) -> None:
    """Keep only real, fixed furniture; page numbers are supplied by HTML."""
    for tree in root.findall(".//p:spTree", NS):
        for shape in list(tree):
            is_placeholder = shape.find(".//p:ph", NS) is not None
            is_page_number = any(
                f.get("type", "").lower() == "slidenum"
                for f in shape.findall(".//a:fld", NS)
            )
            text = "".join(t.text or "" for t in shape.findall(".//a:t", NS))
            if is_placeholder or is_page_number or "‹#›" in text:
                tree.remove(shape)


def prepare_blank_deck(source: Path, target: Path) -> dict:
    with zipfile.ZipFile(source) as archive:
        presentation = ET.fromstring(archive.read("ppt/presentation.xml"))
        relations = ET.fromstring(archive.read("ppt/_rels/presentation.xml.rels"))
        targets = {
            rel.get("Id"): posixpath.normpath("ppt/" + rel.get("Target", ""))
            for rel in relations
        }
        slide_list = presentation.find("p:sldIdLst", NS)
        if slide_list is None or len(slide_list) < max(TEMPLATES.values()):
            raise ValueError("The source does not contain the expected 47-page V5 template.")
        slide_ids = list(slide_list)
        chosen = [slide_ids[number - 1] for number in TEMPLATES.values()]
        slide_parts = [targets[item.get(f"{{{NS['r']}}}id")] for item in chosen]
        slide_list.clear()
        slide_list.extend(chosen)
        size = presentation.find("p:sldSz", NS)
        if size is None:
            raise ValueError("Missing PowerPoint slide dimensions.")
        width, height = int(size.get("cx", "0")), int(size.get("cy", "0"))
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as output:
            for entry in archive.infolist():
                data = archive.read(entry.filename)
                if entry.filename == "ppt/presentation.xml":
                    data = xml_bytes(presentation)
                elif entry.filename in slide_parts:
                    root = ET.fromstring(data)
                    tree = root.find("p:cSld/p:spTree", NS)
                    if tree is None:
                        raise ValueError(f"Missing shape tree in {entry.filename}")
                    for shape in list(tree):
                        if shape.tag.rsplit("}", 1)[-1] not in ("nvGrpSpPr", "grpSpPr"):
                            tree.remove(shape)
                    for tag in ("timing", "transition"):
                        child = root.find(f"p:{tag}", NS)
                        if child is not None:
                            root.remove(child)
                    data = xml_bytes(root)
                elif entry.filename.startswith(("ppt/slideLayouts/slideLayout", "ppt/slideMasters/slideMaster")) and entry.filename.endswith(".xml"):
                    root = ET.fromstring(data)
                    strip_layout_placeholders(root)
                    data = xml_bytes(root)
                output.writestr(entry, data)
    return {
        "emu": {"width": width, "height": height},
        "px": {"width": width / 9525, "height": height / 9525},
    }


def font_environment(font: Path, work: Path) -> dict[str, str]:
    font_dir = work / "fonts"
    font_dir.mkdir()
    shutil.copy2(font, font_dir / font.name)
    candidates = [
        font_dir,
        Path("/System/Library/Fonts"),
        Path("/Library/Fonts"),
        Path("/Applications/Microsoft PowerPoint.app/Contents/Resources/DFonts"),
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
    ]
    root = ET.Element("fontconfig")
    for directory in candidates:
        if directory.exists():
            ET.SubElement(root, "dir").text = str(directory)
    cache = work / "font-cache"
    cache.mkdir()
    ET.SubElement(root, "cachedir").text = str(cache)
    config = work / "fonts.conf"
    config.write_bytes(xml_bytes(root))
    env = os.environ.copy()
    env["FONTCONFIG_FILE"] = str(config)
    return env


def render_pdf(source: Path, work: Path, env: dict[str, str], soffice: str) -> Path:
    destination = work / (source.stem + "-pdf")
    destination.mkdir()
    profile = work / (source.stem + "-lo-profile")
    result = subprocess.run(
        [soffice, f"-env:UserInstallation={profile.as_uri()}", "--headless",
         "--convert-to", "pdf", "--outdir", str(destination), str(source)],
        env=env, capture_output=True, text=True, timeout=180,
    )
    pdf = destination / (source.stem + ".pdf")
    if result.returncode or not pdf.is_file():
        raise RuntimeError(f"LibreOffice failed ({result.returncode}): {result.stdout}\n{result.stderr}")
    return pdf


def svg_artwork(page: pymupdf.Page, width: float, height: float) -> str:
    svg = page.get_svg_image(text_as_path=True)
    root = ET.fromstring(svg)
    root.set("width", f"{width:.8f}")
    root.set("height", f"{height:.8f}")
    # get_svg_image embeds PDF images. Assert that this remains true after upgrades.
    for element in root.iter():
        for key, value in element.attrib.items():
            if key.rsplit("}", 1)[-1] == "href" and not value.startswith(("#", "data:")):
                raise ValueError(f"SVG contains an external asset reference: {value}")
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    return ET.tostring(root, encoding="unicode")


def convert_font(font: Path, output: Path) -> dict:
    """Normalize the known legacy vhea typo in the web copy, never the input."""
    font_dir = output / "fonts"
    font_dir.mkdir(parents=True, exist_ok=True)
    web_font = font_dir / "efund.woff2"
    if font.resolve() == web_font.resolve():
        raise ValueError("The source font must differ from the generated fonts/efund.woff2.")
    source_hash = digest(font)
    normalizations = []
    with TTFont(font, recalcTimestamp=False) as ttfont:
        font_names = sorted({n.toUnicode() for n in ttfont["name"].names if n.nameID in (1, 4, 6) and n.toUnicode()})
        if not any(
            family in name for name in font_names
            for family in ("STHeiti_YFD", "华文黑体_易方达")
        ):
            raise ValueError("Expected the E Fund font (STHeiti_YFD / 华文黑体_易方达); the supplied font has a different internal family name.")
        source_cmap = ttfont.getBestCmap()
        source_metrics = ttfont["hmtx"].metrics.copy()
        if "vhea" in ttfont:
            version = ttfont["vhea"].tableVersion
            if version == 0x00010001:
                # The provided font uses +500 ascent/+500 descent, i.e. v1.0
                # semantics, but stores the invalid version 0x00010001.
                # Spec: https://learn.microsoft.com/en-us/typography/opentype/spec/vhea
                ttfont["vhea"].tableVersion = 0x00010000
                normalizations.append({"table": "vhea", "field": "tableVersion",
                                       "from": "0x00010001", "to": "0x00010000"})
            elif version not in (0x00010000, 0x00011000):
                raise ValueError(f"Unsupported vhea version {version:#010x}; provide a valid font.")
        ttfont.flavor = "woff2"
        ttfont.save(web_font)
    with TTFont(web_font) as converted:
        if converted.getBestCmap() != source_cmap or converted["hmtx"].metrics != source_metrics:
            raise ValueError("WOFF2 conversion changed character mapping or horizontal metrics.")
    if digest(font) != source_hash:
        raise ValueError("The source font unexpectedly changed during conversion.")
    metadata = {"file": "fonts/efund.woff2", "names": font_names,
                "sourceSha256": source_hash, "sha256": digest(web_font),
                "characterCount": len(source_cmap), "normalizations": normalizations}
    (font_dir / "font-manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metadata


def main() -> None:
    skill_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=skill_dir / "material/易方达ppt模板V5.pptx")
    parser.add_argument("--font", type=Path, required=True, help="User-provided STHeiti_YFD.ttf font source")
    parser.add_argument("--font-only", action="store_true", help="Prepare only the browser-compatible WOFF2; no PPTX or LibreOffice required")
    parser.add_argument("--out", type=Path, default=skill_dir / "assets")
    parser.add_argument("--soffice", default="soffice")
    parser.add_argument("--reference-pdf", type=Path, help="Optional full-source reference PDF, for visual comparisons")
    args = parser.parse_args()
    source, font, output = args.source.resolve(), args.font.resolve(), args.out.resolve()
    if not font.is_file():
        parser.error("--font must exist.")
    if args.font_only:
        font_metadata = convert_font(font, output)
        manifest_path = output / "template-manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["font"] = font_metadata
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"font": str(output / font_metadata["file"]), **font_metadata}, ensure_ascii=False))
        return
    if not source.is_file():
        parser.error("--source must exist unless --font-only is used.")
    if shutil.which(args.soffice) is None:
        parser.error("LibreOffice/soffice is required to rebuild artwork; ordinary slide generation does not need it.")
    output.mkdir(parents=True, exist_ok=True)
    (output / "backgrounds").mkdir(exist_ok=True)
    (output / "fonts").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="efund-template-") as directory:
        work = Path(directory).resolve()
        blank = work / "brand-backgrounds.pptx"
        canvas = prepare_blank_deck(source, blank)
        env = font_environment(font, work)
        pdf = render_pdf(blank, work, env, args.soffice)
        templates = {}
        with pymupdf.open(pdf) as document:
            if document.page_count != len(TEMPLATES):
                raise ValueError(f"Expected {len(TEMPLATES)} pages, got {document.page_count}.")
            for index, (name, source_page) in enumerate(TEMPLATES.items()):
                page = document[index]
                fixed_text = page.get_text().strip()
                rendered_fonts = sorted({
                    span["font"]
                    for block in page.get_text("dict")["blocks"] if "lines" in block
                    for line in block["lines"] for span in line["spans"]
                })
                if name == "cover-cn" and (
                    "本报告仅供本公司" not in fixed_text
                    or not any("STHeiti" in name for name in rendered_fonts)
                ):
                    raise ValueError("Chinese brand text did not render with the supplied STHeiti font.")
                artwork = output / "backgrounds" / f"{name}.svg"
                artwork.write_text(svg_artwork(page, **canvas["px"]), encoding="utf-8")
                templates[name] = {
                    "sourcePage": source_page,
                    "background": f"backgrounds/{name}.svg",
                    "sha256": digest(artwork),
                    "fixedText": fixed_text,
                    "renderedFonts": rendered_fonts,
                }
        if args.reference_pdf:
            reference = render_pdf(source, work, env, args.soffice)
            args.reference_pdf.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(reference, args.reference_pdf)
    font_metadata = convert_font(font, output)
    web_font = output / font_metadata["file"]
    manifest = {
        "formatVersion": 1,
        "source": {"file": source.name, "sha256": digest(source)},
        "canvas": canvas,
        "font": font_metadata,
        "colors": {"navy": "#005096", "blue": "#0078B4", "cyan": "#1EB9E1",
                   "lightBlue": "#B3EBFF", "text": "#3C3C3C", "gray": "#969696",
                   "line": "#CCCCCC", "yellow": "#FFC819"},
        "templates": templates,
        "conversion": {
            "renderer": subprocess.check_output([args.soffice, "--version"], text=True).strip(),
            "pymupdf": pymupdf.VersionBind,
            "method": "Retain slide-layout brand furniture; remove slide content, placeholders and page-number fields; render PDF to embedded SVG paths.",
            "rebuild": "uv run scripts/convert_template.py --font /path/to/STHeiti_YFD.ttf",
            "notes": "SVGs contain fixed brand artwork only. The full character-set WOFF2 supplies editable HTML text. PDF rendering can differ from Microsoft PowerPoint rasterization.",
            "fontInput": "The font is supplied separately by the user when rebuilding; this manifest records its digest, not a redistribution license.",
        },
    }
    manifest_path = output / "template-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"templates": len(templates), "canvas": canvas["px"], "fontBytes": web_font.stat().st_size,
                      "manifest": str(manifest_path)}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        raise SystemExit(str(error)) from None
