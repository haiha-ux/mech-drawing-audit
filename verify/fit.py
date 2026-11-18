"""Assembly fit: plate + NEMA 17 motor + 2020 extrusion + screws, built from features.json, and checked.
python verify/fit.py -> out/assembly.step, verify/fit.json (exit 1 on any failure)

The motor and the extrusion are envelopes, not vendor models: motor body 42.7 square x 40, boss at the middle of
its tolerance, M3 tapped to the data-sheet minimum depth; extrusion 20 x 20 with a 6.2 x 6 slot on top (the T-nut and
the slot lip are not modelled). The interference checks use nominal sizes. The screw checks also take the worst case
of the tolerances in features.json["tol"]: plate thickness, counterbore depth, screw length.
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
    motor += zc(mo["boss_d"] + sum(mo["boss_tol"]) / 2, mo["boss_h"], mo["x"], mo["y"], 0)
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
    # 2. screw stack, nominal and worst case: floor = H - counterbore depth; protrusion below A = length - floor
    tol = F["tol"]
    lo, hi = tol["cbore_depth"]
    floors = {k: (H - tol["H"] - (holes[0]["depth"] + hi), H - holes[0]["depth"], H + tol["H"] - (holes[0]["depth"] + lo))
              for k, holes in (("M3", F["m3"]), ("M5", F["m5"]))}             # (min, nominal, max)
    stack = {}
    for k in ("M3", "M5"):
        L_, tl = S[k]["length"], tol["screw_length"]
        fmin, fnom, fmax = floors[k]
        stack[k] = {"floor": [round(fmin, 2), round(fnom, 2), round(fmax, 2)],
                    "protrusion": [round(L_ - tl - fmax, 2), round(L_ - fnom, 2), round(L_ + tl - fmin, 2)]}
    p3 = stack["M3"]["protrusion"]
    check("M3 engagement into the motor, worst case, stays below the 0.15 in (3.81) minimum thread depth",
          p3[2] < mo["thread_depth"], engagement_min_nom_max=p3, thread_depth=round(mo["thread_depth"], 2),
          engagement_nominal_vs_d=round(p3[1] / S["M3"]["d"], 2))
    proud = {k: round(F[k.lower()][0]["depth"] + lo - S[k]["k"], 2) for k in ("M3", "M5")}
    check("screw heads never stand proud of the top face (counterbore depth min >= head height k max)",
          all(v >= 0 for v in proud.values()), recess=proud)
    p5 = stack["M5"]["protrusion"]
    check("M5 screw tip, worst case, stays inside the extrusion slot (6 deep, assumed)", p5[2] < 6.0,
          protrusion_min_nom_max=p5)
    # 3. material under each screw head: punch-through shear vs the tightening preload
    under = []
    for kind, holes in (("M3", F["m3"]), ("M5", F["m5"])):
        s, floor = S[kind], floors[kind][0]                         # thinnest floor
        preload = s["tighten_nm"] * 1000 / (K_NUT * s["d"])          # N
        shear = math.pi * s["dk"] * floor * TAU_6061                  # N
        under.append({"screw": kind, "floor_min_mm": round(floor, 2), "preload_N": round(preload), "shear_capacity_N": round(shear),
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
