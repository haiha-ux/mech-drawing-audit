"""One command: part -> drawing -> PDF -> verify -> fit -> renders -> break test -> deliver/.
python run_all.py   (the Python that runs it needs build123d 0.13, ezdxf, vtk; the PDF step needs ezdxf + PyMuPDF,
from the same Python unless PDF_PYTHON names another one)"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable
PDF_PY = os.environ.get("PDF_PYTHON", PY)
for cmd in ((PY, "part/part.py"), (PY, "drawing/drawing.py"), (PDF_PY, "drawing/to_pdf.py"), (PY, "verify/verify.py"),
            (PY, "verify/fit.py"), (PY, "render/render.py"), (PY, "verify/break_test.py"), (PY, "package.py")):
    print(">", *cmd)
    subprocess.run([str(c) for c in cmd], check=True, cwd=ROOT)
