# RIGSIS Well Schematic Standalone

## Run locally on Windows
```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Latest visual refinements (vNext43)
- Inclined tubular shoes use asymmetric high-side/low-side shoe markers; liner tops are also staggered to communicate inclination.
- Additional annotations wrap to multiple lines and bottom-align to their MD marker.
- vNext43: layout order is now Ruler → Well Illustration → Well Annotation → Section Details, keeping the overall canvas at 1400 × 1360 SVG units.
- Well Annotation guide lines start at the actual trajectory centerline at the annotation MD and run directly into the Well Annotation column.
- Section Details now occupy the far-right column with automatic text wrapping.
- Section 1 details start at the first section end depth; other section details remain bottom-aligned.
- Tie-back receptacle L marker uses a thicker stroke.
- Shoe depths are bold on both MD/TVD rulers.
- Legend identifies blank tubular, pre-perforated tubular, hole, cemented annulus, and tie-back receptacle top.
- PNG export excludes interactive controls.

## Features
- Side-by-side input panel and fixed schematic preview. Only the left input panel scrolls.
- Calculated J-type trajectory or Excel survey upload.
- Downloadable Excel survey template with `Survey` sheet columns `MD_m`, `Inclination_deg`, `Azimuth_deg`.
- Minimum Curvature trajectory calculations.
- Dynamic section builder: Add Section / Remove section.
- Section types: Cemented Casing, Cemented Liner, Tie-Back Casing, Blank Casing, Blank Liner, Pre-Perforated Liner, Blank + Pre-Perforated Liner, Open Hole.
- Left-side TVD and MD rulers, wavy borehole boundaries, cement annulus on cemented/tie-back sections, outward-facing shoe triangles, tie-back L marker, and additional annotations.
- Export the current schematic to a high-resolution PNG (2400 × 2840 px) directly from the browser; no Cairo or native graphics dependency required.
- No drillstring illustration.

## Notes
The supplied casing catalog is an initial catalog carried forward from the prototype. Verify casing OD, grade, weight, and ID against your approved API catalog before formal engineering use. Horizontal departure is illustrative and not to scale.

## Multi-Well Batch Export (vNext26)

The app now includes a **Multi-Well Batch Export — Excel to PNG ZIP** panel. Upload a workbook based on `RIGSIS_Well_Schematic_Multiwell_Excel_Template_v1.xlsx`; each worksheet represents one well. Use **Validate Workbook** to see per-well errors, then **Generate All PNGs and Download ZIP** to render the PNGs and package them into one ZIP. The batch export uses `resvg_py` to render SVG to PNG without requiring a system Cairo library. Install all dependencies from `requirements.txt` first.

Workbook layout expected by the importer:
- Metadata in cells B3, E3, H3 and B4/D4/F4/H4.
- Section rows 9–18, columns A:K (10 section rows). Column K is the optional Casing Connection field.
- Additional annotations rows 23–32, columns A:B.
- Survey stations rows 47 onward, columns A:C when mode is `SURVEY`.

## Export cleanup (vNext30)
- PNG export removes the interactive zoom/pan buttons and JavaScript before rendering, for both single-well browser export and Multi-Well batch PNG export.

## Manual SVG layout configuration

To tune the schematic's column widths, open `schematic.py` and edit the `LAYOUT` dictionary near the top of the file. All values are SVG coordinate units.

- `CANVAS_WIDTH`, `CANVAS_HEIGHT`: overall SVG canvas dimensions.
- `RULER_MD_X`, `RULER_TVD_X`: horizontal positions of the MD/TVD rulers.
- `WELL_X_START`, `WELL_X_SPAN`: horizontal position and span of the well illustration.
- `ANNOTATION_X`, `ANNOTATION_WIDTH`: left edge and available width of Well Annotation (the column immediately after the well illustration).
- `SECTION_X`, `SECTION_WIDTH`: left edge and available width of Section Details (the far-right column).
- `COLUMN_GAP`: general spacing parameter for column layout.
- `TITLE_WIDTH`: width of the blue title bar.

Suggested adjustment order: first set `CANVAS_WIDTH`, then `SECTION_WIDTH`, then `ANNOTATION_X` and `ANNOTATION_WIDTH`. Keep the Section Details right edge inside the canvas (`SECTION_X + SECTION_WIDTH + RIGHT_MARGIN <= CANVAS_WIDTH`). If moving columns, keep a visible gap between the well drawing, Section Details, and Well Annotation. Text wrapping is calculated from the relevant column width.

## vNext43 — Column order update
- Column order: Ruler → Well Illustration → Well Annotation → Section Details.
- Canvas dimensions remain unchanged at 1400 × 1360 SVG units.
- Well Annotation leader lines start from the actual projected trajectory centerline at each annotation MD and run directly toward the Well Annotation column.
- Manual layout and font settings in `schematic.py` are retained.

## Manual layout, colored section alignment, and tubular ID/drift

The SVG layout and font sizes are configurable in the `LAYOUT` dictionary near the top of `schematic.py`. Section-name highlights and shoe icons share a section-specific color. Well Annotation leader lines are straight solid lines starting at the actual trajectory centerline at each annotation MD.

**Tubular drift note:** the current casing catalog stores OD, weight, and ID, but does not contain catalog-specific drift values. The displayed drift is therefore currently a provisional estimate calculated as `ID - 0.125 in`, not a verified API catalog value. Replace this calculation with the exact drift values from the approved tubular catalog before using the schematic as a final engineering document.

## vNext45 layout and API drift notes

- The top margin is 20 SVG units (title box begins at y=20 after the content translation).
- Column headings and MD/TVD ruler labels share a baseline, with approximately 10 SVG units between the title box and heading text.
- Section-name highlight rectangles have no added left/right/top/bottom padding and use the matching shoe color.
- Standard casing/liner drift is calculated using API Spec 5CT 11th Edition Table C.23 standard drift deductions: nominal OD < 9-5/8 in: 3.18 mm; 9-5/8 through 13-3/8 in: 3.97 mm; >13-3/8 in: 4.76 mm, deducted from nominal catalog ID. The 30-in conductor is outside the normal API 5CT casing size range, so its drift is flagged for supplier specification rather than estimated.


### Casing catalog update (vNext46)
- Catalog values and drift diameters are taken from the user-provided Excel file.
- 30-in casing is restricted to grade X-56 in the app; the grade control is disabled for this size.
- The multiwell template includes a Casing Catalog worksheet and X-56 in the grade list.
- Ruler labels are returned to their own alignment beside the ruler, independent of the Well Annotation and Section Details headings.
