"""ISO manufacturing drawing of the NEMA 17 / 2020 plate: A3, first angle, scale 2:1.
python drawing/drawing.py  ->  out/part.dxf, out/views.json, out/dims.json
Views are hidden-line projections of out/part.step. Dimensions are real DIMENSION entities placed on projected
geometry; GD&T frames are TOLERANCE entities (plus a plot-only copy on layer GDT_PDF for the PDF renderer).
"""
import datetime
import json
import math
from pathlib import Path

import ezdxf
import numpy as np
from build123d import Box, Pos, Align, import_step

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
F = json.loads((OUT / "features.json").read_text())
S = 2.0                      # drawing scale 2:1
SHEET = (420.0, 297.0)

# view definitions: camera direction (from part towards camera), up, right; sheet origin of the model origin
VIEWS = {
    "FRONT": dict(projection="front", cam=(0, -1, 0), up=(0, 0, 1), right=(1, 0, 0), origin=(60.0, 236.0)),
    "TOP": dict(projection="top", cam=(0, 0, 1), up=(0, 1, 0), right=(1, 0, 0), origin=(60.0, 76.0)),
    "LEFT": dict(projection="left", cam=(-1, 0, 0), up=(0, 0, 1), right=(0, -1, 0), origin=(345.0, 236.0)),
    "SECTION A-A": dict(projection="section", cam=(1, 0, 0), up=(0, 0, 1), right=(0, 1, 0), origin=(245.0, 168.0),
                        plane={"point": [51.0, 0.0, 0.0], "normal": [1.0, 0.0, 0.0]}),
    "ISO": dict(projection="iso", cam=(1, -1, 1), up=(0, 0, 1), right=None, origin=None, scale=1.0),
}


def unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def frame(view):
    d = VIEWS[view]
    c, up = unit(d["cam"]), unit(d["up"])
    up = unit(up - c * (up @ c))
    right = np.cross(up, c)               # right = up x towards-camera
    return c, up, right


def project(view, p):
    c, up, right = frame(view)
    d = VIEWS[view]
    s = d.get("scale", S)
    p = np.asarray(p, float)
    return d["origin"][0] + s * (p @ right), d["origin"][1] + s * (p @ up)


def setup(doc):
    doc.units = ezdxf.units.MM
    for n, col, lt, lw in (("VISIBLE", 7, "CONTINUOUS", 50), ("HIDDEN", 8, "HIDDEN", 25), ("CENTER", 3, "CENTER", 18),
                           ("THREAD", 7, "CONTINUOUS", 18), ("DIM", 1, "CONTINUOUS", 18), ("GDT", 1, "CONTINUOUS", 18),
                           ("GDT_PDF", 1, "CONTINUOUS", 18), ("DATUM", 1, "CONTINUOUS", 18), ("HATCH", 8, "CONTINUOUS", 13),
                           ("TEXT", 7, "CONTINUOUS", 25), ("FRAME", 7, "CONTINUOUS", 50), ("CUTPLANE", 3, "CENTER", 35)):
        if lt not in doc.linetypes:
            doc.linetypes.add(lt, pattern={"HIDDEN": [4.5, 3, -1.5], "CENTER": [12, 8, -2, 0, -2]}.get(lt, [0.0]))
        doc.layers.add(n, color=col, linetype=lt, lineweight=lw)
    doc.layers.get("GDT_PDF").off()            # plot-only copy of the frames; the TOLERANCE entities are on GDT
    doc.styles.add("ISO", font="isocpeur.ttf")
    doc.styles.add("SYM", font="seguisym.ttf")
    for name, gap in (("ISO25", 0.8), ("TED", -0.8)):          # negative DIMGAP = boxed theoretically exact dimension
        ds = doc.dimstyles.new(name)
        ds.dxf.dimtxt, ds.dxf.dimasz, ds.dxf.dimexe, ds.dxf.dimexo, ds.dxf.dimgap = 3.0, 3.0, 1.5, 1.0, gap
        ds.dxf.dimdec, ds.dxf.dimtad, ds.dxf.dimzin, ds.dxf.dimdsep, ds.dxf.dimlfac = 2, 1, 8, ord("."), 1 / S
        ds.dxf.dimtxsty, ds.dxf.dimclrd, ds.dxf.dimclre, ds.dxf.dimclrt = "SYM", 1, 1, 7
        ds.dxf.dimtih, ds.dxf.dimtoh = 0, 0


def hlr(part, view):
    """Visible + hidden edges of `part` in `view`, as sheet polylines (checked against our own projection)."""
    c, up, right = frame(view)
    vis, hid = part.project_to_viewport(tuple(c * 500), viewport_up=tuple(up), look_at=(0, 0, 0))
    pts = lambda e: np.array([[p.X, p.Y] for p in e.positions(list(np.linspace(0, 1, max(25, int(e.length / 0.1)))))])
    vl, hl = [pts(e) for e in vis], [pts(e) for e in hid]
    # HLR coordinates differ from ours by a shift: fix it from the tessellated part's projection, then verify
    tv = np.array([[v.X, v.Y, v.Z] for v in part.tessellate(0.01)[0]])
    s = VIEWS[view].get("scale", S)
    mine = np.c_[tv @ right, tv @ up]
    allh = np.vstack(vl)
    shift = mine.min(0) - allh.min(0)
    assert np.allclose(mine.max(0) - mine.min(0), allh.max(0) - allh.min(0), atol=1e-3), view
    o = VIEWS[view]["origin"]
    to_sheet = lambda a: np.c_[o[0] + s * (a[:, 0] + shift[0]), o[1] + s * (a[:, 1] + shift[1])]
    return [to_sheet(a) for a in vl], [to_sheet(a) for a in hl]


class Sheet:
    def __init__(self):
        self.doc = ezdxf.new("R2018", setup=True)
        setup(self.doc)
        self.msp = self.doc.modelspace()
        self.dims = []
        self.n = 0

    def poly(self, pts, layer):
        self.msp.add_lwpolyline([tuple(p) for p in pts], dxfattribs={"layer": layer})

    def line(self, a, b, layer):
        self.msp.add_line(tuple(a), tuple(b), dxfattribs={"layer": layer})

    def text(self, s, at, h=3.0, style="SYM", layer="TEXT", align=None):
        t = self.msp.add_text(s, height=h, dxfattribs={"layer": layer, "style": style})
        t.set_placement(tuple(at), align=align) if align else t.set_placement(tuple(at))
        return t

    def _record(self, d, typ, value, tol, feature, view, text, geo):
        self.n += 1
        did = f"D{self.n}"
        d.render()
        ent = d.dimension
        rec = {"id": did, "type": typ, "value": round(value, 4), "tol": tol, "feature": feature, "view": view,
               "text": text, "handle": ent.dxf.handle}
        rec.update({k: [round(float(c), 4) for c in v] for k, v in geo.items()})
        self.dims.append(rec)
        return did

    def lin(self, view, p1, p2, base, value, feature, tol="ISO2768-m", angle=0, ted=False, text="<>"):
        """Linear dimension between two model points (projected); base is a sheet point for the dimension line."""
        a, b = project(view, p1), project(view, p2)
        d = self.msp.add_linear_dim(base=base, p1=a, p2=b, angle=angle, dimstyle="TED" if ted else "ISO25",
                                    text=text, dxfattribs={"layer": "DIM"})
        return self._record(d, "linear", value, "basic" if ted else tol, feature, view, text, {"p1": p1, "p2": p2})

    def dia(self, view, centre, r_model, ang_deg, value, feature, text, tol="ISO2768-m", axis=(0, 0, 1), loc=None):
        cx, cy = project(view, centre)
        s = VIEWS[view].get("scale", S)
        d = self.msp.add_diameter_dim(center=(cx, cy), radius=r_model * s, angle=ang_deg, dimstyle="ISO25", text=text,
                                      location=loc, override={"dimtoh": 1, "dimtih": 1, "dimtad": 0},
                                      dxfattribs={"layer": "DIM"})
        return self._record(d, "diameter", value, tol, feature, view, text, {"at": centre, "axis": axis})

    def rad(self, view, centre, r_model, ang_deg, value, feature, text="<>", tol="ISO2768-m", axis=(0, 0, 1), loc=None):
        cx, cy = project(view, centre)
        s = VIEWS[view].get("scale", S)
        d = self.msp.add_radius_dim(center=(cx, cy), radius=r_model * s, angle=ang_deg, dimstyle="ISO25", text=text,
                                    location=loc, override={"dimtoh": 1, "dimtih": 1, "dimtad": 0},
                                    dxfattribs={"layer": "DIM"})
        return self._record(d, "radius", value, tol, feature, view, text, {"at": centre, "axis": axis})

    def cross(self, view, p, r_model, ext=1.5):
        cx, cy = project(view, p)
        e = r_model * S + ext
        self.line((cx - e, cy), (cx + e, cy), "CENTER")
        self.line((cx, cy - e), (cx, cy + e), "CENTER")

    def gdt(self, at, sym, tol, datums, feature_pt, note="", attached_to=None):
        """ISO 1101 frame: TOLERANCE entity + plot-only graphic copy. sym: GDT font letter."""
        content = "{\\Fgdt;%s}%%%%v%s%%%%v%s" % (sym, tol.replace("Ø", "{\\Fgdt;n}"), "%%v".join(datums))
        content = content.replace("%%%%v", "%%v")
        tol_ent = self.msp.new_entity("TOLERANCE", dxfattribs={"layer": "GDT", "dimstyle": "ISO25", "insert": (at[0], at[1], 0),
                                                              "content": content})
        uni = {"j": "⌖", "c": "⏥", "b": "⟂", "r": "◎", "u": "⏤"}[sym]
        cells = [uni, tol] + list(datums)
        x, h = at[0], 6.0
        for k, cval in enumerate(cells):
            w = 7.0 if k == 0 else (4.0 + 2.2 * len(cval) if k == 1 else 6.0)
            self.msp.add_lwpolyline([(x, at[1] - h / 2), (x + w, at[1] - h / 2), (x + w, at[1] + h / 2), (x, at[1] + h / 2)], close=True,
                                    dxfattribs={"layer": "GDT_PDF"})
            self.msp.add_text(cval, height=3.0, dxfattribs={"layer": "GDT_PDF", "style": "SYM"}).set_placement(
                (x + w / 2, at[1]), align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
            x += w
        if attached_to is None:
            self.msp.add_line((at[0], at[1]), tuple(feature_pt), dxfattribs={"layer": "GDT"})     # leader to the feature
        self.gdts.append({"insert": list(at), "content": content, "feature_pt": list(feature_pt), "note": note,
                          "handle": tol_ent.dxf.handle, "attached_to": attached_to,
                          "bbox": [at[0], at[1] - h / 2, x, at[1] + h / 2]})

    def datum(self, letter, foot, direction):
        """ISO 5459 datum feature symbol: filled triangle on the feature, square frame with the letter."""
        fx, fy = foot
        dx, dy = direction
        tri = [(fx - 1.6 * dy, fy + 1.6 * dx), (fx + 1.6 * dy, fy - 1.6 * dx), (fx + 2.8 * dx, fy + 2.8 * dy)]
        h = self.msp.add_hatch(color=1, dxfattribs={"layer": "DATUM"})
        h.paths.add_polyline_path(tri, is_closed=True)
        h.set_solid_fill()
        top = (fx + 9 * dx, fy + 9 * dy)
        self.line((fx + 2.8 * dx, fy + 2.8 * dy), top, "DATUM")
        bx, by = top[0] + 3.5 * dx, top[1] + 3.5 * dy
        self.msp.add_lwpolyline([(bx - 3.5, by - 3.5), (bx + 3.5, by - 3.5), (bx + 3.5, by + 3.5), (bx - 3.5, by + 3.5)], close=True,
                                dxfattribs={"layer": "DATUM"})
        self.text(letter, (bx, by), 4.0, align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER, layer="DATUM")
        self.datums.append({"letter": letter, "foot": list(foot)})


def main():
    part = import_step(OUT / "part.step")
    sh = Sheet()
    sh.gdts, sh.datums = [], []
    msp = sh.msp
    # ---------------- views
    views_json = []
    for v in ("FRONT", "TOP", "LEFT"):
        vl, hl = hlr(part, v)
        for a in vl:
            sh.poly(a, "VISIBLE")
        for a in hl:
            sh.poly(a, "HIDDEN")
        allp = np.vstack(vl + hl)
        views_json.append({"name": v, "projection": VIEWS[v]["projection"], "system": "first", "scale": S,
                           "origin": list(VIEWS[v]["origin"]), "bbox": [*allp.min(0).round(3), *allp.max(0).round(3)],
                           "view_dir": list(-unit(VIEWS[v]["cam"])), "up": list(frame(v)[1]), "right": list(frame(v)[2])})
    # section A-A: keep x <= 51, look from +x
    keep = part & (Pos(-10, -10, -10) * Box(61, 70, 30, align=(Align.MIN, Align.MIN, Align.MIN)))
    vl, hl = hlr(keep, "SECTION A-A")
    for a in vl:
        sh.poly(a, "VISIBLE")
    cutf = [f for f in keep.faces() if abs(f.center().X - 51.0) < 1e-6 and f.geom_type.name == "PLANE"]
    for f in cutf:
        h = msp.add_hatch(color=8, dxfattribs={"layer": "HATCH"})
        h.set_pattern_fill("ANSI31", scale=0.6)
        for k, w in enumerate([f.outer_wire()] + list(f.inner_wires())):
            pts = [project("SECTION A-A", (p.X, p.Y, p.Z)) for e in w.order_edges() for p in e.positions([i / 12 for i in range(13)])]
            h.paths.add_polyline_path(pts, is_closed=True, flags=1 if k == 0 else 0)
    allp = np.vstack(vl)
    views_json.append({"name": "SECTION A-A", "projection": "section", "system": "first", "scale": S,
                       "origin": list(VIEWS["SECTION A-A"]["origin"]), "bbox": [*allp.min(0).round(3), *allp.max(0).round(3)],
                       "plane": VIEWS["SECTION A-A"]["plane"], "view_dir": [-1.0, 0.0, 0.0], "up": [0, 0, 1], "right": [0, 1, 0]})
    # iso view at 1:1, placed in a free area
    VIEWS["ISO"]["origin"] = (0.0, 0.0)
    c, up, right = frame("ISO")
    tv = np.array([[q.X, q.Y, q.Z] for q in part.tessellate(0.05)[0]])
    u, w = tv @ right, tv @ up
    VIEWS["ISO"]["origin"] = (368.0 - (u.min() + u.max()) / 2, 95.0 - (w.min() + w.max()) / 2)
    vl, hl = hlr(part, "ISO")
    for a in vl:
        sh.poly(a, "VISIBLE")
    allp = np.vstack(vl)
    views_json.append({"name": "ISO", "projection": "iso", "system": "first", "scale": 1.0, "origin": [round(x, 4) for x in VIEWS["ISO"]["origin"]],
                       "bbox": [*allp.min(0).round(3), *allp.max(0).round(3)], "view_dir": list(-c), "up": list(up), "right": list(right)})
    for vj in views_json:
        vj["bbox"] = [float(x) for x in vj["bbox"]]
        vj["view_dir"] = [float(x) for x in vj["view_dir"]]
        vj["up"] = [float(x) for x in vj["up"]]
        vj["right"] = [float(x) for x in vj["right"]]
        lab = vj["name"] + ("" if vj["name"] != "ISO" else " (1:1)")
        sh.text(lab, (vj["bbox"][0], vj["bbox"][3] + 4), 3.5, style="ISO")

    O, P5, M3, M5, M4, PK = F["overall"], F["pilot"], F["m3"], F["m5"], F["m4"], F["pocket"]
    L, W, H = O["L"], O["W"], O["H"]
    sx, hs = F["step"]["x"], F["step"]["h"]
    # ---------------- centre lines and thread conventions
    for hole, r in [(P5, P5["d"] / 2)] + [(m, m["hole"] / 2) for m in M3] + [(m, m["hole"] / 2) for m in M5]:
        sh.cross("TOP", (hole["x"], hole["y"], H), max(r, hole.get("cbore", 0) / 2))
    sh.cross("TOP", (PK["cx"], PK["cy"], hs), min(PK["lx"], PK["ly"]) / 2)
    for hole, zt in [(P5, H)] + [(m, H) for m in M3] + [(m, hs) for m in M5]:     # axes in front and left views
        a, b = project("FRONT", (hole["x"], 0, -1)), project("FRONT", (hole["x"], 0, zt + 1))
        sh.line(a, b, "CENTER")
        a, b = project("LEFT", (0, hole["y"], -1)), project("LEFT", (0, hole["y"], zt + 1))
        sh.line(a, b, "CENTER")
    for m in M5:
        a, b = project("SECTION A-A", (51, m["y"], -1)), project("SECTION A-A", (51, m["y"], hs + 1))
        sh.line(a, b, "CENTER")
    for m in M4:
        sh.cross("FRONT", (m["x"], 0, m["z"]), m["major"] / 2)
        cx, cy = project("FRONT", (m["x"], 0, m["z"]))
        msp.add_arc((cx, cy), m["major"] / 2 * S, 0, 270, dxfattribs={"layer": "THREAD"})    # 3/4 circle: thread major dia
        for sgn in (-1, 1):                                                                   # hidden thread in top and left views
            a = project("TOP", (m["x"] + sgn * m["major"] / 2, 0, H)); b = project("TOP", (m["x"] + sgn * m["major"] / 2, m["thread_depth"], H))
            msp.add_line(a, b, dxfattribs={"layer": "THREAD", "linetype": "HIDDEN"})
        a = project("TOP", (m["x"] - m["major"] / 2, m["thread_depth"], H)); b = project("TOP", (m["x"] + m["major"] / 2, m["thread_depth"], H))
        msp.add_line(a, b, dxfattribs={"layer": "THREAD", "linetype": "HIDDEN"})
        a, b = project("TOP", (m["x"], -1, H)), project("TOP", (m["x"], m["drill_depth"] + 1, H))
        sh.line(a, b, "CENTER")
        for sgn in (-1, 1):
            a = project("LEFT", (0, 0, m["z"] + sgn * m["major"] / 2)); b = project("LEFT", (0, m["thread_depth"], m["z"] + sgn * m["major"] / 2))
            msp.add_line(a, b, dxfattribs={"layer": "THREAD", "linetype": "HIDDEN"})
    # cutting plane A-A in the top view (arrows show the viewing direction, -x)
    a, b = project("TOP", (51, -6, H)), project("TOP", (51, W + 6, H))
    sh.line(a, b, "CUTPLANE")
    for p in (a, b):
        msp.add_line(p, (p[0] - 8, p[1]), dxfattribs={"layer": "CUTPLANE", "linetype": "CONTINUOUS"})
        h = msp.add_hatch(color=3, dxfattribs={"layer": "CUTPLANE"})
        h.paths.add_polyline_path([(p[0] - 8, p[1] + 1.4), (p[0] - 8, p[1] - 1.4), (p[0] - 12, p[1])], is_closed=True)
        h.set_solid_fill()
        sh.text("A", (p[0] - 7, p[1] + (3 if p is b else -7)), 4.0, style="ISO")

    # ---------------- dimensions (TOP view: bottom = -y side, right = +x side)
    T = "TOP"
    t00, tLW, t0W, tL0 = project(T, (0, 0, H)), project(T, (L, W, H)), project(T, (0, W, H)), project(T, (L, 0, H))
    sh.lin(T, (0, 1.5, H), (L, 1.5, hs), (0, t00[1] - 34), L, "overall length X")
    sh.lin(T, (1.5, 0, H), (1.5, W, H), (t00[0] - 22, 0), W, "overall width Y", angle=90)
    sh.lin(T, (0, W - 1.5, H), (sx, W, H), (0, t0W[1] + 18), sx, "step edge X from datum C")
    sh.lin(T, (0, W - 1.5, H), (P5["x"], P5["y"], H), (0, t0W[1] + 10), P5["x"], "bore pos X from datum C", ted=True)
    sh.lin(T, (L - 1.5, W, hs), (P5["x"], P5["y"], H), (tLW[0] + 10, 0), W - P5["y"], "bore pos Y from datum B", angle=90, ted=True)
    sh.dia(T, (P5["x"], P5["y"], H), P5["d"] / 2, 135, P5["d"], "bore (NEMA pilot) dia", "<> +0.1/0", tol="+0.1/0",
           loc=(t0W[0] - 4, t0W[1] + 26))
    m3a, m3b, m3c = M3[1], M3[3], M3[0]          # (5.5, 40.5), (36.5, 40.5), (5.5, 9.5)
    sh.lin(T, (0, 1.5, H), (m3c["x"], m3c["y"], H), (0, t00[1] - 10), m3c["x"], "M3 holes pos X from datum C", ted=True)
    sh.lin(T, (m3c["x"], m3c["y"], H), (M3[2]["x"], M3[2]["y"], H), (0, t00[1] - 10), M3[2]["x"] - m3c["x"], "M3 pattern spacing X", ted=True)
    sh.lin(T, (L - 1.5, W, hs), (m3a["x"], m3a["y"], H), (tLW[0] + 18, 0), W - m3a["y"], "M3 holes pos Y from datum B", angle=90, ted=True)
    sh.lin(T, (0, 0, H), (m3c["x"], m3c["y"], H), (t00[0] - 12, 0), m3c["y"], "", angle=90, ted=True) if False else None
    sh.lin(T, (m3a["x"], m3a["y"], H), (m3c["x"], m3c["y"], H), (t00[0] - 10, 0), m3a["y"] - m3c["y"], "M3 pattern spacing Y", angle=90, ted=True)
    sh.dia(T, (m3c["x"], m3c["y"], H), m3c["hole"] / 2, 225, m3c["hole"], "M3 holes dia (4x), counterbore 6.5 x 3.4",
           "4× <> THRU\\P⌴ Ø6.5 ↧ 3.4", loc=(92.0, 32.0))
    m5a, m5b = M5[1], M5[0]                      # (51, 35), (51, 15)
    sh.lin(T, (0, 1.5, H), (m5b["x"], m5b["y"], hs), (0, t00[1] - 22), m5b["x"], "M5 holes pos X from datum C", ted=True)
    sh.lin(T, (L - 1.5, W, hs), (m5a["x"], m5a["y"], hs), (tLW[0] + 26, 0), W - m5a["y"], "M5 holes pos Y from datum B", angle=90, ted=True)
    sh.lin(T, (m5a["x"], m5a["y"], hs), (m5b["x"], m5b["y"], hs), (tLW[0] + 34, 0), m5a["y"] - m5b["y"], "M5 holes spacing Y", angle=90, ted=True)
    sh.dia(T, (m5b["x"], m5b["y"], hs), m5b["hole"] / 2, 315, m5b["hole"], "M5 holes dia (2x), counterbore 10 x 5.4",
           "2× <> THRU\\P⌴ Ø10 ↧ 5.4", loc=(234.0, 80.0))
    px0, px1 = PK["cx"] - PK["lx"] / 2, PK["cx"] + PK["lx"] / 2
    py0, py1 = PK["cy"] - PK["ly"] / 2, PK["cy"] + PK["ly"] / 2
    sh.lin(T, (px0, py1, hs), (px1, py1, hs), (0, project(T, (0, py1, hs))[1] + 5), PK["lx"], "pocket length X")
    sh.lin(T, (px0, py0, hs), (px0, py1, hs), (project(T, (px0, 0, hs))[0] - 9, 0), PK["ly"], "pocket width Y", angle=90)
    rc = (px1 - PK["r"], py1 - PK["r"], hs)
    sh.rad(T, rc, PK["r"], 45, PK["r"], "pocket corner radius (4x, cutter R2)", text="4× <>", loc=(project(T, (px1, 0, 0))[0] + 3, project(T, (0, py1, hs))[1] + 5))
    ch = F["chamfer"]
    sh.lin(T, (L - ch, W, hs), (L, W - ch, hs), (0, tLW[1] + 6), ch, "corner chamfer leg (4x, 45 deg)", text="4× <>×45°")
    # FRONT view
    Fv = "FRONT"
    f00, fL0 = project(Fv, (0, 0, 0)), project(Fv, (L, 0, 0))
    sh.lin(Fv, (0, 1.5, 0), (0, 1.5, H), (f00[0] - 10, 0), H, "overall height Z", angle=90)
    sh.lin(Fv, (L, 1.5, 0), (L, 1.5, hs), (fL0[0] + 8, 0), hs, "step thickness Z", angle=90)
    m4a, m4b = M4
    sh.lin(Fv, (0, 1.5, H), (m4a["x"], 0, m4a["z"]), (0, project(Fv, (0, 0, H))[1] + 8), m4a["x"], "M4 holes pos X from datum C", ted=True)
    sh.lin(Fv, (m4a["x"], 0, m4a["z"]), (m4b["x"], 0, m4b["z"]), (0, project(Fv, (0, 0, H))[1] + 8), m4b["x"] - m4a["x"], "M4 holes spacing X", ted=True)
    sh.lin(Fv, (0, 1.5, 0), (m4a["x"], 0, m4a["z"]), (f00[0] - 20, 0), m4a["z"], "M4 holes pos Z from datum A", angle=90, ted=True)
    sh.dia(Fv, (m4b["x"], 0, m4b["z"]), m4b["major"] / 2, 45, m4b["major"], "M4 thread major dia (2x); tap drill 3.3 x 10 in the STEP",
           "2× M4×0.7-6H ↧ 8\\Ptap drill Ø3.3 ↧ 10", tol="6H", axis=(0, 1, 0), loc=(150.0, 278.0))
    # SECTION A-A: pocket depth
    Sv = "SECTION A-A"
    sh.lin(Sv, (51, py0, hs), (51, py0, hs - PK["depth"]), (project(Sv, (51, 0, 0))[0] - 8, 0), PK["depth"], "pocket depth Z", angle=90)

    # ---------------- datums, GD&T, roughness (frames sit outside the views, leader to the feature)
    fa = project(Fv, (6, 0, 0))
    sh.datum("A", fa, (0, -1))
    fb = project(T, (8, W, H))
    sh.datum("B", (project(T, (30, W, H))[0], fb[1]), (0, 1))
    fc = project(T, (0, 22, H))
    sh.datum("C", fc, (-1, 0))
    fd = project(Sv, (51, m5b["y"] - m5b["hole"] / 2, 1.5))
    sh.datum("D", fd, (0, -1)) if False else sh.datum("D", (fd[0], project(Sv, (51, 0, 0))[1]), (0, -1))
    fl = project(Fv, (30, 0, 0))
    sh.gdt((fl[0] - 6, fl[1] - 12), "c", "0.02", [], fl, "flatness of A")
    bpt = project(T, (52, W, H))
    sh.gdt((bpt[0] + 6, bpt[1] + 22), "b", "0.05", ["A"], bpt, "perpendicularity of B to A")
    m3pt = project(T, (m3a["x"] + m3a["cbore"] / 2 * 0.7071, m3a["y"] + m3a["cbore"] / 2 * 0.7071, H))
    sh.gdt((92.0, 22.5), "j", "Ø0.1", ["A", "B", "C"], m3pt, "position of 4x M3 holes", attached_to="M3 holes dia")
    p5pt = project(T, (P5["x"], P5["y"] + P5["d"] / 2, H))
    sh.gdt((21.0, t0W[1] + 18.5), "j", "Ø0.05", ["A", "B", "C"], p5pt, "position of the pilot bore", attached_to="bore (NEMA pilot) dia")
    m5pt = project(T, (m5b["x"] + m5b["cbore"] / 2, m5b["y"], hs))
    sh.gdt((234.0, 70.5), "j", "Ø0.2", ["A", "B", "C"], m5pt, "position of 2x M5 holes", attached_to="M5 holes dia")
    m4pt = project(Fv, (m4a["x"], 0, m4a["z"] + m4a["major"] / 2))
    sh.gdt((150.0, 268.5), "j", "Ø0.2", ["A", "C", "B"], m4pt, "position of 2x M4 threads", attached_to="M4 thread major dia")
    cbp = project(Sv, (51, m5b["y"] + m5b["cbore"] / 2, hs - 2.7))
    sh.gdt((cbp[0] + 14, cbp[1] - 14), "r", "Ø0.1", ["D"], cbp, "coaxiality of M5 counterbore to hole D")
    rx, ry = project(Fv, (48, 0, 0))
    msp.add_lwpolyline([(rx - 3, ry - 6), (rx, ry), (rx + 9, ry - 16)], dxfattribs={"layer": "DIM"})
    msp.add_line((rx - 3, ry - 6), (rx + 3, ry - 6), dxfattribs={"layer": "DIM"})
    sh.text("Ra 1.6", (rx + 6, ry - 10), 3.0, style="ISO")

    # ---------------- frame, title block, notes
    Wd, Hd = SHEET
    msp.add_lwpolyline([(0, 0), (Wd, 0), (Wd, Hd), (0, Hd)], close=True, dxfattribs={"layer": "FRAME"})
    msp.add_lwpolyline([(20, 10), (Wd - 10, 10), (Wd - 10, Hd - 10), (20, Hd - 10)], close=True, dxfattribs={"layer": "FRAME"})
    x0 = Wd - 190
    msp.add_lwpolyline([(x0, 10), (Wd - 10, 10), (Wd - 10, 52), (x0, 52)], close=True, dxfattribs={"layer": "FRAME"})
    for yy in (24, 38):
        sh.line((x0, yy), (Wd - 10, yy), "FRAME")
    rows = [("NEMA 17 MOTOR PLATE FOR 2020 EXTRUSION", 44, 4.0),
            (f"Material: {F['material']}   Finish: clear anodise   Mass ≈ {20484 * 2.7e-3:.0f} g", 30.5, 2.6),
            ("General tol. ISO 2768-mK   Edges break 0.2 max   Ra 3.2 unless stated", 26.5, 2.6),
            (f"Drawn: Ha Phan Thanh Hai   {datetime.date.today().isoformat()}   SCALE 2:1   A3   DWG MDA-001 rev A", 15.5, 2.6)]
    for s, y, hgt in rows:
        sh.text(s, (x0 + 3, y), hgt, style="ISO")
    # first angle symbol (ISO 5456-2): cone front view, then the view from its left placed on the right
    sx0, sy0 = Wd - 36, 31.0
    msp.add_lwpolyline([(sx0, sy0 - 4), (sx0 + 10, sy0 - 2), (sx0 + 10, sy0 + 2), (sx0, sy0 + 4)], close=True, dxfattribs={"layer": "FRAME"})
    msp.add_circle((sx0 + 20, sy0), 4, dxfattribs={"layer": "FRAME"})
    msp.add_circle((sx0 + 20, sy0), 2, dxfattribs={"layer": "FRAME"})
    sh.text("FIRST ANGLE", (sx0 - 6, sy0 - 9.5), 2.4, style="ISO")
    notes = ["NOTES",
             "1. Datums: A underside, B back face, C left face, D axis of the M5 hole at Y15.",
             "2. Boxed dimensions are theoretically exact (ISO 5458); tolerance in the frames.",
             "3. Counterbores for ISO 4762 heads: M3 Ø6.5 ↧3.4, M5 Ø10 ↧5.4 (ISO 273 medium holes).",
             "4. M4×0.7-6H thread depth 8, tap drill Ø3.3 depth 10 (ISO 2306).",
             "5. Pocket corners R2 from a Ø4 end mill. Remove all burrs."]
    for k, s in enumerate(notes):
        sh.text(s, (232, 229 - 5 * k), 2.4 if k else 2.8)
    doc = sh.doc
    for rec in sh.dims:
        if rec["tol"] != "basic":
            continue
        dim = doc.entitydb[rec["handle"]]
        blk = doc.blocks.get(dim.dxf.geometry)
        for e in blk:
            if e.dxftype() != "MTEXT":
                continue
            h = e.dxf.char_height
            txt = e.plain_text()
            w = 0.62 * h * len(txt) + 1.6
            cx, cy = e.dxf.insert.x, e.dxf.insert.y
            ap = e.dxf.attachment_point                       # 1..9: TL TC TR ML MC MR BL BC BR
            cy += {1: -h / 2, 2: -h / 2, 3: -h / 2, 7: h / 2, 8: h / 2, 9: h / 2}.get(ap, 0)
            cx += {1: w / 2 - 0.8, 4: w / 2 - 0.8, 7: w / 2 - 0.8, 3: -w / 2 + 0.8, 6: -w / 2 + 0.8, 9: -w / 2 + 0.8}.get(ap, 0)
            hh = h / 2 + 0.8
            blk.add_lwpolyline([(cx - w / 2, cy - hh), (cx + w / 2, cy - hh), (cx + w / 2, cy + hh), (cx - w / 2, cy + hh)],
                               close=True, dxfattribs={"layer": "DIM", "color": 1})
    doc.saveas(OUT / "part.dxf")
    (OUT / "views.json").write_text(json.dumps(views_json, indent=1))
    (OUT / "dims.json").write_text(json.dumps(sh.dims, indent=1))
    (OUT / "gdt.json").write_text(json.dumps({"frames": sh.gdts, "datums": sh.datums}, indent=1))
    print(len(sh.dims), "dimensions,", len(sh.gdts), "GD&T frames, views", [v["name"] for v in views_json])


if __name__ == "__main__":
    main()
