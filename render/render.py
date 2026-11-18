"""Two shaded views of out/part.step (vtk off-screen).  python render/render.py -> render/*.png"""
from pathlib import Path

import vtk
from build123d import export_stl, import_step

ROOT = Path(__file__).resolve().parents[1]
OUT, R = ROOT / "out", ROOT / "render"


def shot(stl, name, pos, focal=(30, 25, 5)):
    r = vtk.vtkSTLReader(); r.SetFileName(str(stl)); r.Update()
    m = vtk.vtkPolyDataMapper(); m.SetInputConnection(r.GetOutputPort())
    a = vtk.vtkActor(); a.SetMapper(m)
    p = a.GetProperty(); p.SetColor(0.78, 0.80, 0.83); p.SetDiffuse(0.75); p.SetAmbient(0.15); p.SetSpecular(0.3)
    ren = vtk.vtkRenderer(); ren.GradientBackgroundOn(); ren.SetBackground(0.62, 0.66, 0.72); ren.SetBackground2(0.30, 0.33, 0.38)
    ren.AddActor(a)
    cam = ren.GetActiveCamera(); cam.SetPosition(*pos); cam.SetFocalPoint(*focal); cam.SetViewUp(0, 0, 1)
    ren.ResetCamera(); cam.Zoom(1.3)
    w = vtk.vtkRenderWindow(); w.SetOffScreenRendering(1); w.AddRenderer(ren); w.SetSize(1600, 1200); w.Render()
    f = vtk.vtkWindowToImageFilter(); f.SetInput(w); f.Update()
    wr = vtk.vtkPNGWriter(); wr.SetFileName(str(R / name)); wr.SetInputConnection(f.GetOutputPort()); wr.Write()
    print("wrote", R / name)


def main():
    stl = OUT / "part.stl"
    export_stl(import_step(OUT / "part.step"), stl, tolerance=0.01, angular_tolerance=0.2)
    shot(stl, "1_iso_top.png", (150, -120, 120))
    shot(stl, "2_iso_front_threads.png", (-60, -150, 60))


if __name__ == "__main__":
    main()
