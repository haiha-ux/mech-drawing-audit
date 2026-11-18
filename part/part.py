"""NEMA 17 motor plate for 2020 aluminium extrusion. Al 6061-T6, 3-axis milled.

Frame: x along the plate (65), y across (50), z up. Datum A = underside (z = 0), B = back face (y = 50),
C = left face (x = 0). The motor face and the top of the extrusion both bear on the underside (A): the motor hangs
below the left part of the plate with its shaft up through the pilot bore, and the extrusion runs along y under the
right part. The screws go in from the top, into the counterbores.
python part/part.py  ->  out/part.step, out/features.json
"""
import json
from pathlib import Path

from build123d import Align, Axis, Box, Cylinder, Pos, Rot, chamfer, export_step

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"

L, W, H = 65.0, 50.0, 10.0          # overall
CH = 1.0                             # 4 vertical corner edges, 1 x 45 deg

# NEMA 17: 31 mm M3 square (NEMA ICS 16). Square flange 42.7 (1.7 in), length 34.0, pilot boss Ø22.0 +0/-0.051 x 2.0, M3x0.5 thread 0.15 in (3.81 mm)
# minimum deep: Novanta IMS size 17 linear actuator data sheet, REV032022 (same NEMA 17 frame as their rotary motors).
# Other makers give up to 4.5 mm thread; the 3.81 minimum is the one designed to.
MOTOR = (22.0, 25.0)                 # body spans x 0.65..43.35, inside the plate
PILOT_D = 22.0                       # H8: locates on the boss, so the position tolerance on the bore means something
PILOT_FIT = "H8"
NEMA_SPACING = 31.0
MOTOR_BODY = 42.7
MOTOR_THREAD = 0.15 * 25.4
# Counterbores: DIN 974-1 diameters for ISO 4762 heads (M3 6.5, M5 10); depths chosen here, see SCREWS
M3 = dict(hole=3.4, cbore=6.5, depth=3.0)        # floor 7.0: an M3x10 engages 3.0, worst case 3.49 < 3.81 (verify/fit.py)
M5 = dict(hole=5.5, cbore=10.0, depth=5.2)       # floor 4.8 under the M5 head
# tolerances that set the screw stack: plate thickness and counterbore depths are toleranced on the drawing
TOL = {"H": 0.1, "cbore_depth": [0.0, 0.1], "screw_length": 0.29}   # ISO 4759-1 grade A: length js15, +-0.29 for l = 10
M5_POS = [(55.0, 15.0), (55.0, 35.0)]            # 20 apart on the extrusion's slot line; extrusion spans x 45..65
EXTRUSION = 20.0
# M4 x 0.7 - 6H, thread depth 8, tap drill 3.3 (ISO 2306) depth 10, into the front face (y = 0): accessory mounting
M4 = dict(tap=3.3, major=4.0, thread_depth=8.0, drill_depth=10.0, pitch=0.7)
M4_POS = [(13.0, 5.0), (29.0, 5.0)]     # (x, z) on the front face
# ISO 4762 heads: M3 dk 5.5 k 3.0, M5 dk 8.5 k 5.0
SCREWS = {"M3": dict(d=3.0, dk=5.5, k=3.0, length=10.0, tighten_nm=0.6),     # 0.6 Nm: the motor thread is short
          "M5": dict(d=5.0, dk=8.5, k=5.0, length=10.0, tighten_nm=4.0)}


def build():
    A0 = (Align.MIN, Align.MIN, Align.MIN)
    part = Box(L, W, H, align=A0)
    part = chamfer(part.edges().filter_by(Axis.Z), CH)
    zc = lambda d, h: Cylinder(d / 2, h, align=(Align.CENTER, Align.CENTER, Align.MIN))
    mx, my = MOTOR
    part -= Pos(mx, my, -1) * zc(PILOT_D, H + 2)
    h = NEMA_SPACING / 2
    for dx in (-h, h):
        for dy in (-h, h):
            part -= Pos(mx + dx, my + dy, -1) * zc(M3["hole"], H + 2)
            part -= Pos(mx + dx, my + dy, H - M3["depth"]) * zc(M3["cbore"], M3["depth"] + 1)
    for x, y in M5_POS:
        part -= Pos(x, y, -1) * zc(M5["hole"], H + 2)
        part -= Pos(x, y, H - M5["depth"]) * zc(M5["cbore"], M5["depth"] + 1)
    for x, z in M4_POS:   # tap drill only: the thread is a drawing convention, not modelled
        part -= Pos(x, -1, z) * Rot(-90, 0, 0) * Cylinder(M4["tap"] / 2, M4["drill_depth"] + 1, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return part


def features():
    mx, my = MOTOR
    h = NEMA_SPACING / 2
    return {
        "overall": {"L": L, "W": W, "H": H}, "chamfer": CH,
        "pilot": {"x": mx, "y": my, "d": PILOT_D, "fit": PILOT_FIT},
        "m3": [{"x": mx + dx, "y": my + dy, **M3} for dx in (-h, h) for dy in (-h, h)],
        "m5": [{"x": x, "y": y, **M5} for x, y in M5_POS],
        "m4": [{"x": x, "z": z, **M4} for x, z in M4_POS],
        "motor": {"x": mx, "y": my, "body": MOTOR_BODY, "boss_d": 22.0, "boss_tol": [-0.051, 0.0], "boss_h": 2.0,
                  "thread_depth": MOTOR_THREAD},
        "tol": TOL,
        "extrusion": {"x": M5_POS[0][0], "size": EXTRUSION},
        "screws": SCREWS,
        "datums": {"A": "z = 0 underside", "B": "y = 50 back face", "C": "x = 0 left face", "D": "axis of the M5 hole 35 from B (55, 15)"},
        "material": "Al 6061-T6",
        "sources": {
            "ISO 4762": "M3 dk 5.5, k 3.0; M5 dk 8.5, k 5.0 (max)",
            "DIN 974-1": "counterbore diameters for ISO 4762: M3 6.5, M5 10",
            "ISO 273": "clearance holes, medium series, H13: M3 3.4, M5 5.5",
            "ISO 2306 / ISO 965": "M4x0.7-6H tap drill 3.3",
            "NEMA ICS 16": "NEMA 17: 31 mm hole square",
            "Novanta IMS size 17 linear actuator data sheet REV032022": "body 42.7, boss 22.0 +0/-0.051 x 2.0, 4x M3x0.5 thread 0.15 in min deep",
            "ISO 4759-1": "product grade A screw length tolerance js15",
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
