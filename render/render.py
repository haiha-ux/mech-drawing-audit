"""Two shaded views of out/part.step (vtk off-screen).  python render/render.py -> render/*.png"""
from pathlib import Path

import vtk
from build123d import export_stl, import_step

ROOT = Path(__file__).resolve().parents[1]
OUT, R = ROOT / "out", ROOT / "render"


COL = {"plate": (0.78, 0.80, 0.83), "motor": (0.15, 0.15, 0.17), "extrusion": (0.62, 0.64, 0.68)}


def actor(stl, col):
    r = vtk.vtkSTLReader(); r.SetFileName(str(stl)); r.Update()
    m = vtk.vtkPolyDataMapper(); m.SetInputConnection(r.GetOutputPort())
    a = vtk.vtkActor(); a.SetMapper(m)
    p = a.GetProperty(); p.SetColor(*col); p.SetDiffuse(0.75); p.SetAmbient(0.15); p.SetSpecular(0.3)
    return a


def shot(stls, name, pos, focal=(30, 25, 5)):
    ren = vtk.vtkRenderer(); ren.GradientBackgroundOn(); ren.SetBackground(0.62, 0.66, 0.72); ren.SetBackground2(0.30, 0.33, 0.38)
    for stl, col in stls:
        ren.AddActor(actor(stl, col))
    cam = ren.GetActiveCamera(); cam.SetPosition(*pos); cam.SetFocalPoint(*focal); cam.SetViewUp(0, 0, 1)
    ren.ResetCamera(); cam.Zoom(1.3)
    w = vtk.vtkRenderWindow(); w.SetOffScreenRendering(1); w.AddRenderer(ren); w.SetSize(1600, 1200); w.Render()
    f = vtk.vtkWindowToImageFilter(); f.SetInput(w); f.Update()
    wr = vtk.vtkPNGWriter(); wr.SetFileName(str(R / name)); wr.SetInputConnection(f.GetOutputPort()); wr.Write()
    print("wrote", R / name)


def main():
    stl = OUT / "part.stl"
    export_stl(import_step(OUT / "part.step"), stl, tolerance=0.01, angular_tolerance=0.2)
    shot([(stl, COL["plate"])], "1_iso_top.png", (150, -120, 120))
    shot([(stl, COL["plate"])], "2_iso_front_threads.png", (-60, -150, 60))
    # assembly: plate, motor, extrusion envelope, screws (out/assembly.step from verify/fit.py)
    asm = []
    for c in import_step(OUT / "assembly.step").children:
        f = OUT / f"asm_{c.label}.stl"
        export_stl(c, f, tolerance=0.05, angular_tolerance=0.3)
        asm.append((f, COL.get(c.label, (0.90, 0.55, 0.15) if c.label[:1] == "M" else (0.35, 0.35, 0.38))))   # screws orange
    shot(asm, "3_assembly.png", (170, -170, 90), focal=(32, 25, -15))


if __name__ == "__main__":
    main()
