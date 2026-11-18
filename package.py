"""Copy the deliverables to deliver/ (run after verify, fit and render).  python package.py"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT, D = ROOT / "out", ROOT / "deliver"
D.mkdir(exist_ok=True)
for f in ("part.step", "assembly.step", "part.dxf", "part.pdf", "part.png", "views.json", "dims.json", "gdt.json", "features.json"):
    shutil.copy2(OUT / f, D / f)
(D / "render").mkdir(exist_ok=True)
for f in (ROOT / "render").glob("*.png"):
    shutil.copy2(f, D / "render" / f.name)
print("deliver/ written")
