"""Assembly fit: plate + NEMA 17 motor + 2020 extrusion + screws, built from features.json, and checked.
python verify/fit.py -> out/assembly.step, verify/fit.json (exit 1 on any failure)

The motor and the extrusion are envelopes, not vendor models: motor body 42.3 square x 40, boss at the middle of
its tolerance, M3 tapped 4.5 deep; extrusion 20 x 20 with a 6.2 x 6 slot on top (the T-nut is not modelled).
"""
import json
import math
import os
import sys
from pathlib import Path

from build123d import Align, Box, Compound, Cylinder, Pos, export_step, import_step

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("MDA_OUT", ROOT / "out"))
TAU_6061 = 207.0        # MPa, shear strength of 6061-T6 (ASM Aerospace Specification Metals data sheet)
K_NUT = 0.2             # torque coefficient, dry steel screw
checks = []


def check(name, ok, **kw):
    checks.append({"name": name, "pass": bool(ok), **kw})
    print(("PASS " if ok else "FAIL ") + name, kw if kw else "")


def zc(d, h, x, y, z0):
    return Pos(x, y, z0) * Cylinder(d / 2, h, align=(Align.CENTER, Align.CENTER, Align.MIN))


def vol(a, b):
    i = a & b
    return 0.0 if i is None else sum(s.volume for s in i.solids())


def main():
    F = json.loads((OUT / "features.json").read_text())
    H = F["overall"]["H"]
    plate = import_step(OUT / "part.step")
    mo, ex, S = F["motor"], F["extrusion"], F["screws"]
    # motor: body below the plate, boss and shaft up into the pilot bore, M3 tapped holes
    b = mo["body"]
    motor = Pos(mo["x"], mo["y"], -40) * Box(b, b, 40, align=(Align.CENTER, Align.CENTER, Align.MIN))
    for m in F["m3"]:
        motor -= zc(2.5, mo["thread_depth"], m["x"], m["y"], -mo["thread_depth"])
    motor += zc(mo["boss_d"] - 0.026, mo["boss_h"], mo["x"], mo["y"], 0)
    motor += zc(5.0, 24, mo["x"], mo["y"], 0)
    # extrusion envelope along y under the M5 holes
    e = ex["size"]
    extr = Pos(ex["x"], F["overall"]["W"] / 2, -e) * Box(e, 80, e, align=(Align.CENTER, Align.CENTER, Align.MIN))
    extr -= Pos(ex["x"], F["overall"]["W"] / 2, -6) * Box(6.2, 82, 7, align=(Align.CENTER, Align.CENTER, Align.MIN))
    screws = []
    for kind, holes in (("M3", F["m3"]), ("M5", F["m5"])):
        s = S[kind]
        for m in holes:
            zb = H - m["depth"]                                 # head seat = counterbore floor
            screws.append((kind, m, zc(s["dk"], s["k"], m["x"], m["y"], zb) + zc(s["d"], s["length"], m["x"], m["y"], zb - s["length"])))
    parts = {"plate": plate, "motor": motor, "extrusion": extr, **{f"{k}_{i}": sc for i, (k, _, sc) in enumerate(screws)}}

    # 1. nothing overlaps except a screw in its own thread
    clash = []
    names = list(parts)
    for i, a in enumerate(names):
        for bn in names[i + 1:]:
            if {a.split("_")[0], bn.split("_")[0]} == {"M3", "motor"} or (a.startswith("M3") and bn == "motor"):
                continue
            v = vol(parts[a], parts[bn])
            if v > 1e-3:
                clash.append((a, bn, round(v, 3)))
    check("no interference (plate, motor, extrusion, 6 screws; M3 thread engagement excluded)", not clash, clash=clash)
    gap = motor.distance_to(extr)
    check("motor body clears the extrusion by >= 1 mm", gap >= 1.0, gap=round(gap, 3))
    xs = (mo["x"] - b / 2, mo["x"] + b / 2)
    check("motor body lies inside the plate in x and y", xs[0] >= 0 and mo["y"] - b / 2 >= 0 and mo["y"] + b / 2 <= F["overall"]["W"],
          motor_x=[round(v, 2) for v in xs])
    # 2. M3 engagement into the motor: enough thread, and the screw must not bottom
    for kind, m, sc in screws:
        if kind != "M3":
            continue
        eng = S["M3"]["length"] - (H - m["depth"])
        ok = S["M3"]["d"] <= eng < mo["thread_depth"]
        if not ok:
            break
    check("M3 screws engage the motor 1 d .. motor thread depth", ok, engagement=eng, thread_depth=mo["thread_depth"])
    m5 = F["m5"][0]
    tip = (H - m5["depth"]) - S["M5"]["length"]
    check("M5 screw tip stays inside the extrusion slot (6 deep)", -6.0 < tip < 0, tip_z=tip)
    # 3. material under each screw head: punch-through shear vs the tightening preload
    under = []
    for kind, holes in (("M3", F["m3"]), ("M5", F["m5"])):
        s, floor = S[kind], H - holes[0]["depth"]
        preload = s["tighten_nm"] * 1000 / (K_NUT * s["d"])          # N
        shear = math.pi * s["dk"] * floor * TAU_6061                  # N
        under.append({"screw": kind, "floor_mm": floor, "preload_N": round(preload), "shear_capacity_N": round(shear),
                      "ratio": round(shear / preload, 2), "floor_vs_d": round(floor / s["d"], 2)})
    check("material under every screw head: shear capacity >= 3 x preload and floor >= 0.8 d",
          all(u["ratio"] >= 3 and u["floor_vs_d"] >= 0.8 for u in under), under=under)

    asm = Compound(children=[p for p in parts.values()])
    for n, p in zip(parts, asm.children):
        p.label = n
    if "MDA_OUT" not in os.environ:
        export_step(asm, OUT / "assembly.step")
        (ROOT / "verify" / "fit.json").write_text(json.dumps(checks, indent=1, default=str))
    failed = [c["name"] for c in checks if not c["pass"]]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} fit checks pass")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
