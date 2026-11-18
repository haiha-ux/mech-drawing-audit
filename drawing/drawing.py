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
from ezdxf.tools import text_size
import numpy as np
from build123d import Box, Pos, Align, import_step

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
F = json.loads((OUT / "features.json").read_text())
S = 2.0                      # drawing scale 2:1
SHEET = (420.0, 297.0)
SECTION_X = 55.0             # section A-A through the M5 holes
# sheet positions of callouts, frames and notes (tuned so that no text touches a line: verify checks it)
PILOT_LOC = (125.0, 200.0)
M3_LOC, M4_LOC, M5_LOC = (215.0, 78.0), (215.0, 268.0), (245.0, 98.0)
COAX_FRAME = (288.0, 194.0)
NOTES_AT = (232.0, 231.0)
LABEL_DY = {"TOP": 20, "FRONT": 13, "SECTION A-A": 4}
LABEL_LEFT = {"TOP"}            # labels set at the left of the view (the right side carries frames)

# view definitions: camera direction (from part towards camera), up, right; sheet origin of the model origin
VIEWS = {
    "FRONT": dict(projection="front", cam=(0, -1, 0), up=(0, 0, 1), right=(1, 0, 0), origin=(60.0, 236.0)),
    "TOP": dict(projection="top", cam=(0, 0, 1), up=(0, 1, 0), right=(1, 0, 0), origin=(60.0, 76.0)),
    "LEFT": dict(projection="left", cam=(-1, 0, 0), up=(0, 0, 1), right=(0, -1, 0), origin=(345.0, 236.0)),
    "SECTION A-A": dict(projection="section", cam=(1, 0, 0), up=(0, 0, 1), right=(0, 1, 0), origin=(245.0, 168.0),
                        plane={"point": [55.0, 0.0, 0.0], "normal": [1.0, 0.0, 0.0]}),
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
    for n, col, lt, lw in (("VISIBLE", 7, "CONTINUOUS", 50), ("HIDDEN", 8, "HIDDEN", 25), ("CENTER", 3, "CENTER", 25),
                           ("THREAD", 7, "CONTINUOUS", 25), ("DIM", 1, "CONTINUOUS", 25), ("GDT", 1, "CONTINUOUS", 25),
                           ("GDT_PDF", 1, "CONTINUOUS", 25), ("DATUM", 1, "CONTINUOUS", 25), ("HATCH", 8, "CONTINUOUS", 25),
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
        pl = self.msp.add_lwpolyline([tuple(p) for p in pts], dxfattribs={"layer": layer})
        pl.dxf.flags |= 128                     # PLINEGEN: the dash pattern runs along the whole polyline

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

    def lin(self, view, p1, p2, base, value, feature, tol="ISO2768-m", angle=0, ted=False, text="<>", loc=None):
        """Linear dimension between two model points (projected); base is a sheet point for the dimension line."""
        a, b = project(view, p1), project(view, p2)
        d = self.msp.add_linear_dim(base=base, p1=a, p2=b, angle=angle, dimstyle="TED" if ted else "ISO25",
                                    text=text, location=loc, dxfattribs={"layer": "DIM"})
        return self._record(d, "linear", value, "basic" if ted else tol, feature, view, text, {"p1": p1, "p2": p2})

    def dia(self, view, centre, r_model, ang_deg, value, feature, text, tol="ISO2768-m", axis=(0, 0, 1), loc=None):
        cx, cy = project(view, centre)
        s = VIEWS[view].get("scale", S)
        d = self.msp.add_diameter_dim(center=(cx, cy), radius=r_model * s, angle=ang_deg, dimstyle="ISO25", text=text,
                                      location=loc, override={"dimtoh": 1, "dimtih": 1, "dimtad": 0},
                                      dxfattribs={"layer": "DIM"})
        did = self._record(d, "diameter", value, tol, feature, view, text, {"at": centre, "axis": axis})
        self._snap_text(self.dims[-1]["handle"])
        return did

    def _snap_text(self, handle):
        """ezdxf sizes multi-line callout text from the raw string (about twice too wide) and leaves a gap between the
        leader shoulder and the text: move the text to 1 mm past the shoulder, using the real font width."""
        dim = self.doc.entitydb[handle]
        blk = self.doc.blocks.get(dim.dxf.geometry)
        mt = next(e for e in blk if e.dxftype() == "MTEXT")
        sh_ = [e for e in blk if e.dxftype() == "LINE" and abs(e.dxf.start.y - e.dxf.end.y) < 1e-9][-1]
        ar = next(e for e in blk if e.dxftype() == "INSERT")              # arrowhead, its tip on the circle
        for ln in blk:
            if ln.dxftype() == "LINE" and ln is not sh_ and math.dist((ln.dxf.start.x, ln.dxf.start.y), (ar.dxf.insert.x, ar.dxf.insert.y)) < 4:
                ln.dxf.start = ar.dxf.insert
        x0, x1 = sorted((sh_.dxf.start.x, sh_.dxf.end.x))
        w = text_size.mtext_size(mt).total_width
        assert mt.dxf.attachment_point == 5
        nx = x1 + 1.0 + w / 2 if mt.dxf.insert.x > x1 else x0 - 1.0 - w / 2
        mt.dxf.insert = (nx, mt.dxf.insert.y, 0)
        dim.dxf.text_midpoint = (nx, mt.dxf.insert.y, 0)

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

    def under_callout(self, feature, tol, datums):
        """Frame insert next to the text of size callout `feature`, left-aligned: under it, or above it when the leader comes from below."""
        rec = next(d for d in self.dims if d["feature"].startswith(feature))
        dim = self.doc.entitydb[rec["handle"]]
        mt = next(e for e in self.doc.blocks.get(dim.dxf.geometry) if e.dxftype() == "MTEXT")
        sz = text_size.mtext_size(mt)
        tm = dim.dxf.text_midpoint
        lead_y = [y for e in self.doc.blocks.get(dim.dxf.geometry) if e.dxftype() == "LINE" for y in (e.dxf.start.y, e.dxf.end.y)]
        if min(lead_y) < tm.y - sz.total_height / 2:          # leader comes up from below: the frame goes above the text
            return (tm.x - sz.total_width / 2, tm.y + sz.total_height / 2 + 4.5)
        return (tm.x - sz.total_width / 2, tm.y - sz.total_height / 2 - 4.5)     # left edge under the text

    def gdt(self, at, sym, tol, datums, feature_pt, note="", attached_to=None):
        """ISO 1101 frame: TOLERANCE entity + plot-only graphic copy. sym: GDT font letter.
        With attached_to and at=None, the frame goes directly under that size callout's text."""
        if at is None:
            at = self.under_callout(attached_to, tol, datums)
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
        if attached_to is None:                                                # leader with an arrowhead on the feature
            if at[0] <= feature_pt[0] <= x:
                mid = (at[0] + x) / 2
                start = (mid, at[1] + h / 2) if feature_pt[1] > at[1] else (mid, at[1] - h / 2)
            else:
                start = (x, at[1]) if feature_pt[0] > x else (at[0], at[1])
            self.msp.add_line(start, tuple(feature_pt), dxfattribs={"layer": "GDT"})
            self.arrow(feature_pt, start, "GDT")
        self.gdts.append({"insert": list(at), "content": content, "feature_pt": list(feature_pt), "note": note,
                          "handle": tol_ent.dxf.handle, "attached_to": attached_to,
                          "bbox": [at[0], at[1] - h / 2, x, at[1] + h / 2]})

    def arrow(self, tip, frm, layer):
        d = np.subtract(tip, frm)
        d = d / np.linalg.norm(d)
        n = np.array([-d[1], d[0]])
        b = np.asarray(tip) - 3.0 * d
        h = self.msp.add_hatch(color=1, dxfattribs={"layer": layer})
        h.paths.add_polyline_path([tuple(tip), tuple(b + 0.5 * n), tuple(b - 0.5 * n)], is_closed=True)
        h.set_solid_fill()

    def roughness(self, surface_pt, value):
        """ISO 21920-1 graphical symbol, material removal required, on a leader from the surface (below it)."""
        sx_, sy_ = surface_pt
        vx, vy = sx_ + 8, sy_ - 22                       # symbol vertex on the leader shoulder
        self.msp.add_line((sx_, sy_), (vx - 6, vy), dxfattribs={"layer": "DIM"})
        self.arrow((sx_, sy_), (vx - 6, vy), "DIM")
        self.msp.add_line((vx - 6, vy), (vx + 3, vy), dxfattribs={"layer": "DIM"})
        h1, h2 = 5.0, 10.5
        t = math.tan(math.radians(60))
        self.msp.add_lwpolyline([(vx - h1 / t, vy + h1), (vx, vy), (vx + h2 / t, vy + h2), (vx + h2 / t + 16, vy + h2)], dxfattribs={"layer": "DIM"})
        self.msp.add_line((vx - h1 / t, vy + h1), (vx + h1 / t, vy + h1), dxfattribs={"layer": "DIM"})   # bar: material removal
        self.text(value, (vx + h2 / t + 1, vy + h2 - 4.2), 3.0, style="ISO")

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
    # section A-A: keep x <= SECTION_X, look from +x
    keep = part & (Pos(-10, -10, -10) * Box(10 + SECTION_X, 70, 30, align=(Align.MIN, Align.MIN, Align.MIN)))
    vl, hl = hlr(keep, "SECTION A-A")
    for a in vl:
        sh.poly(a, "VISIBLE")
    cutf = [f for f in keep.faces() if abs(f.center().X - SECTION_X) < 1e-6 and f.geom_type.name == "PLANE"]
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
        left = vj["name"] in LABEL_LEFT
        sh.text(lab, (vj["bbox"][0 if left else 2], vj["bbox"][3] + LABEL_DY.get(vj["name"], 4)), 3.5, style="ISO",
                align=ezdxf.enums.TextEntityAlignment.BOTTOM_LEFT if left else ezdxf.enums.TextEntityAlignment.BOTTOM_RIGHT)

    O, P5, M3, M5, M4 = F["overall"], F["pilot"], F["m3"], F["m5"], F["m4"]
    L, W, H = O["L"], O["W"], O["H"]
    XS = SECTION_X
    # ---------------- centre lines and thread conventions
    for hole, r in [(P5, P5["d"] / 2)] + [(m, m["hole"] / 2) for m in M3] + [(m, m["hole"] / 2) for m in M5]:
        sh.cross("TOP", (hole["x"], hole["y"], H), max(r, hole.get("cbore", 0) / 2))
    for hole in [P5] + M3 + M5:                                   # axes in front and left views
        a, b = project("FRONT", (hole["x"], 0, -1)), project("FRONT", (hole["x"], 0, H + 1))
        sh.line(a, b, "CENTER")
        a, b = project("LEFT", (0, hole["y"], -1)), project("LEFT", (0, hole["y"], H + 1))
        sh.line(a, b, "CENTER")
    for m in M5:
        a, b = project("SECTION A-A", (XS, m["y"], -1)), project("SECTION A-A", (XS, m["y"], H + 1))
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
    a, b = project("TOP", (XS, -6, H)), project("TOP", (XS, W + 6, H))
    sh.line(a, b, "CUTPLANE")
    for p in (a, b):
        msp.add_line(p, (p[0] - 8, p[1]), dxfattribs={"layer": "CUTPLANE", "linetype": "CONTINUOUS"})
        h = msp.add_hatch(color=3, dxfattribs={"layer": "CUTPLANE"})
        h.paths.add_polyline_path([(p[0] - 8, p[1] + 1.4), (p[0] - 8, p[1] - 1.4), (p[0] - 12, p[1])], is_closed=True)
        h.set_solid_fill()
        sh.text("A", (p[0] - 7, p[1] + (3 if p is b else -7)), 4.0, style="ISO")

    # ---------------- dimensions (TOP view: bottom = -y side, right = +x side)
    T = "TOP"
    t00, tLW, t0W = project(T, (0, 0, H)), project(T, (L, W, H)), project(T, (0, W, H))
    sh.lin(T, (0, 1.5, H), (L, 1.5, H), (0, t00[1] - 34), L, "overall length X")
    sh.lin(T, (1.5, 0, H), (1.5, W, H), (t00[0] - 30, 0), W, "overall width Y", angle=90)
    sh.lin(T, (0, W - 1.5, H), (P5["x"], P5["y"], H), (0, t0W[1] + 10), P5["x"], "bore pos X from datum C", ted=True)
    sh.lin(T, (L - 1.5, W, H), (P5["x"], P5["y"], H), (tLW[0] + 10, 0), W - P5["y"], "bore pos Y from datum B", angle=90, ted=True)
    sh.dia(T, (P5["x"], P5["y"], H), P5["d"] / 2, 80, P5["d"], "bore (NEMA pilot) dia", "<> " + P5["fit"], tol=P5["fit"],
           loc=PILOT_LOC)
    m3a, m3c = M3[1], M3[0]                      # (6.5, 40.5), (6.5, 9.5)
    sh.lin(T, (0, 1.5, H), (m3c["x"], m3c["y"], H), (0, t00[1] - 10), m3c["x"], "M3 holes pos X from datum C", ted=True)
    sh.lin(T, (m3c["x"], m3c["y"], H), (M3[2]["x"], M3[2]["y"], H), (0, t00[1] - 10), M3[2]["x"] - m3c["x"], "M3 pattern spacing X", ted=True)
    sh.lin(T, (L - 1.5, W, H), (m3a["x"], m3a["y"], H), (tLW[0] + 18, 0), W - m3a["y"], "M3 holes pos Y from datum B", angle=90, ted=True,
           loc=(tLW[0] + 18 - 2.6, (tLW[1] + project(T, (0, m3a["y"], H))[1]) / 2))
    sh.lin(T, (m3a["x"], m3a["y"], H), (m3c["x"], m3c["y"], H), (t00[0] - 10, 0), m3a["y"] - m3c["y"], "M3 pattern spacing Y", angle=90, ted=True)
    m3d = M3[2]                                  # (37.5, 9.5): its leader runs right, clear of the dimension rows
    sh.dia(T, (m3d["x"], m3d["y"], H), m3d["hole"] / 2, 345, m3d["hole"], f"M3 holes dia (4x), counterbore {m3d['cbore']:g} x {m3d['depth']:g}",
           f"4× <> H13 THRU\\P⌴ Ø{m3d['cbore']:g} ↧ {m3d['depth']:g} +0.1/0", tol="H13", loc=M3_LOC)
    m5a, m5b = M5[1], M5[0]                      # (55, 35), (55, 15)
    sh.lin(T, (0, 1.5, H), (m5b["x"], m5b["y"], H), (0, t00[1] - 22), m5b["x"], "M5 holes pos X from datum C", ted=True)
    sh.lin(T, (L - 1.5, W, H), (m5a["x"], m5a["y"], H), (tLW[0] + 26, 0), W - m5a["y"], "M5 holes pos Y from datum B", angle=90, ted=True)
    sh.lin(T, (m5a["x"], m5a["y"], H), (m5b["x"], m5b["y"], H), (tLW[0] + 34, 0), m5a["y"] - m5b["y"], "M5 holes spacing Y", angle=90, ted=True)
    sh.dia(T, (m5b["x"], m5b["y"], H), m5b["hole"] / 2, 355, m5b["hole"], f"M5 holes dia (2x), counterbore {m5b['cbore']:g} x {m5b['depth']:g}",
           f"2× <> H13 THRU\\P⌴ Ø{m5b['cbore']:g} ↧ {m5b['depth']:g} +0.1/0", tol="H13", loc=M5_LOC)
    ch = F["chamfer"]
    sh.lin(T, (L - ch, W, H), (L, W - ch, H), (0, tLW[1] + 6), ch, "corner chamfer leg (4x, 45 deg)", text="4× <>×45°",
           loc=(tLW[0] + 17, tLW[1] + 8))                       # text past the corner, clear of the B frame leader
    # FRONT view
    Fv = "FRONT"
    f00, fL0 = project(Fv, (0, 0, 0)), project(Fv, (L, 0, 0))
    sh.lin(Fv, (L, 1.5, 0), (L, 1.5, H), (fL0[0] + 10, 0), H, "overall height Z", angle=90, text="<> ±0.1", tol="±0.1")
    m4a, m4b = M4
    sh.lin(Fv, (0, 1.5, H), (m4a["x"], 0, m4a["z"]), (0, project(Fv, (0, 0, H))[1] + 8), m4a["x"], "M4 holes pos X from datum C", ted=True)
    sh.lin(Fv, (m4a["x"], 0, m4a["z"]), (m4b["x"], 0, m4b["z"]), (0, project(Fv, (0, 0, H))[1] + 8), m4b["x"] - m4a["x"], "M4 holes spacing X", ted=True)
    sh.lin(Fv, (0, 1.5, 0), (m4a["x"], 0, m4a["z"]), (f00[0] - 10, 0), m4a["z"], "M4 holes pos Z from datum A", angle=90, ted=True)
    sh.dia(Fv, (m4b["x"], 0, m4b["z"]), m4b["major"] / 2, 45, m4b["major"], "M4 thread major dia (2x); tap drill 3.3 x 10 in the STEP",
           "2× M4×0.7-6H ↧ 8\\Ptap drill Ø3.3 ↧ 10", tol="6H", axis=(0, 1, 0), loc=M4_LOC)
    # SECTION A-A: the M5 hole that is datum D, as an auxiliary dimension carrying the datum triangle (ISO 5459)
    Sv = "SECTION A-A"
    zd = 2.0
    dD = (project(Sv, (XS, 0, 0))[1] - 9)
    sh.lin(Sv, (XS, m5b["y"] - m5b["hole"] / 2, zd), (XS, m5b["y"] + m5b["hole"] / 2, zd), (0, dD), m5b["hole"],
           "M5 hole D dia (auxiliary, carries datum D)", text="(Ø<>)", tol="aux",
           loc=(project(Sv, (XS, m5b["y"] - m5b["hole"] / 2, 0))[0] - 8.0, dD + 2.4))     # text outside, left
    xl = project(Sv, (XS, m5b["y"] - m5b["hole"] / 2, 0))[0]
    sh.line((xl, dD), (xl - 14.0, dD), "DIM")                     # dimension line carried out under its text

    # ---------------- datums, GD&T, roughness
    sh.datum("A", project(Fv, (9, 0, 0)), (0, -1))          # clear of the M3 axis (6.5) and the "13" extension line
    sh.datum("B", project(T, (36, W, H)), (0, 1))           # clear of the "22" dimension and the pilot leader
    sh.datum("C", project(T, (0, 45, H)), (-1, 0))
    sh.datum("D", (project(Sv, (XS, m5b["y"] + m5b["hole"] / 2, 0))[0], dD), (1, 0))
    fl = project(Fv, (32, 0, 0))
    sh.gdt((fl[0] + 6, fl[1] - 14), "c", "0.05", [], fl, "flatness of A")
    bpt = project(T, (58, W, H))
    sh.gdt((bpt[0] + 8, bpt[1] + 22), "b", "0.05", ["A"], bpt, "perpendicularity of B to A")
    cpt = project(T, (0, 47, H))
    sh.gdt((22.0, cpt[1] + 12), "b", "0.05", ["A", "B"], cpt, "perpendicularity of C to A and B")
    m3pt = project(T, (m3a["x"], m3a["y"], H))
    sh.gdt(None, "j", "Ø0.1", ["A", "B", "C"], m3pt, "position of 4x M3 holes", attached_to="M3 holes dia")
    p5pt = project(T, (P5["x"], P5["y"] + P5["d"] / 2, H))
    sh.gdt(None, "j", "Ø0.05", ["A", "B", "C"], p5pt, "position of the pilot bore", attached_to="bore (NEMA pilot) dia")
    m5pt = project(T, (m5b["x"], m5b["y"], H))
    sh.gdt(None, "j", "Ø0.2", ["A", "B", "C"], m5pt, "position of 2x M5 holes", attached_to="M5 holes dia")
    m4pt = project(Fv, (m4a["x"], 0, m4a["z"]))
    sh.gdt(None, "j", "Ø0.2", ["A", "C"], m4pt, "position of 2x M4 threads", attached_to="M4 thread major dia")
    cbp = project(Sv, (XS, m5b["y"] + m5b["cbore"] / 2, H - 2.0))     # on the counterbore wall
    sh.gdt(COAX_FRAME, "r", "Ø0.1", ["D"], cbp, "coaxiality of M5 counterbore to hole D")
    sh.roughness(project(Fv, (50, 0, 0)), "Ra 1.6")

    # ---------------- frame, title block, notes
    Wd, Hd = SHEET
    msp.add_lwpolyline([(0, 0), (Wd, 0), (Wd, Hd), (0, Hd)], close=True, dxfattribs={"layer": "FRAME"})
    msp.add_lwpolyline([(20, 10), (Wd - 10, 10), (Wd - 10, Hd - 10), (20, Hd - 10)], close=True, dxfattribs={"layer": "FRAME"})
    x0 = Wd - 190
    msp.add_lwpolyline([(x0, 10), (Wd - 10, 10), (Wd - 10, 52), (x0, 52)], close=True, dxfattribs={"layer": "FRAME"})
    for yy in (22, 39):
        sh.line((x0, yy), (Wd - 10, yy), "FRAME")
    mass = part.volume * 2.7e-3
    rows = [("NEMA 17 MOTOR PLATE FOR 2020 EXTRUSION", 44, 4.0),
            (f"Material: {F['material']}   Mass ≈ {mass:.0f} g   Dimensions in mm", 34.5, 2.4),
            ("Finish: clear anodise MIL-A-8625 Type II Cl 1, 10-15 µm (see note 8)", 30.0, 2.4),
            ("General tol. ISO 2768-mK   Ra 3.2 unless stated (ISO 21920-1)   Edges 0.2 max", 25.5, 2.4),
            (f"Drawn: Ha Phan Thanh Hai   {datetime.date.today().isoformat()}   SCALE 2:1   A3   Sheet 1/1   DWG MDA-001 rev D", 14.5, 2.4)]
    for s, y, hgt in rows:
        sh.text(s, (x0 + 3, y), hgt, style="ISO")
    # first angle symbol (ISO 5456-2): cone front view, then the view from its left placed on the right
    sx0, sy0 = Wd - 34, 46.0
    msp.add_lwpolyline([(sx0, sy0 - 3), (sx0 + 8, sy0 - 1.5), (sx0 + 8, sy0 + 1.5), (sx0, sy0 + 3)], close=True, dxfattribs={"layer": "FRAME"})
    msp.add_circle((sx0 + 16, sy0), 3, dxfattribs={"layer": "FRAME"})
    msp.add_circle((sx0 + 16, sy0), 1.5, dxfattribs={"layer": "FRAME"})
    sh.text("FIRST ANGLE", (sx0 - 22, sy0 - 1), 2.2, style="ISO")
    notes = ["NOTES",
             "1. Datums: A underside, B back face, C left face, D axis of the M5 hole 35 from B.",
             "2. Boxed dimensions are theoretically exact (ISO 5458); tolerance in the frames.",
             "3. Counterbores: DIN 974-1, for ISO 4762 M3×10 (0.6 Nm: motor thread 3.8 deep) and M5×10.",
             "4. Ø3.4 and Ø5.5 clearance holes H13 (ISO 273 medium), not general tolerance.",
             "5. M4×0.7-6H ↧8, tap drill Ø3.3 ↧10 (ISO 2306): accessory mounting.",
             "6. Ø22 H8 bore locates the NEMA 17 boss (Ø22 +0/-0.051 × 2); bore is through.",
             "7. Datum A finish milled for flatness 0.05. Remove all burrs.",
             "8. Dimensions apply after anodising. Mask the Ø22 bore and the M4 threads."]
    for k, s in enumerate(notes):
        sh.text(s, NOTES_AT[0:1] + (NOTES_AT[1] - 4.0 * k,), 2.4 if k else 2.8)
    doc = sh.doc
    for rec in sh.dims:
        if rec["tol"] != "basic":
            continue
        dim = doc.entitydb[rec["handle"]]
        blk = doc.blocks.get(dim.dxf.geometry)
        for e in blk:
            if e.dxftype() != "MTEXT":
                continue
            # box in the text's own frame (font size + attachment point 1..9), then rotated with the text
            sz = text_size.mtext_size(e)
            w, h, ap, g = sz.total_width, sz.total_height, e.dxf.attachment_point, 0.8
            lx0, ly1 = -w * ((ap - 1) % 3) / 2, h * ((ap - 1) // 3) / 2
            d = e.dxf.get("text_direction")
            a = math.atan2(d[1], d[0]) if d is not None else math.radians(e.dxf.get("rotation", 0.0))
            c_, s_ = math.cos(a), math.sin(a)
            loc = [(lx0 - g, ly1 - h - g), (lx0 + w + g, ly1 - h - g), (lx0 + w + g, ly1 + g), (lx0 - g, ly1 + g)]
            blk.add_lwpolyline([(e.dxf.insert.x + x * c_ - y * s_, e.dxf.insert.y + x * s_ + y * c_) for x, y in loc],
                               close=True, dxfattribs={"layer": "DIM", "color": 1})
    doc.saveas(OUT / "part.dxf")
    (OUT / "views.json").write_text(json.dumps(views_json, indent=1))
    (OUT / "dims.json").write_text(json.dumps(sh.dims, indent=1))
    (OUT / "gdt.json").write_text(json.dumps({"frames": sh.gdts, "datums": sh.datums}, indent=1))
    print(len(sh.dims), "dimensions,", len(sh.gdts), "GD&T frames, views", [v["name"] for v in views_json])


if __name__ == "__main__":
    main()
