"""Break test: damage a copy of out/ in one way per case and show that verify.py catches it.
python verify/break_test.py -> verify/break_test.json (exit 1 if any case passes verify)"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import ezdxf
from build123d import Cylinder, Pos, export_step, import_step

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"


def dim_by(tmp, feature):
    h = next(d["handle"] for d in json.loads((tmp / "dims.json").read_text()) if d["feature"].startswith(feature))
    doc = ezdxf.readfile(tmp / "part.dxf")
    return doc, doc.entitydb[h]


def wrong_text(tmp):            # the 65 overall length printed as 64
    doc, e = dim_by(tmp, "overall length X")
    e.dxf.text = "64"
    doc.saveas(tmp / "part.dxf")


def moved_defpoint(tmp):        # a dimension that no longer measures the edge it names
    doc, e = dim_by(tmp, "M5 holes spacing Y")
    p = e.dxf.defpoint3
    e.dxf.defpoint3 = (p.x, p.y + 1.0, p.z)
    doc.saveas(tmp / "part.dxf")


def json_point_off_part(tmp):   # dims.json says the M4 holes sit at z 5.5, the model has 5
    d = json.loads((tmp / "dims.json").read_text())
    for x in d:
        if x["feature"].startswith("M4 holes pos Z"):
            x["p2"][2] += 0.5
    (tmp / "dims.json").write_text(json.dumps(d))


def frame_deleted(tmp):         # one GD&T frame gone from the DXF
    doc = ezdxf.readfile(tmp / "part.dxf")
    msp = doc.modelspace()
    msp.delete_entity([e for e in msp if e.dxftype() == "TOLERANCE"][0])
    doc.saveas(tmp / "part.dxf")


def model_changed(tmp):         # pilot bore opened to 23 in the model; the drawing still says 22
    part = import_step(tmp / "part.step")
    part = part - Pos(22, 25, 5) * Cylinder(11.5, 12)
    export_step(part, tmp / "part.step")


def text_on_line(tmp):          # a note moved onto the section view
    doc = ezdxf.readfile(tmp / "part.dxf")
    t = next(e for e in doc.modelspace() if e.dxftype() == "TEXT" and e.dxf.text.startswith("7. "))
    t.set_placement((250.0, 178.0))
    doc.saveas(tmp / "part.dxf")


def motor_hits_extrusion(tmp):  # pilot moved 3 mm towards the extrusion: the motor body now overlaps it
    f = json.loads((tmp / "features.json").read_text())
    f["motor"]["x"] += 3
    (tmp / "features.json").write_text(json.dumps(f))


def thin_floor(tmp):            # M5 counterbore 9.4 deep: 0.6 mm left under the head (the REV1 mistake)
    f = json.loads((tmp / "features.json").read_text())
    for m in f["m5"]:
        m["depth"] = 9.4
    (tmp / "features.json").write_text(json.dumps(f))


def frame_on_leader(tmp):       # the M5 position frame drawn across its own callout leader
    g = next(f for f in json.loads((tmp / "gdt.json").read_text())["frames"] if f["note"] == "position of 2x M5 holes")
    x0, y0, x1, y1 = g["bbox"]
    doc = ezdxf.readfile(tmp / "part.dxf")
    for e in doc.modelspace():
        if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == "GDT_PDF":
            pts = [(p[0], p[1]) for p in e.get_points()]
            if all(x0 - 0.01 <= x <= x1 + 0.01 and y0 - 0.01 <= y <= y1 + 0.01 for x, y in pts):
                e.set_points([(x - 30, y + 12) for x, y in pts])
    doc.saveas(tmp / "part.dxf")


CASES = [(wrong_text, "dimension text shows the value"),
         (moved_defpoint, "DIMENSION defpoints"),
         (json_point_off_part, "DIMENSION defpoints"),
         (frame_deleted, "GD&T frames are TOLERANCE entities"),
         (model_changed, "every diameter / radius is a cylinder"),
         (text_on_line, "no text touches"),
         (frame_on_leader, "no leader crosses"),
         (motor_hits_extrusion, "fit: no interference"),
         (thin_floor, "fit: material under every screw head")]


def main():
    res, ok_all = [], True
    for fn, expect in CASES:
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            for f in OUT.iterdir():
                if f.is_file():
                    shutil.copy2(f, tmp / f.name)
            fn(tmp)
            fails, rc = [], 0
            for script, prefix in (("verify.py", ""), ("fit.py", "fit: ")):
                r = subprocess.run([sys.executable, str(ROOT / "verify" / script)], capture_output=True, text=True,
                                   env={**os.environ, "MDA_OUT": str(tmp)})
                rc |= r.returncode
                fails += [prefix + l[5:].split(" {")[0] for l in r.stdout.splitlines() if l.startswith("FAIL ")]
        caught = rc != 0 and any(f.startswith(expect) for f in fails)
        ok_all &= caught
        res.append({"case": fn.__name__, "expected_fail": expect, "caught": caught, "failed_checks": fails})
        print(("CAUGHT " if caught else "MISSED ") + fn.__name__, fails)
    (ROOT / "verify" / "break_test.json").write_text(json.dumps(res, indent=1))
    print(f"\n{sum(r['caught'] for r in res)}/{len(res)} damaged copies rejected")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
