"""Copy the deliverables to deliver/ and the verify report to report.json (run after verify).  python package.py"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT, D = ROOT / "out", ROOT / "deliver"
D.mkdir(exist_ok=True)
for f in ("part.step", "part.dxf", "part.pdf", "part.png", "views.json", "dims.json", "gdt.json", "features.json"):
    shutil.copy2(OUT / f, D / f)
(D / "render").mkdir(exist_ok=True)
for f in (ROOT / "render").glob("*.png"):
    shutil.copy2(f, D / "render" / f.name)
shutil.copy2(ROOT / "verify" / "report.json", ROOT / "report.json")
print("deliver/ written")
