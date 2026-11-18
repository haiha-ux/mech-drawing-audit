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
        if e.dxf.layer in ("GDT", "HATCH", "FRAME") and t != "TEXT" or t == "TOLERANCE":
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
