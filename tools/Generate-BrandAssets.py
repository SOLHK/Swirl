"""Derive product SVG variants from the editable Swirl symbol (standard library)."""
from pathlib import Path
import argparse
import copy
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src/Swirl.Quick/assets"
NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)
DARK = {
    "#F5A04D": "#FFB567", "#F47C51": "#FF9569",
    "#EC5260": "#FF7685", "#D93962": "#F55F86",
    "#20B7D0": "#54D0E4", "#188FD2": "#51B1EF",
    "#285DD3": "#729BF5", "#168DCB": "#4DADE4",
    "#099DC2": "#37BBD8", "#20AE9B": "#55CCB2",
    "#098CAF": "#44B5D1", "#12A39C": "#41C3B9",
    "#3CAA79": "#6ACA96", "#1BAA9E": "#51C9B9",
    "#287CCB": "#66A8E7",
}


def variants():
    master = ET.parse(ASSETS / "brand/swirl-symbol.svg").getroot()
    for dark in (False, True):
        for tile in (False, True):
            svg = copy.deepcopy(master)
            if dark:
                for stop in svg.findall(f".//{{{NS}}}stop"):
                    stop.set("stop-color", DARK[stop.get("stop-color")])
            if tile:
                rect = ET.Element(f"{{{NS}}}rect", {
                    "width": "1024", "height": "1024", "rx": "216",
                    "fill": "#14283F" if dark else "#FBFCFD",
                })
                svg.insert(list(svg).index(svg.find(f"{{{NS}}}g")), rect)
            mode = "dark" if dark else "light"
            name = f"swirl_knot_{'' if tile else 'mark_'}{mode}.svg"
            ET.indent(svg, space="  ")
            yield ASSETS / "icons" / name, ET.tostring(
                svg, encoding="utf-8", xml_declaration=True
            ) + b"\n"
        svg = copy.deepcopy(master)
        svg.remove(svg.find(f"{{{NS}}}defs"))
        for path in svg.findall(f".//{{{NS}}}path"):
            path.set("fill", "#FFFFFF" if dark else "#14283F")
        ET.indent(svg, space="  ")
        mode = "dark" if dark else "light"
        yield ASSETS / "icons" / f"swirl_knot_mark_mono_{mode}.svg", ET.tostring(
            svg, encoding="utf-8", xml_declaration=True
        ) + b"\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = []
    for path, data in variants():
        if args.check:
            if not path.exists() or path.read_bytes() != data:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.write_bytes(data)
    if stale:
        parser.exit(1, "Out-of-date brand assets:\n" + "\n".join(stale) + "\n")
    print("Brand SVG variants match the editable master." if args.check else "Generated six brand SVG variants.")


if __name__ == "__main__":
    main()
