"""NEMA 17 motor plate for 2020 aluminium extrusion. Al 6061-T6, 3-axis milled.

Frame: x along the plate (60), y across (50), z up. Datum A = underside (z = 0), B = back face (y = 50),
C = left face (x = 0). Every number below is a design value; FEATURES records them for the drawing and the checks.
python part/part.py  ->  out/part.step, out/features.json
"""
import json
from pathlib import Path

from build123d import Align, Axis, Box, Cylinder, Pos, Rot, chamfer, export_step, fillet, Location

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"

L, W, H = 60.0, 50.0, 10.0          # overall
STEP_X, H_STEP = 42.0, 6.0          # step: x > 42 is 6 thick (sits on the extrusion)
CH = 1.0                             # 4 vertical corner edges, 1 x 45 deg

# NEMA 17 (NEMA ICS 16): pilot boss 22 mm, 4 x M3 on a 31 mm square
MOTOR = (21.0, 25.0)
PILOT_D = 22.5                       # 22 mm pilot + clearance
NEMA_SPACING = 31.0
# ISO 4762 M3: dk max 5.5, k max 3.0 -> counterbore 6.5 x 3.4; ISO 273 medium clearance 3.4
M3 = dict(hole=3.4, cbore=6.5, depth=3.4)
# ISO 4762 M5: dk max 8.5, k max 5.0 -> counterbore 10 x 5.4; ISO 273 medium clearance 5.5
M5 = dict(hole=5.5, cbore=10.0, depth=5.4)
M5_POS = [(51.0, 15.0), (51.0, 35.0)]   # 20 mm apart, on the extrusion's slot line
# M4 x 0.7 - 6H, thread depth 8, tap drill 3.3 (ISO 2306) depth 10, into the front face (y = 0)
M4 = dict(tap=3.3, major=4.0, thread_depth=8.0, drill_depth=10.0, pitch=0.7)
M4_POS = [(13.0, 5.0), (29.0, 5.0)]     # (x, z) on the front face
# pocket in the step face, cutter R2 (4 mm end mill)
POCKET = dict(cx=51.0, cy=25.0, lx=12.0, ly=8.0, depth=2.0, r=2.0)


def build():
    A0 = (Align.MIN, Align.MIN, Align.MIN)
    part = Box(L, W, H, align=A0)
    part -= Pos(STEP_X, -1, H_STEP) * Box(L - STEP_X + 1, W + 2, H, align=A0)
    part = chamfer(part.edges().filter_by(Axis.Z).filter_by(
        lambda e: (abs(e.center().X) < 1e-6 or abs(e.center().X - L) < 1e-6)
        and (abs(e.center().Y) < 1e-6 or abs(e.center().Y - W) < 1e-6)), CH)
    zc = lambda d, z0, z1: Cylinder(d / 2, z1 - z0, align=(Align.CENTER, Align.CENTER, Align.MIN))
    mx, my = MOTOR
    part -= Pos(mx, my, -1) * zc(PILOT_D, -1, H + 1)
    h = NEMA_SPACING / 2
    for dx in (-h, h):
        for dy in (-h, h):
            part -= Pos(mx + dx, my + dy, -1) * zc(M3["hole"], -1, H + 1)
            part -= Pos(mx + dx, my + dy, H - M3["depth"]) * zc(M3["cbore"], 0, M3["depth"] + 1)
    for x, y in M5_POS:
        part -= Pos(x, y, -1) * zc(M5["hole"], -1, H_STEP + 1)
        part -= Pos(x, y, H_STEP - M5["depth"]) * zc(M5["cbore"], 0, M5["depth"] + 1)
    for x, z in M4_POS:   # tap drill only: the thread is a drawing convention, not modelled
        part -= Pos(x, -1, z) * Rot(-90, 0, 0) * Cylinder(M4["tap"] / 2, M4["drill_depth"] + 1, align=(Align.CENTER, Align.CENTER, Align.MIN))
    pk = Box(POCKET["lx"], POCKET["ly"], POCKET["depth"] + 1, align=(Align.CENTER, Align.CENTER, Align.MIN))
    pk = fillet(pk.edges().filter_by(Axis.Z), POCKET["r"])
    part -= Pos(POCKET["cx"], POCKET["cy"], H_STEP - POCKET["depth"]) * pk
    return part


def features():
    mx, my = MOTOR
    h = NEMA_SPACING / 2
    return {
        "overall": {"L": L, "W": W, "H": H}, "step": {"x": STEP_X, "h": H_STEP}, "chamfer": CH,
        "pilot": {"x": mx, "y": my, "d": PILOT_D},
        "m3": [{"x": mx + dx, "y": my + dy, **M3} for dx in (-h, h) for dy in (-h, h)],
        "m5": [{"x": x, "y": y, **M5} for x, y in M5_POS],
        "m4": [{"x": x, "z": z, **M4} for x, z in M4_POS],
        "pocket": POCKET,
        "datums": {"A": "z = 0 underside", "B": "y = 50 back face", "C": "x = 0 left face", "D": "axis of M5 hole at (51, 15)"},
        "material": "Al 6061-T6",
        "sources": {
            "ISO 4762": "M3 dk max 5.5, k max 3.0; M5 dk max 8.5, k max 5.0 (counterbore = dk + 1, depth = k + 0.4)",
            "ISO 273": "clearance holes, medium series: M3 3.4, M5 5.5",
            "ISO 2306 / ISO 965": "M4x0.7-6H tap drill 3.3",
            "NEMA ICS 16": "NEMA 17 frame: 31 mm hole spacing, 22 mm pilot",
        },
    }


def main():
    OUT.mkdir(exist_ok=True)
    p = build()
    assert len(p.solids()) == 1 and p.is_valid
    p.label = "nema17_2020_plate"
    export_step(p, OUT / "part.step")
    (OUT / "features.json").write_text(json.dumps(features(), indent=1))
    b = p.bounding_box()
    print("volume", round(p.volume, 2), "bbox", b.size, "faces", len(p.faces()))


if __name__ == "__main__":
    main()
