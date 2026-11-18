# mech-drawing-audit

A CNC-milled part and its ISO production drawing, plus a script that checks the drawing against the 3D model.
The checks read the DXF itself, not a picture of it. The part is a NEMA 17 motor plate that bolts to 2020
aluminium extrusion.

![drawing](deliver/part.png)

| | |
|---|---|
| Part | 60 × 50 × 10 mm, Al 6061-T6, clear anodised. Stepped to 6 mm beyond x = 42 so that end sits on the extrusion |
| Features | Ø22.5 pilot bore for the motor boss; 4 × M3 counterbored on the 31 mm NEMA 17 square; 2 × M5 counterbored for the extrusion slot, 20 apart; 2 × M4×0.7-6H tapped 8 deep in the front face; a 12 × 8 × 2 pocket with R2 corners; 1 × 45° chamfer on the 4 vertical corners |
| Drawing | A3, scale 2:1, first-angle projection. Front, top, left, section A-A, and an iso view at 1:1. 26 real DIMENSION entities, 7 GD&T frames, datums A–D, title block, ISO 2768-mK |

## Files

| Path | What it is |
|---|---|
| `deliver/part.step` | the model |
| `deliver/part.dxf`, `part.pdf`, `part.png` | the drawing |
| `deliver/views.json` | each view's projection: origin, right and up vectors, scale |
| `deliver/dims.json` | each dimension: DXF handle, view, value, tolerance, and the 3D points it measures (`p1`/`p2`, or `at`/`axis` for a diameter or radius) |
| `deliver/gdt.json` | each GD&T frame: DXF handle, content, the feature it controls |
| `deliver/render/` | shaded views of the model |
| `verify/report.json`, `verify/checks.json` | check results |
| `verify/break_test.json` | the damaged copies and what caught them |

Run everything with `python run_all.py`, using a Python 3.11 that has build123d 0.13, ezdxf and vtk. The PDF step
needs PyMuPDF; its interpreter path is at the top of `run_all.py`.

## How the drawing is made

- The views are hidden-line projections of `part.step`, so the drawing cannot drift from the model.
- Every dimension is a DIMENSION entity, not loose lines and text. The sheet is at 2:1, so the dimension style
  sets DIMLFAC = 0.5 and the numbers read in true mm.
- Theoretically exact dimensions (ISO 5458) use their own dimension style, with a box around the number.
- GD&T frames are TOLERANCE entities on layer `GDT`. The PDF renderer does not draw TOLERANCE, so a line copy of each
  frame sits on layer `GDT_PDF`. That layer is off in the DXF and switched on only for the PDF.
- Threads seen end-on are drawn as ¾ circles on layer `THREAD`.

## What `verify/verify.py` checks (18 checks)

1. `part.step` is one valid solid.
2. The DXF's DIMENSION entities and `dims.json` match one to one, and no dimension has been exploded into
   loose text.
3. Each dimension's measured geometry × DIMLFAC equals its `dims.json` value to 0.005 mm. The text shows that value,
   both in the rendered block and in any typed override.
4. Each dimension's defpoints are its `dims.json` 3D points projected through `views.json`, to 0.02 sheet mm.
5. Every linear dimension point lies on the STEP, either on a surface or on a hole axis. Every diameter and radius
   is a cylinder of the STEP with that axis.
6. Overall X, Y and Z are dimensioned.
7. Each drawn view matches a fresh hidden-line projection of the STEP to 0.05 mm, in both directions, so nothing is
   missing and nothing is extra.
8. Every hole has a size, a location given as theoretically exact dimensions, and a position frame.
9. The GD&T frames are TOLERANCE entities, every datum letter they use has a datum symbol, and each frame sits near
   its feature or directly under the size callout it controls.
10. The title block has the author, scale, projection, material and general tolerance, and the views are drawn at
    the title-block scale.

`verify/break_test.py` damages a copy of the outputs five ways and confirms each damaged copy is rejected:

- a dimension that shows 41 instead of 42;
- a dimension point moved 1 mm;
- `dims.json` pointing 0.5 mm off the part;
- a GD&T frame deleted;
- the pilot bore opened to Ø23 in the model while the drawing still says Ø22.5.

All five are caught. The first version of the checks missed the typed override, so the override check in step 3 was
added after this test failed.

## Design values and sources

- NEMA 17: 22 mm pilot boss and 31 mm M3 square (NEMA ICS 16). The bore is 22.5, which leaves clearance on the boss.
- Counterbores fit ISO 4762 socket heads: M3 head 5.5 × 3.0 → Ø6.5 ↧ 3.4, M5 head 8.5 × 5.0 → Ø10 ↧ 5.4.
  Clearance holes are ISO 273 medium: 3.4 and 5.5.
- M4×0.7-6H, tap drill Ø3.3 (ISO 2306), thread 8 deep, drill 10 deep.
- The pocket corners are R2, so a Ø4 end mill can cut them.

## Limits

- The STEP models the M4 holes at tap-drill size. The thread exists only on the drawing (callout and ¾ circles),
  which is the usual practice, so the checks treat the thread callout as text and do not look for it in the model.
- The checks prove that the drawing and the model agree. They do not prove that the tolerances suit the motor or the
  extrusion; the frame values are design choices.
- The PDF is rendered from the DXF by ezdxf. Another CAD program may place dimension text slightly differently.
