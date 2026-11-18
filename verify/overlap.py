"""Text legibility on the drawing: no text may touch a line, an arrow or another text.
Used by verify.py. Every text (TEXT, dimension MTEXT, plot-only frame cells) gets its real extents from the font;
every other entity, dimension blocks included, is flattened to points 0.15 mm apart. A text is clear when no point
falls inside its box (SHRINK = 0: touching counts; a box drawn around a text, or the gap above a dimension line,
lies outside the box and does not).
"""
import numpy as np
from ezdxf import bbox, disassemble
from ezdxf.tools import text_size

SHRINK = 0.0


def items(msp):
    texts, pts = [], []
    for e in disassemble.recursive_decompose(msp):
        t = e.dxftype()
        if e.dxf.layer in ("HATCH", "FRAME") and t != "TEXT" or t == "TOLERANCE":
            continue                       # TOLERANCE is drawn by its GDT_PDF copy; section hatch and sheet frame skipped
        if not e.dxf.layer == "GDT_PDF" and msp.doc.layers.get(e.dxf.layer).is_off():
            continue
        if t == "TEXT":
            ext = bbox.extents([e], fast=False)
            texts.append((e.dxf.text, ext.extmin.x, ext.extmin.y, ext.extmax.x, ext.extmax.y))
            continue
        if t == "MTEXT":
            # bbox.extents mis-sizes dimension MTEXT here, so build the box from the font size and the attachment
            # point in the text's own frame, then rotate it to the sheet
            sz = text_size.mtext_size(e)
            w, h, ap = sz.total_width, sz.total_height, e.dxf.attachment_point
            lx0, ly1 = -w * ((ap - 1) % 3) / 2, h * ((ap - 1) // 3) / 2
            d = e.dxf.get("text_direction")
            a = np.arctan2(d[1], d[0]) if d is not None else np.radians(e.dxf.get("rotation", 0.0))
            c, s_ = np.cos(a), np.sin(a)
            corners = np.array([(x, y) for x in (lx0, lx0 + w) for y in (ly1 - h, ly1)])
            sheet = np.c_[corners[:, 0] * c - corners[:, 1] * s_, corners[:, 0] * s_ + corners[:, 1] * c] + [e.dxf.insert.x, e.dxf.insert.y]
            texts.append((e.plain_text(), *sheet.min(0), *sheet.max(0)))
            continue
        for p in disassemble.to_primitives([e]):
            v = np.array([(q.x, q.y) for q in p.vertices()])
            if len(v) == 1:
                pts.append(v)
            for a, b in zip(v[:-1], v[1:]):
                n = max(2, int(np.linalg.norm(b - a) / 0.15) + 1)
                pts.append(a + (b - a) * np.linspace(0, 1, n)[:, None])
    return texts, np.vstack(pts)


def clashes(msp):
    texts, pts = items(msp)
    out = []
    for s, x0, y0, x1, y1 in texts:
        x0, y0, x1, y1 = x0 + SHRINK, y0 + SHRINK, x1 - SHRINK, y1 - SHRINK
        inside = (pts[:, 0] > x0) & (pts[:, 0] < x1) & (pts[:, 1] > y0) & (pts[:, 1] < y1)
        if inside.any():
            out.append((s, "line", [round(c, 1) for c in pts[inside][0]]))
    for i, a in enumerate(texts):
        for b in texts[i + 1:]:
            if a[1] < b[3] - SHRINK and b[1] < a[3] - SHRINK and a[2] < b[4] - SHRINK and b[2] < a[4] - SHRINK:
                out.append((a[0], "text", b[0]))
    return out, len(texts)


def _segs(entities):
    out = []
    for p in disassemble.to_primitives(entities):
        v = [(q.x, q.y) for q in p.vertices()]
        out += list(zip(v[:-1], v[1:]))
    return out


def _cross(a, b, c, d, end_tol=0.3):
    """Segments ab and cd cross at a point that is not within end_tol of an end of ab (the leader)."""
    a, b, c, d = map(np.asarray, (a, b, c, d))
    r, s = b - a, d - c
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-12:
        return False
    t = ((c - a)[0] * s[1] - (c - a)[1] * s[0]) / den
    u = ((c - a)[0] * r[1] - (c - a)[1] * r[0]) / den
    L = np.linalg.norm(r)
    return end_tol / L < t < 1 - end_tol / L and 0 <= u <= 1


def leader_crossings(msp):
    """Leaders (diameter / radius callouts, GD&T frame leaders) must not cross a dimension line, a frame, a datum
    box or a TED box. Extension lines and view geometry may be crossed."""
    leaders, obstacles = [], []
    for e in msp:
        if e.dxftype() == "DIMENSION":
            ve = list(e.virtual_entities())
            if e.dimtype in (3, 4):                                     # diameter, radius: its lines are the leader
                leaders += [(e.dxf.handle, s) for s in _segs([x for x in ve if x.dxftype() == "LINE"])]
            else:
                dp = np.array([e.dxf.defpoint.x, e.dxf.defpoint.y])
                ang = np.radians(e.dxf.get("angle", 0.0))
                u = np.array([np.cos(ang), np.sin(ang)])
                for x in ve:
                    if x.dxftype() == "LINE":   # the dimension line: through defpoint and along the dimension angle
                        a, b = np.array([x.dxf.start.x, x.dxf.start.y]), np.array([x.dxf.end.x, x.dxf.end.y])
                        d = b - a
                        n = np.linalg.norm(d)
                        if n > 0 and abs(d[0] * (dp - a)[1] - d[1] * (dp - a)[0]) / n < 0.01 and abs(d[0] * u[1] - d[1] * u[0]) / n < 0.01:
                            obstacles.append((e.dxf.handle, (tuple(a), tuple(b))))
                    elif x.dxftype() == "LWPOLYLINE":                   # TED box
                        obstacles += [(e.dxf.handle, s) for s in _segs([x])]
        elif e.dxftype() == "LINE" and e.dxf.layer == "GDT":
            leaders.append((e.dxf.handle, ((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y))))
        elif e.dxftype() == "LWPOLYLINE" and e.dxf.layer in ("GDT_PDF", "DATUM"):
            obstacles += [(e.dxf.handle, s) for s in _segs([e])]
    out = []
    for h, (a, b) in leaders:
        for h2, (c, d) in obstacles:
            if h2 != h and _cross(a, b, c, d):
                out.append((h, [round(v, 1) for v in a], [round(v, 1) for v in b], h2))
                break
    return out, len(leaders)
