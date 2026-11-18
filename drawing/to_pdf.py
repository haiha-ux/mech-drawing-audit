"""out/part.dxf -> out/part.pdf + out/part.png, A3 at 1:1 paper scale.
The plot-only GD&T copy (layer GDT_PDF) is switched on for printing because the renderer does not draw TOLERANCE.
Run with a Python that has ezdxf + PyMuPDF."""
from pathlib import Path
import ezdxf
from ezdxf.addons.drawing import Frontend, RenderContext, layout, pymupdf, config

OUT = Path(__file__).resolve().parents[1] / "out"
doc = ezdxf.readfile(OUT / "part.dxf")
doc.layers.get("GDT_PDF").on()
cfg = config.Configuration(background_policy=config.BackgroundPolicy.WHITE, color_policy=config.ColorPolicy.BLACK,
                           lineweight_scaling=0.6)
page = layout.Page(420, 297, layout.Units.mm)
st = layout.Settings(scale=1, fit_page=False)
for fmt in ("pdf", "png"):
    be = pymupdf.PyMuPdfBackend()
    Frontend(RenderContext(doc), be, config=cfg).draw_layout(doc.modelspace())
    data = be.get_pdf_bytes(page, settings=st) if fmt == "pdf" else be.get_pixmap_bytes(page, fmt="png", settings=st, dpi=120)
    (OUT / f"part.{fmt}").write_bytes(data)
print("wrote part.pdf, part.png")
