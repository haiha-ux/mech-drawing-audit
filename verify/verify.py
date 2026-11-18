"""Self-check of the drawing against the STEP. python verify/verify.py -> verify/report.json (exit 1 on any failure)
Checks: one valid solid; every DIMENSION is a real entity listed 1-1 in dims.json; its geometric value, its text and
dims.json agree; its defpoints are the dims.json 3D points projected through views.json; those 3D points lie on the
STEP (surface or hole axis); every diameter is a cylinder of the STEP; the drawn views match a fresh hidden-line
projection of the STEP; every hole has a size and a location; GD&T frames are TOLERANCE entities near their feature,
datums A/B/C exist; title block content.
"""
import json
import math
import os
import re
import sys
from pathlib import Path

import ezdxf
import numpy as np
from build123d import import_step, Vertex, GeomType

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("MDA_OUT", ROOT / "out"))     # break_test.py points this at a damaged copy
checks, report = [], {}


def check(name, ok, **kw):
    checks.append({"name": name, "pass": bool(ok), **kw})
    print(("PASS " if ok else "FAIL ") + name, kw if kw else "")


def proj(v, p):
    p = np.asarray(p, float)
    return np.array([v["origin"][0] + v["scale"] * (p @ np.array(v["right"])), v["origin"][1] + v["scale"] * (p @ np.array(v["up"]))])


def main():
    part = import_step(OUT / "part.step")
    b = part.bounding_box()
    check("part.step: one valid solid", len(part.solids()) == 1 and part.is_valid, solids=len(part.solids()))
    report["part"] = {"volume": part.volume, "bbox": [b.size.X, b.size.Y, b.size.Z], "faces": len(part.faces())}
    views = {v["name"]: v for v in json.loads((OUT / "views.json").read_text())}
    dims = json.loads((OUT / "dims.json").read_text())
    gdt = json.loads((OUT / "gdt.json").read_text())
    doc = ezdxf.readfile(OUT / "part.dxf")
    msp = doc.modelspace()

    # 1. DIMENSION entities <-> dims.json
    ents = {e.dxf.handle: e for e in msp if e.dxftype() == "DIMENSION"}
    handles = [d["handle"] for d in dims]
    check("every DIMENSION is listed once in dims.json and vice versa", sorted(ents) == sorted(handles) and len(set(handles)) == len(handles),
          dxf=len(ents), json=len(dims))
    exploded = [e for e in msp if e.dxftype() in ("LINE", "TEXT", "MTEXT") and e.dxf.layer == "DIM" and e.dxftype() != "LINE"]
    check("no exploded dimension text on the DIM layer", not exploded, count=len(exploded))

    # 2. value = geometry = text, and back-projection to the STEP
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    axes = []
    for f in part.faces():
        if f.geom_type != GeomType.CYLINDER:
            continue
        ax_ = BRepAdaptor_Surface(f.wrapped).Cylinder().Axis()          # the true axis, also for partial cylinders
        dvec = np.abs([ax_.Direction().X(), ax_.Direction().Y(), ax_.Direction().Z()])
        a = int(np.argmax(dvec))
        c = np.array([ax_.Location().X(), ax_.Location().Y(), ax_.Location().Z()])
        bb = f.bounding_box()
        axes.append((a, c, f.radius, np.array([bb.min.X, bb.min.Y, bb.min.Z]), np.array([bb.max.X, bb.max.Y, bb.max.Z])))
    def on_step(p):
        if part.distance_to(Vertex(*p)) <= 0.01:
            return True
        p = np.asarray(p)
        for a, c, r_, lo, hi in axes:
            off = np.delete(p - c, a)
            if np.linalg.norm(off) <= 0.01 and lo[a] - 0.01 <= p[a] <= hi[a] + 0.01:
                return True
        return False
    bad_val, bad_txt, bad_proj, bad_step, bad_cyl = [], [], [], [], []
    for d in dims:
        e = ents[d["handle"]]
        ds = doc.dimstyles.get(e.dxf.dimstyle)
        lfac = ds.dxf.dimlfac
        geo = e.get_measurement() * lfac
        if abs(geo - d["value"]) > 0.005:
            bad_val.append((d["id"], geo, d["value"]))
        blk = doc.blocks.get(e.dxf.geometry)
        txt = " ".join(m.plain_text() for m in blk if m.dxftype() == "MTEXT")
        nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", txt)]
        if not any(abs(x - d["value"]) < 1e-6 for x in nums) and "thread" not in d["feature"]:
            bad_txt.append((d["id"], txt, d["value"]))
        if "thread" in d["feature"] and not re.search(r"M%g" % d["value"], txt):
            bad_txt.append((d["id"], txt, d["value"]))
        # the override is what a CAD program re-renders from, so a hard-typed number in it must be the value too
        ovr = e.dxf.get("text", "")
        if ovr and "<>" not in ovr and "thread" not in d["feature"] and \
                not any(abs(float(x) - d["value"]) < 1e-6 for x in re.findall(r"\d+(?:\.\d+)?", ovr)):
            bad_txt.append((d["id"], "override: " + ovr, d["value"]))
        v = views[d["view"]]
        if d["type"] == "linear":
            a, c = proj(v, d["p1"]), proj(v, d["p2"])
            dp = [np.array([e.dxf.defpoint2.x, e.dxf.defpoint2.y]), np.array([e.dxf.defpoint3.x, e.dxf.defpoint3.y])]
            if min(np.linalg.norm(a - dp[0]) + np.linalg.norm(c - dp[1]), np.linalg.norm(a - dp[1]) + np.linalg.norm(c - dp[0])) > 0.02:
                bad_proj.append(d["id"])
            for q in (d["p1"], d["p2"]):
                if not on_step(q):
                    bad_step.append((d["id"], q))
        else:
            at = proj(v, d["at"])
            p0, p4 = np.array([e.dxf.defpoint.x, e.dxf.defpoint.y]), np.array([e.dxf.defpoint4.x, e.dxf.defpoint4.y])
            centre = (p0 + p4) / 2 if d["type"] == "diameter" else p0
            if np.linalg.norm(centre - at) > 0.02:
                bad_proj.append(d["id"])
            r_need = d["value"] / 2 if d["type"] == "diameter" else d["value"]
            if "thread" in d["feature"]:
                r_need = 3.3 / 2                                   # the STEP carries the tap drill; the thread is a drawing convention
            ax = int(np.argmax(np.abs(d["axis"])))
            hit = [1 for a_, c, r_, lo, hi in axes if a_ == ax and abs(r_ - r_need) < 1e-3 and np.linalg.norm(np.delete(np.asarray(d["at"]) - c, ax)) < 0.01]
            if not hit:
                bad_cyl.append(d["id"])
    check("DIMENSION geometry x DIMLFAC = dims.json value (+-0.005)", not bad_val, bad=bad_val)
    check("dimension text shows the value (thread callouts show the thread)", not bad_txt, bad=bad_txt)
    check("DIMENSION defpoints = dims.json 3D points through views.json (+-0.02 sheet mm)", not bad_proj, bad=bad_proj)
    check("every linear dimension point lies on the STEP (surface or hole axis, 0.01)", not bad_step, bad=bad_step)
    check("every diameter / radius is a cylinder of the STEP with that axis", not bad_cyl, bad=bad_cyl)
    overall = {k: [d for d in dims if d["feature"].startswith(k)] for k in ("overall length X", "overall width Y", "overall height Z")}
    check("overall X / Y / Z dimensioned", all(overall.values()), **{k: len(v) for k, v in overall.items()})

    # 3. hidden-line projection of the STEP = drawn view lines
    worst = {}
    for name in ("FRONT", "TOP", "LEFT"):
        v = views[name]
        right, up = np.array(v["right"]), np.array(v["up"])
        cam = np.cross(right, up)
        vis, hid = part.project_to_viewport(tuple(cam * 500), viewport_up=tuple(up), look_at=(0, 0, 0))
        # dense sampling (0.02 mm): sparse samples on long straight edges read as a fake offset
        pts = lambda es: np.vstack([[[p.X, p.Y] for p in e.positions(list(np.linspace(0, 1, max(31, int(e.length / 0.02)))))] for e in es])
        H = np.vstack([pts(vis), pts(hid)])
        tv = np.array([[q.X, q.Y, q.Z] for q in part.tessellate(0.01)[0]])
        shift = np.array([(tv @ right).min(), (tv @ up).min()]) - H.min(0)
        H = np.c_[v["origin"][0] + v["scale"] * (H[:, 0] + shift[0]), v["origin"][1] + v["scale"] * (H[:, 1] + shift[1])]
        x0, y0, x1, y1 = v["bbox"]
        D = []
        for e in msp.query("LWPOLYLINE[layer=='VISIBLE' | layer=='HIDDEN']"):
            P_ = np.array([p[:2] for p in e.get_points()])
            if P_[:, 0].min() >= x0 - 0.1 and P_[:, 0].max() <= x1 + 0.1 and P_[:, 1].min() >= y0 - 0.1 and P_[:, 1].max() <= y1 + 0.1:
                for a_, b_ in zip(P_[:-1], P_[1:]):
                    n_ = max(2, int(np.linalg.norm(b_ - a_) / 0.04))
                    D.append(a_ + (b_ - a_) * np.linspace(0, 1, n_)[:, None])
        D = np.vstack(D)
        from scipy.spatial import cKDTree
        d1 = cKDTree(H).query(D)[0].max() / v["scale"]
        d2 = cKDTree(D).query(H)[0].max() / v["scale"]
        worst[name] = (round(float(d1), 4), round(float(d2), 4))
    check("drawn views = fresh HLR of the STEP (<= 0.05 mm both ways)", all(max(w) <= 0.05 for w in worst.values()), **{k: list(v) for k, v in worst.items()})

    # 4. holes: size and location
    F = json.loads((OUT / "features.json").read_text())
    need = {"bore": "pilot bore", "M3": "M3 holes", "M5": "M5 holes", "M4": "M4 thr"}
    miss = []
    for key, gd in need.items():
        size = [d for d in dims if d["feature"].startswith(key) and d["type"] == "diameter"]
        loc = [d for d in dims if d["feature"].startswith(key) and "pos" in d["feature"]]
        frame = [g for g in gdt["frames"] if "position" in g["note"] and key.split()[0] in g["note"]]
        if not size or not (loc or frame):
            miss.append(key)
    check("every hole feature has a size and a location (TED + position frame)", not miss, missing=miss)

    # 5. GD&T
    tols = [e for e in msp if e.dxftype() == "TOLERANCE"]
    letters = {d["letter"] for d in gdt["datums"]}
    used = set()
    far = []
    for g in gdt["frames"]:
        used |= set(re.findall(r"%%v([A-Z])", g["content"]))
        if g.get("attached_to"):
            # ISO 1101: a frame may sit directly under the size callout of the feature it controls
            d = next(x for x in dims if x["feature"].startswith(g["attached_to"]))
            e = ents[d["handle"]]
            tm = e.dxf.text_midpoint                       # where the callout text sits on its leader
            x0, y0, x1, y1 = g["bbox"]
            dist = math.hypot(max(x0 - tm.x, 0, tm.x - x1), max(y0 - tm.y, 0, tm.y - y1))   # callout to the frame box
            lim = 12
        else:
            x0, y0, x1, y1 = g["bbox"]
            fx, fy = g["feature_pt"]
            dist, lim = math.hypot(max(x0 - fx, 0, fx - x1), max(y0 - fy, 0, fy - y1)), 25
        if dist > lim:
            far.append((g["note"], round(dist, 1)))
    check("GD&T frames are TOLERANCE entities", len(tols) == len(gdt["frames"]) and len(tols) >= 6, tolerance_entities=len(tols))
    check("every datum used in a frame has a datum symbol (A, B, C, D)", used <= letters and {"A", "B", "C"} <= letters, used=sorted(used), drawn=sorted(letters))
    check("every frame within 25 mm of its feature, or directly under the size callout it controls", not far, far=far)
    pos = [g for g in gdt["frames"] if "position" in g["note"]]
    check("position frames refer to A|B|C datums only", all(set(re.findall(r"%%v([A-Z])", g["content"])) <= {"A", "B", "C"} for g in pos))

    # 6. legibility: no text touches a line, an arrow or another text
    sys.path.insert(0, str(ROOT / "verify"))
    import overlap
    clash, ntext = overlap.clashes(msp)
    check("no text touches a line, an arrow or another text", not clash, texts=ntext, clashes=clash)
    cross, nlead = overlap.leader_crossings(msp)
    check("no leader crosses a dimension line, a GD&T frame, a datum box or a TED box", not cross, leaders=nlead, crossings=cross)

    # 7. title block
    texts = " ".join(e.dxf.text for e in msp if e.dxftype() == "TEXT")
    check("title block: author, SCALE 2:1, FIRST ANGLE, material, ISO 2768",
          all(s in texts for s in ("Ha Phan Thanh Hai", "SCALE 2:1", "FIRST ANGLE", "6061-T6", "ISO 2768", "Dimensions in mm", "Sheet 1/1")))
    check("main views drawn at the title-block scale", all(views[n]["scale"] == 2.0 for n in ("FRONT", "TOP", "LEFT", "SECTION A-A")))
    thread = [e for e in msp if e.dxf.layer == "THREAD" and e.dxftype() == "ARC" and abs((e.dxf.end_angle - e.dxf.start_angle) % 360 - 270) < 1e-6]
    check("threads end-on drawn as 3/4 circles on layer THREAD", len(thread) == len(F["m4"]), arcs=len(thread))
    import build123d
    report.update({"views": list(views), "dimensions": len(dims), "tolerance_frames": len(tols), "hlr_worst_mm": worst,
                   "tools": {"build123d": build123d.__version__, "ezdxf": ezdxf.__version__}})
    report["checks_failed"] = [c["name"] for c in checks if not c["pass"]]
    report["checks_total"] = len(checks)
    if "MDA_OUT" not in os.environ:
        (ROOT / "verify" / "report.json").write_text(json.dumps(report, indent=1, default=float))
        (ROOT / "verify" / "checks.json").write_text(json.dumps(checks, indent=1, default=str))
    print(f"\n{len(checks) - len(report['checks_failed'])}/{len(checks)} checks pass")
    sys.exit(1 if report["checks_failed"] else 0)


if __name__ == "__main__":
    main()
