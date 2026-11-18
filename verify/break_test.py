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


def wrong_text(tmp):            # the 42 step edge printed as 41
    doc, e = dim_by(tmp, "step edge X")
    e.dxf.text = "41"
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


def model_changed(tmp):         # pilot bore opened to 23 in the model; the drawing still says 22.5
    part = import_step(tmp / "part.step")
    part = part - Pos(21, 25, 5) * Cylinder(11.5, 12)
    export_step(part, tmp / "part.step")


CASES = [(wrong_text, "dimension text shows the value"),
         (moved_defpoint, "DIMENSION defpoints"),
         (json_point_off_part, "DIMENSION defpoints"),
         (frame_deleted, "GD&T frames are TOLERANCE entities"),
         (model_changed, "every diameter / radius is a cylinder")]


def main():
    res, ok_all = [], True
    for fn, expect in CASES:
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            for f in OUT.iterdir():
                if f.is_file():
                    shutil.copy2(f, tmp / f.name)
            fn(tmp)
            r = subprocess.run([sys.executable, str(ROOT / "verify" / "verify.py")], capture_output=True, text=True,
                               env={**os.environ, "MDA_OUT": str(tmp)})
        fails = [l[5:].split(" {")[0] for l in r.stdout.splitlines() if l.startswith("FAIL ")]
        caught = r.returncode != 0 and any(f.startswith(expect) for f in fails)
        ok_all &= caught
        res.append({"case": fn.__name__, "expected_fail": expect, "caught": caught, "failed_checks": fails})
        print(("CAUGHT " if caught else "MISSED ") + fn.__name__, fails)
    (ROOT / "verify" / "break_test.json").write_text(json.dumps(res, indent=1))
    print(f"\n{sum(r['caught'] for r in res)}/{len(res)} damaged copies rejected")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
