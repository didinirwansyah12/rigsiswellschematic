"""SVG renderer for the standalone RIGSIS Well Schematic tool."""
from html import escape
import math
from fractions import Fraction
import numpy as np
import pandas as pd



# =============================================================================
# MANUAL SVG LAYOUT SETUP
# Adjust these values to tune column widths and horizontal positions.
# All coordinates are SVG units (roughly pixels at the native viewBox size).
# Layout order: Ruler -> Well Illustration -> Well Annotation -> Section Details.
# Keep SECTION_X + SECTION_WIDTH + RIGHT_MARGIN <= CANVAS_WIDTH.
# =============================================================================
LAYOUT = {
    # Canvas and column geometry (SVG units)
    "CANVAS_WIDTH": 1400,
    "CANVAS_HEIGHT": 1370,
    "RULER_MD_X": 82,
    "RULER_TVD_X": 100,
    "WELL_X_START": 310,
    "WELL_X_SPAN": 250,
    "SECTION_X": 950,
    "SECTION_WIDTH": 445,
    "ANNOTATION_X": 620,
    "ANNOTATION_WIDTH": 250,
    "RIGHT_MARGIN": 0,
    "COLUMN_GAP": 0,
    "TITLE_WIDTH": 500,

    # Manual font sizes (SVG units)
    "FONT_RULER_LABEL": 19,
    "FONT_RULER_DEPTH": 21,
    "FONT_SECTION_TITLE": 20,
    "FONT_SECTION_DETAIL": 22,
    "FONT_ANNOTATION": 20,
    "FONT_LEGEND": 18,
    "FONT_MAIN_TITLE": 26,
    "FONT_COLUMN_HEADING": 20,
    "FONT_ZOOM_CONTROLS": 19,

    # Text spacing / wrapping
    "DETAIL_LINE_HEIGHT": 21,
    "ANNOTATION_LINE_HEIGHT": 21,
}

# Matching section-name highlight and shoe colors. Keep order consistent with
# section sequence; pastel title highlights remain readable with white text.
SECTION_COLORS = ["#2563EB", "#0F766E", "#B45309", "#7C3AED", "#BE123C", "#475569", "#15803D", "#A16207"]


def _format_inches(value):
    """Format inch dimensions as readable mixed fractions (nearest 1/16 in)."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return str(value)
    whole = int(math.floor(x + 1e-9))
    frac = Fraction(x - whole).limit_denominator(16)
    if frac.numerator == 0:
        return str(whole)
    if frac.numerator >= frac.denominator:
        whole += 1
        frac = Fraction(0, 1)
    if frac.numerator == 0:
        return str(whole)
    return f"{whole}-{frac.numerator}/{frac.denominator}" if whole else f"{frac.numerator}/{frac.denominator}"


def _unit_tangent(inc_deg, azi_deg):
    inc, azi = math.radians(float(inc_deg)), math.radians(float(azi_deg))
    return np.array([math.sin(inc)*math.cos(azi), math.sin(inc)*math.sin(azi), math.cos(inc)])


def minimum_curvature_survey(survey_df):
    """Calculate TVD, North/East coordinates, dogleg and departure by Minimum Curvature."""
    data = survey_df[["MD_m", "Inclination_deg", "Azimuth_deg"]].astype(float).sort_values("MD_m").reset_index(drop=True)
    rows = []
    north = east = tvd = 0.0
    first = data.iloc[0]
    rows.append({"MD_m": float(first.MD_m), "Inclination_deg": float(first.Inclination_deg),
                 "Azimuth_deg": float(first.Azimuth_deg), "North_m": 0.0, "East_m": 0.0,
                 "TVD_m": 0.0, "Dogleg_deg": 0.0, "Departure_m": 0.0})
    for i in range(len(data)-1):
        a, b = data.iloc[i], data.iloc[i+1]
        ds = float(b.MD_m-a.MD_m)
        t1, t2 = _unit_tangent(a.Inclination_deg, a.Azimuth_deg), _unit_tangent(b.Inclination_deg, b.Azimuth_deg)
        dogleg = math.acos(float(np.clip(np.dot(t1, t2), -1.0, 1.0)))
        rf = 1.0 if abs(dogleg) < 1e-12 else 2.0/dogleg*math.tan(dogleg/2.0)
        i1, i2 = math.radians(a.Inclination_deg), math.radians(b.Inclination_deg)
        az1, az2 = math.radians(a.Azimuth_deg), math.radians(b.Azimuth_deg)
        north += ds/2*(math.sin(i1)*math.cos(az1)+math.sin(i2)*math.cos(az2))*rf
        east += ds/2*(math.sin(i1)*math.sin(az1)+math.sin(i2)*math.sin(az2))*rf
        tvd += ds/2*(math.cos(i1)+math.cos(i2))*rf
        rows.append({"MD_m": float(b.MD_m), "Inclination_deg": float(b.Inclination_deg),
                     "Azimuth_deg": float(b.Azimuth_deg), "North_m": north, "East_m": east,
                     "TVD_m": tvd, "Dogleg_deg": math.degrees(dogleg), "Departure_m": math.hypot(north, east)})
    return pd.DataFrame(rows)


def validate_survey(df, td):
    required = ["MD_m", "Inclination_deg", "Azimuth_deg"]
    if any(c not in df.columns for c in required):
        return ["Survey must contain MD_m, Inclination_deg, and Azimuth_deg."]
    if len(df) < 2:
        return ["Survey must contain at least two stations."]
    try:
        d = df[required].astype(float)
    except Exception:
        return ["All survey values must be numeric."]
    errors = []
    if d.isna().any().any(): errors.append("Survey contains blank values.")
    if (d.MD_m < 0).any(): errors.append("MD cannot be negative.")
    if not d.MD_m.is_monotonic_increasing or d.MD_m.duplicated().any():
        errors.append("MD values must be strictly increasing and unique.")
    if (d.Inclination_deg < 0).any() or (d.Inclination_deg > 180).any():
        errors.append("Inclination must be between 0° and 180°.")
    if (d.Azimuth_deg < 0).any() or (d.Azimuth_deg > 360).any():
        errors.append("Azimuth must be between 0° and 360°.")
    if not d.empty and float(d.MD_m.iloc[0]) != 0:
        errors.append("Survey must start at MD = 0 m.")
    if not d.empty and float(d.MD_m.max()) < float(td):
        errors.append(f"Survey must extend to TD ({float(td):,.1f} m) or beyond.")
    return errors


def generate_jtype_survey(td, kop, eob, inclination, azimuth=0.0, interval=30.0):
    """Create planned J-type survey: vertical to KOP, build to EOB, then tangent."""
    td, kop, eob, inc, azi = map(float, (td, kop, eob, inclination, azimuth))
    if not (0 <= kop < eob <= td): raise ValueError("Require 0 ≤ KOP < EOB ≤ TD.")
    if not (0 <= inc <= 90): raise ValueError("Final inclination must be between 0° and 90°.")
    if not (0 <= azi <= 360): raise ValueError("Azimuth must be between 0° and 360°.")
    md = list(np.arange(0.0, td, max(float(interval), 1.0))) + [td, kop, eob]
    md = sorted(set(round(float(x), 6) for x in md if 0 <= x <= td))
    rows = []
    for depth in md:
        inc_at_md = 0.0 if depth <= kop else inc*(depth-kop)/(eob-kop) if depth < eob else inc
        rows.append((depth, inc_at_md, azi))
    return pd.DataFrame(rows, columns=["MD_m", "Inclination_deg", "Azimuth_deg"])


def _interp(df, md, col):
    return float(np.interp(float(md), df.MD_m.to_numpy(float), df[col].to_numpy(float)))


def build_well_schematic_svg(td, trajectory_df, sections, annotations=None, title="Well Schematic"):
    """Draw two left-side depth rulers, wavy hole walls, tubulars, cement and section annotations."""
    annotations = annotations or []
    tr = trajectory_df.sort_values("MD_m").drop_duplicates("MD_m").reset_index(drop=True)
    if tr.empty: raise ValueError("Trajectory is empty.")
    td = float(td)
    max_tvd = max(float(tr.TVD_m.max()), 1.0)
    W, H = int(LAYOUT["CANVAS_WIDTH"]), int(LAYOUT["CANVAS_HEIGHT"])
    top, bottom = 78, 1280
    plot_h = bottom-top
    y_tvd = lambda v: top + min(max(float(v), 0.0), max_tvd)/max_tvd*plot_h
    y_md = lambda md: y_tvd(_interp(tr, md, "TVD_m"))
    # Project the actual North/East trajectory onto a signed 2D horizontal axis.
    # This preserves left/right changes in the projected path instead of forcing
    # every trajectory to depart only to the right.
    ne = tr[["North_m", "East_m"]].to_numpy(float)
    axis = ne[-1] - ne[0]
    if np.linalg.norm(axis) < 1e-8:
        axis = ne[int(np.argmax(tr["Departure_m"].to_numpy(float)))] - ne[0]
    if np.linalg.norm(axis) < 1e-8:
        axis = np.array([1.0, 0.0])
    axis = axis / np.linalg.norm(axis)
    signed_projection = ne @ axis
    proj_min, proj_max = float(signed_projection.min()), float(signed_projection.max())
    proj_span = max(proj_max - proj_min, 1.0)
    def x_center(md):
        north, east = _interp(tr, md, "North_m"), _interp(tr, md, "East_m")
        return LAYOUT["WELL_X_START"] + (((north*axis[0] + east*axis[1]) - proj_min) / proj_span) * LAYOUT["WELL_X_SPAN"]
    def center_point(md):
        return x_center(md), y_md(md)
    def normal_vector(md):
        # Normal to the local projected trajectory in the SVG side view.
        eps = max(0.5, min(5.0, td * 0.001))
        a, b = max(float(tr.MD_m.min()), float(md)-eps), min(float(tr.MD_m.max()), float(md)+eps)
        x1, y1 = center_point(a); x2, y2 = center_point(b)
        dx, dy = x2-x1, y2-y1
        norm = math.hypot(dx, dy)
        if norm < 1e-9:
            return (1.0, 0.0)
        return (-dy/norm, dx/norm)
    def offset_point(md, offset, side):
        x, yy = center_point(md)
        nx, ny = normal_vector(md)
        return x + side*offset*nx, yy + side*offset*ny
    def svg_path(points):
        return " ".join(("M" if i == 0 else "L")+f" {x:.1f} {yy:.1f}" for i,(x,yy) in enumerate(points))
    def points_for(start, end, n=100):
        mds = np.linspace(float(start), float(end), max(2, int(n)))
        return [(x_center(m), y_md(m)) for m in mds]
    def wavy_path(start, end, side, offset, amp=3.0, wavelength=16.0):
        ys, ye = y_md(start), y_md(end)
        # Follow the survey path and add a small wave to the hole wall.
        count = max(8, int(abs(ye-ys)/5))
        pts = []
        for j, md in enumerate(np.linspace(start, end, count)):
            phase = (y_md(md)-top)/wavelength * 2*math.pi
            pts.append(offset_point(md, offset + amp*math.sin(phase), side))
        return svg_path(pts)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" height="100%" preserveAspectRatio="xMinYMin meet" role="img" aria-label="RIGSIS Well Schematic" style="touch-action:none;cursor:grab;user-select:none">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<g id="schematicContent" transform="translate(0 15)">',
        f'<style>text{{font-family:Arial,Helvetica,sans-serif;fill:#202124;user-select:none;-webkit-user-select:none}}.small{{font-size:{LAYOUT["FONT_RULER_DEPTH"]}px}}.label{{font-size:{LAYOUT["FONT_RULER_LABEL"]}px;font-weight:700}}.detail{{font-size:{LAYOUT["FONT_SECTION_DETAIL"]}px}}.detailTitle{{font-size:{LAYOUT["FONT_SECTION_TITLE"]}px;font-weight:700}}.rulerShoe{{font-size:{LAYOUT["FONT_RULER_DEPTH"]}px;font-weight:700}}.muted{{fill:#62676d}}.ann{{font-size:{LAYOUT["FONT_ANNOTATION"]}px;font-weight:400}}.legend{{font-size:{LAYOUT["FONT_LEGEND"]}px;fill:#62676d}}</style>',
        f'<rect x="{(W-LAYOUT["TITLE_WIDTH"])/2:.1f}" y="5" width="{LAYOUT["TITLE_WIDTH"]}" height="39" rx="3" fill="#0070C0"/>',
        f'<text x="{W/2:.1f}" y="32" text-anchor="middle" font-size="{LAYOUT['FONT_MAIN_TITLE']}" font-weight="700" fill="#FFFFFF" style="fill:#FFFFFF">{escape(title).upper()} WELL SCHEMATIC</text>',
        f'<text x="{LAYOUT["ANNOTATION_X"] + LAYOUT["ANNOTATION_WIDTH"]/2:.1f}" y="69" font-size="{LAYOUT['FONT_COLUMN_HEADING']}" font-weight="700" text-anchor="middle">Well Annotation</text>',
        f'<text x="{LAYOUT["SECTION_X"] + LAYOUT["SECTION_WIDTH"]/2:.1f}" y="69" font-size="{LAYOUT['FONT_COLUMN_HEADING']}" font-weight="700" text-anchor="middle">Section Details</text>',
    ]

    # Both rulers are on the left. Vertical position is TVD; MD is interpolated at each TVD.
    ruler_md_x, ruler_tvd_x = LAYOUT["RULER_MD_X"], LAYOUT["RULER_TVD_X"]
    parts += [
        f'<text x="{ruler_md_x-7}" y="69" text-anchor="end" class="label">MD (m)</text>',
        f'<text x="{ruler_tvd_x+7}" y="69" text-anchor="start" class="label">TVD (m)</text>',
        f'<line x1="{ruler_md_x}" y1="{top}" x2="{ruler_md_x}" y2="{bottom}" stroke="#111" stroke-width="1.5"/>',
        f'<line x1="{ruler_tvd_x}" y1="{top}" x2="{ruler_tvd_x}" y2="{bottom}" stroke="#111" stroke-width="1.5"/>',
    ]
    # Show only key ruler depths: zero, TD, tubular shoes, and tie-back depths.
    # Regular 300 m station annotations are intentionally omitted.
    max_md = float(tr.MD_m.max())
    md_ticks = {0, int(round(max_md))}
    for sec in sections:
        for key in ("end_md", "tieback_md"):
            value = sec.get(key)
            if value is not None:
                try:
                    value = float(value)
                    if 0 <= value <= max_md:
                        md_ticks.add(int(round(value)))
                except (TypeError, ValueError):
                    pass
    shoe_depths = {int(round(float(sec.get("end_md", -1)))) for sec in sections if sec.get("type") != "Open Hole"}
    for md_tick in sorted(md_ticks):
        if md_tick < 0 or md_tick > max_md + 1e-6:
            continue
        md_value = min(float(md_tick), max_md)
        tv = _interp(tr, md_value, "TVD_m")
        yy = y_md(md_value)
        is_shoe = int(round(md_value)) in shoe_depths
        md_cls = "rulerShoe" if is_shoe else "small"
        tv_cls = "rulerShoe" if is_shoe else "small"
        tick_sw = 1.8 if is_shoe else 1.0
        parts.append(f'<line x1="{ruler_tvd_x-5}" y1="{yy:.1f}" x2="{ruler_tvd_x+5}" y2="{yy:.1f}" stroke="#111" stroke-width="{tick_sw}"/>')
        tv_label_x = ruler_tvd_x + (5 if abs(md_value) < 1e-6 else 8)
        parts.append(f'<text x="{tv_label_x}" y="{yy+4:.1f}" text-anchor="start" class="{tv_cls}">{tv:,.0f}</text>')
        parts.append(f'<line x1="{ruler_md_x-5}" y1="{yy:.1f}" x2="{ruler_md_x+5}" y2="{yy:.1f}" stroke="#111" stroke-width="{tick_sw}"/>')
        md_label_x = ruler_md_x - (5 if abs(md_value) < 1e-6 else 8)
        parts.append(f'<text x="{md_label_x}" y="{yy+4:.1f}" text-anchor="end" class="{md_cls}">{md_value:,.0f}</text>')

    # Explicit geometry model: the first section keeps the current visual
    # reference but is enlarged to 150%. Every later section uses an absolute
    # percentage of the NEW Section 1 width (not a repeated reduction):
    # Section 2 = 80%, Section 3 = 65%, Section 4 = 50%, Section 5 = 35%.
    # Hole boundary, tubular OD and annulus are calculated together so that
    # the tubular remains inside the wavy hole boundary.
    geometry = []
    section_width_factors = [1.00, 0.82, 0.65, 0.50, 0.35]
    first_sec = sections[0] if sections else {"type": "Open Hole", "tubular": None}
    first_tubular = first_sec.get("tubular")
    first_base_half = max(7.0, min(20.0, float(first_tubular[0]) * 0.65)) if first_tubular else 14.0
    original_first_tubular_half = 3.0 * first_base_half
    original_first_hole_half = original_first_tubular_half * 1.25
    first_hole_half = original_first_hole_half * 1.50
    tubular_to_hole_ratio = original_first_tubular_half / original_first_hole_half
    for sec_index, sec in enumerate(sections):
        stype = sec["type"]
        is_open = stype == "Open Hole"
        if sec_index < len(section_width_factors):
            factor = section_width_factors[sec_index]
        else:
            # Sections after Section 5 continue at 70% of the preceding section.
            factor = section_width_factors[-1] * (0.70 ** (sec_index - len(section_width_factors) + 1))
        hole_half = first_hole_half * factor
        if not is_open and sec.get("tubular"):
            tubular_half = hole_half * tubular_to_hole_ratio
            # Leave a minimum visible annulus on each side at small scales.
            tubular_half = min(tubular_half, hole_half - 2.0)
        else:
            tubular_half = None
        geometry.append({"hole_half": hole_half, "tubular_half": tubular_half, "width_factor": factor})

    # Draw continuous hole walls first. Their width changes only at section
    # boundaries, and each new contour starts exactly where the previous ends.
    hole_previous_end = 0.0
    for sec_index, sec in enumerate(sections):
        end = float(sec["end_md"])
        start = hole_previous_end
        if end <= start:
            continue
        hole_previous_end = end
        hole_half = geometry[sec_index]["hole_half"]
        for side in (-1, 1):
            parts.append(f'<path d="{wavy_path(start, end, side, hole_half)}" fill="none" stroke="#30343b" stroke-width="1.8"/>')

    # Draw annulus fill first, then tubular walls on top. The same precomputed
    # widths are shared by all three layers to prevent crossed or inverted lines.
    for sec_index, sec in enumerate(sections):
        start, end = float(sec["start_md"]), float(sec["end_md"])
        if end <= start:
            continue
        stype = sec["type"]
        is_open = stype == "Open Hole"
        tubular = sec.get("tubular")
        hole_half = geometry[sec_index]["hole_half"]
        half = geometry[sec_index]["tubular_half"]
        cemented = stype in {"Cemented Casing", "Cemented Liner", "Tie-Back Casing"}
        if not is_open and tubular and half is not None:
            sample_mds = np.linspace(start, end, max(12, int(abs(y_md(end)-y_md(start))/8)))
            # Cement/annulus extends fully to end depth. Tubular walls stop at
            # the base of the shoe symbol so the shoe tip itself defines end depth.
            tri = 2.0 * min(28.0, max(12.0, half * 0.72))
            wall_end_md = end
            wall_mds = np.linspace(start, wall_end_md, max(12, int(abs(y_md(wall_end_md)-y_md(start))/8)))
            left_outer = [offset_point(m, half, -1) for m in sample_mds]
            right_outer = [offset_point(m, half, 1) for m in sample_mds]
            if cemented:
                # Extend cement polygons very slightly past section boundaries so
                # adjacent cemented sections cannot leave a 1-pixel white seam.
                fill_mds = np.linspace(max(0.0, start-2.5), min(td, end+2.5), len(sample_mds))
                left_outer = [offset_point(m, half, -1) for m in fill_mds]
                right_outer = [offset_point(m, half, 1) for m in fill_mds]
                left_hole = [offset_point(m, hole_half, -1) for m in fill_mds]
                right_hole = [offset_point(m, hole_half, 1) for m in fill_mds]
                for polygon in (left_hole + list(reversed(left_outer)), right_outer + list(reversed(right_hole))):
                    points = " ".join(f"{x:.1f},{y:.1f}" for x,y in polygon)
                    parts.append(f'<polygon points="{points}" fill="#d8dadd" opacity=".95"/>')
            if stype == "Blank + Pre-Perforated Liner":
                perf_md = min(max(float(sec.get("perf_tol_md", start)), start), end)
                segments = [(start, perf_md, ""), (perf_md, end, ' stroke-dasharray="7 4"')]
                for seg_start, seg_end, dash in segments:
                    if seg_end <= seg_start:
                        continue
                    seg_mds = np.linspace(seg_start, seg_end, max(2, int((seg_end-seg_start)/max(1.0, (end-start)/max(len(sample_mds)-1, 1)))+1))
                    for side in (-1, 1):
                        pts = [offset_point(m, half, side) for m in seg_mds]
                        parts.append(f'<path d="{svg_path(pts)}" fill="none" stroke="#111" stroke-width="2.5"{dash}/>')
            else:
                dash = ' stroke-dasharray="7 4"' if "Liner" in stype else ""
                for side in (-1, 1):
                    pts = [offset_point(m, half, side) for m in wall_mds]
                    parts.append(f'<path d="{svg_path(pts)}" fill="none" stroke="#111" stroke-width="2.5"{dash}/>')
            # Do not draw a horizontal line across the tubular ID at the shoe;
            # the two tubular walls terminate cleanly at the shoe depth.
            if stype == "Tie-Back Casing":
                tie_md = float(sec.get("tieback_md", start))
                nx, ny = normal_vector(tie_md)
                # Place receptacle symbols inside the cement annulus, between
                # the tubular OD and hole boundary. Build each bracket in the
                # local tangent/normal frame so it rotates with the projected
                # well angle. The right-hand symbol is a horizontal mirror of
                # the exact L on the left-hand side.
                txv, tyv = ny, -nx
                annulus_offset = (half + hole_half) / 2.0
                for tie_side in (-1, 1):
                    ax, ay = offset_point(tie_md, annulus_offset, tie_side)
                    # L: downhole leg followed by a radial return toward the
                    # tubular. Multiplying the normal component by tie_side
                    # mirrors the shape across the tubular centerline.
                    p1 = (ax, ay)
                    p2 = (ax + txv * 9.0, ay + tyv * 9.0)
                    p3 = (p2[0] - tie_side * nx * 8.0, p2[1] - tie_side * ny * 8.0)
                    parts.append(
                        f'<path d="M {p1[0]:.1f} {p1[1]:.1f} L {p2[0]:.1f} {p2[1]:.1f} L {p3[0]:.1f} {p3[1]:.1f}" '
                        'fill="none" stroke="#111" stroke-width="4" stroke-linecap="square" stroke-linejoin="miter"/>'
                    )
        # Section Details: consistent detail typography and automatic wrapping.
        # The title remains bold; every specification line uses the same detail
        # class. Wrapping is based on the available column width, never stretched
        # horizontally with SVG textLength.
        name = sec.get("name", "Section")
        label_x = LAYOUT["SECTION_X"]
        depth_y = y_md(end)
        is_first = sec_index == 0

        def wrap_detail(text, max_chars=None):
            if max_chars is None:
                max_chars = max(18, int((LAYOUT["SECTION_WIDTH"] - 8) / 10.2))
            words = str(text).split()
            wrapped, current = [], ""
            for word in words:
                candidate = word if not current else current + " " + word
                if len(candidate) > max_chars and current:
                    wrapped.append(current)
                    current = word
                else:
                    current = candidate
            if current:
                wrapped.append(current)
            return wrapped or [""]

        detail_lines = [
            f"Hole Dia: {_format_inches(sec.get('hole_diameter', 0))} in"
        ]
        if tubular:
            casing_size = "Casing" if "Casing" in stype else "Liner"
            connection = str(sec.get("casing_connection") or "").strip()
            casing_spec = f"{casing_size}: {_format_inches(tubular[0])} in, {tubular[3]}, {tubular[1]:g} ppf"
            if connection:
                casing_spec += f", {connection}"
            detail_lines.append(casing_spec)
            tubular_id = float(tubular[2])
            tubular_drift = float(tubular[4]) if len(tubular) > 4 else tubular_id
            drift_text = f"{tubular_drift:.3f} in"
            detail_lines.append(
                f"{casing_size} ID & Drift: {tubular_id:.3f} in & {drift_text}"
            )

        if stype == "Blank + Pre-Perforated Liner":
            detail_lines.append(f"Blank Liner: {start:,.0f}–{float(sec.get('perf_tol_md', end)):,.0f} mMD")
            detail_lines.append(f"Pre-Perforated Liner: {float(sec.get('perf_tol_md', start)):,.0f}–{end:,.0f} mMD")
        elif stype == "Tie-Back Casing":
            detail_lines.append(f"Casing Depth: {end:,.0f} mMD")
            detail_lines.append(f"Tie-back Depth: {float(sec.get('tieback_md', 0)):,.0f} mMD")
        else:
            detail_lines.append(
                f"Liner Interval: {start:,.0f}–{end:,.0f} mMD"
                if "Liner" in stype else f"Casing Depth: {end:,.0f} mMD"
            )

        rendered_lines = []
        for detail in detail_lines:
            rendered_lines.extend(wrap_detail(detail))

        line_height = LAYOUT["DETAIL_LINE_HEIGHT"]
        all_line_count = 1 + len(rendered_lines)  # title + detail lines
        if is_first:
            first_baseline = y_md(0.0) + 21
        else:
            first_baseline = depth_y - line_height * (all_line_count - 1)

        section_color = SECTION_COLORS[sec_index % len(SECTION_COLORS)]
        title_font = float(LAYOUT["FONT_SECTION_TITLE"])
        title_width = min(float(LAYOUT["SECTION_WIDTH"]), max(1.0, len(str(name)) * title_font * 0.56))
        parts.append(
            f'<rect x="{label_x:.1f}" y="{first_baseline-title_font+2:.1f}" width="{title_width:.1f}" height="{title_font:.1f}" rx="0" fill="{section_color}"/>'
        )
        parts.append(
            f'<text x="{label_x}" y="{first_baseline:.1f}" class="detailTitle" style="fill:#FFFFFF">{escape(str(name))}</text>'
        )
        for li, txt in enumerate(rendered_lines, start=1):
            yy = first_baseline + li * line_height
            parts.append(
                f'<text x="{label_x}" y="{yy:.1f}" class="detail muted">{escape(txt)}</text>'
            )

    # Restore light depth guides between ruler and well schematic at each section shoe.
    for sec_index, sec in enumerate(sections):
        md = float(sec["end_md"])
        yy = y_md(md)
        hole_half = geometry[sec_index]["hole_half"]
        x_end = x_center(md) + hole_half + 8
        parts.append(f'<line x1="{ruler_tvd_x+8}" y1="{yy:.1f}" x2="{x_end:.1f}" y2="{yy:.1f}" stroke="#b7bec8" stroke-width="1" stroke-dasharray="3 4"/>')

    # Tie-back depth gets its own dashed ruler-to-well guide, but does not alter
    # the regular ruler station spacing.
    for sec_index, sec in enumerate(sections):
        try:
            tie_md = float(sec.get("tieback_md", 0) or 0)
        except (TypeError, ValueError):
            tie_md = 0.0
        if tie_md <= 0 or tie_md > max_md:
            continue
        yy = y_md(tie_md)
        hole_half = geometry[sec_index]["hole_half"]
        x_end = x_center(tie_md) + hole_half + 8
        parts.append(f'<line x1="{ruler_tvd_x+8}" y1="{yy:.1f}" x2="{x_end:.1f}" y2="{yy:.1f}" stroke="#b7bec8" stroke-width="1" stroke-dasharray="3 4"/>')

    # Redraw tubular walls after every annulus polygon has been painted. This prevents
    # later sections' cement fill from masking the first and second casing outlines.
    for sec_index, sec in enumerate(sections):
        start, end = float(sec["start_md"]), float(sec["end_md"])
        stype = sec["type"]
        tubular = sec.get("tubular")
        half = geometry[sec_index]["tubular_half"]
        if stype == "Open Hole" or not tubular or half is None or end <= start:
            continue
        tri = 2.0 * min(28.0, max(12.0, half * 0.72))
        wall_end_md = end
        sample_mds = np.linspace(start, wall_end_md, max(12, int(abs(y_md(wall_end_md)-y_md(start))/8)))
        dash = ' stroke-dasharray="7 4"' if "Liner" in stype else ""
        if stype == "Blank + Pre-Perforated Liner":
            perf_md = min(max(float(sec.get("perf_tol_md", start)), start), end)
            segments = [(start, perf_md, ""), (perf_md, end, ' stroke-dasharray="7 4"')]
        else:
            segments = [(start, end, dash)]
        for seg_start, seg_end, seg_dash in segments:
            if seg_end <= seg_start: continue
            seg_end_for_wall = min(seg_end, wall_end_md)
            if seg_end_for_wall <= seg_start: continue
            for side in (-1, 1):
                side_start = seg_start
                side_end = seg_end_for_wall
                # Side-specific top/shoe positions come from the local trajectory
                # normal in offset_point(), not from a fixed MD shift.
                seg_mds = np.linspace(side_start, side_end, max(2, int(abs(y_md(side_end)-y_md(side_start))/8)))
                pts = [offset_point(m, half, side) for m in seg_mds]
                parts.append(f'<path d="{svg_path(pts)}" fill="none" stroke="#111" stroke-width="2.5"{seg_dash}/>')
        # Outward-facing triangular shoe symbols; no horizontal line crosses
        # the tubular ID at the shoe depth.
        # Shoe markers are built from the local trajectory normal. Thus the
        # two sides follow the actual projected path orientation instead of a
        # fixed left/right vertical offset.
        left_tip = offset_point(end, half, -1)
        right_tip = offset_point(end, half, 1)
        nx, ny = normal_vector(end)
        txv, tyv = ny, -nx  # local tangent direction in the drawing plane
        shoe_half_width = tri * 0.25  # 50% of the previous full width
        shoe_height = tri * 0.35      # 200% of the previous tangent depth
        for side, tip in ((-1, left_tip), (1, right_tip)):
            px, py = tip
            outer_x, outer_y = px + side*shoe_half_width*nx, py + side*shoe_half_width*ny
            back_x, back_y = px - shoe_height*txv, py - shoe_height*tyv
            shoe_color = SECTION_COLORS[sec_index % len(SECTION_COLORS)]
            parts.append(f'<polygon points="{px:.1f},{py:.1f} {outer_x:.1f},{outer_y:.1f} {back_x:.1f},{back_y:.1f}" fill="{shoe_color}" stroke="{shoe_color}" stroke-width="0.7"/>')

    # No red centerline: actual trajectory is represented by the geometry of the hole/tubular path.
    # No horizontal line across the top ID of Section 1; tubular walls define the opening.

    # Well annotations occupy the column immediately to the right of the well.
    # Their leader lines begin at the actual trajectory centerline at each MD
    # and run directly to the annotation column; Section Details are after it.
    ann_x = LAYOUT["ANNOTATION_X"]
    ruler_ann_x = 215
    for ann in annotations:
        md = float(ann.get("depth_md", 0.0))
        if md < float(tr.MD_m.min()) or md > float(tr.MD_m.max()): continue
        yy = y_md(md)
        well_marker_x = x_center(md)
        raw_text = str(ann.get("text", "")).strip()
        text = escape(raw_text)
        if raw_text.upper() == "KOP":
            parts.append(f'<line x1="{well_marker_x:.1f}" y1="{yy:.1f}" x2="{ann_x-10}" y2="{yy:.1f}" stroke="#64748b" stroke-width="1.5"/>')
            parts.append(f'<circle cx="{well_marker_x}" cy="{yy:.1f}" r="3.2" fill="#334155"/>')
            parts.append(f'<text x="{ann_x}" y="{yy-4:.1f}" class="ann">KOP @ {md:,.0f} mMD</text>')
        elif raw_text.upper() == "EOB":
            inc_value = _interp(tr, md, "Inclination_deg")
            azi_value = _interp(tr, md, "Azimuth_deg")
            parts.append(f'<line x1="{well_marker_x:.1f}" y1="{yy:.1f}" x2="{ann_x-10}" y2="{yy:.1f}" stroke="#64748b" stroke-width="1.5"/>')
            parts.append(f'<circle cx="{well_marker_x}" cy="{yy:.1f}" r="3.2" fill="#334155"/>')
            eob_text = f'EOB @ {md:,.0f} mMD, Inc {inc_value:g}°, Azi {azi_value:g}°'
            eob_words, eob_lines, eob_current = eob_text.split(), [], ''
            for word in eob_words:
                candidate = (eob_current + ' ' + word).strip()
                if len(candidate) > max(18, int((LAYOUT["ANNOTATION_WIDTH"] - 20) / 9.2)) and eob_current:
                    eob_lines.append(eob_current); eob_current = word
                else:
                    eob_current = candidate
            if eob_current: eob_lines.append(eob_current)
            eob_line_h = LAYOUT["ANNOTATION_LINE_HEIGHT"]
            eob_first_y = yy - 4
            for li, line in enumerate(eob_lines):
                parts.append(f'<text x="{ann_x}" y="{eob_first_y+li*eob_line_h:.1f}" class="ann">{escape(line)}</text>')
        elif raw_text.lower().startswith("inclination "):
            continue
        else:
            parts.append(f'<line x1="{well_marker_x:.1f}" y1="{yy:.1f}" x2="{ann_x-10}" y2="{yy:.1f}" stroke="#64748b" stroke-width="1.5"/>')
            parts.append(f'<circle cx="{well_marker_x}" cy="{yy:.1f}" r="3.2" fill="#334155"/>')
            full_text = f'{raw_text} @ {md:,.0f} mMD'
            max_chars = max(18, int((LAYOUT["ANNOTATION_WIDTH"] - 20) / 9.2))
            words = full_text.split()
            wrapped, current = [], ''
            for word in words:
                candidate = (current + ' ' + word).strip()
                if len(candidate) > max_chars and current:
                    wrapped.append(current); current = word
                else: current = candidate
            if current: wrapped.append(current)
            # Bottom-align the annotation block with the actual depth marker.
            line_h = LAYOUT["ANNOTATION_LINE_HEIGHT"]
            first_y = yy + 4 - line_h * (len(wrapped)-1)
            for li, line in enumerate(wrapped):
                parts.append(f'<text x="{ann_x}" y="{first_y+li*line_h:.1f}" class="ann">{escape(line)}</text>')

    # Compact legend clarifies the visual conventions without competing with the well.
    parts.append('<g id="schematicLegend">')
    parts.append('<text x="20" y="1320" class="legend" font-weight="700">Legend</text>')
    parts.append('<line x1="95" y1="1315" x2="130" y2="1315" stroke="#111" stroke-width="3"/><text x="138" y="1320" class="legend">Blank tubular</text>')
    parts.append('<line x1="285" y1="1315" x2="320" y2="1315" stroke="#111" stroke-width="3" stroke-dasharray="7 4"/><text x="328" y="1320" class="legend">Pre-perforated tubular</text>')
    parts.append('<path d="M 520 1315 l 5 -4 l 5 8 l 5 -8 l 5 8 l 5 -4" fill="none" stroke="#30343b" stroke-width="1.8"/><text x="555" y="1320" class="legend">Hole</text>')
    parts.append('<rect x="640" y="1308" width="28" height="13" fill="#d8dadd" stroke="#aeb4bc" stroke-width=".6"/><text x="676" y="1320" class="legend">Cemented annulus</text>')
    parts.append('<text x="895" y="1320" class="legend" font-weight="700">L</text><text x="914" y="1320" class="legend">Top of receptacle of tie-back system</text>')
    parts.append('</g>')
    parts.append('</g>')
    parts.append('''<g id="zoomControls" font-family="Arial,Helvetica,sans-serif" font-size="19" cursor="pointer">
      <rect x="1280" y="45" width="34" height="34" rx="5" fill="#f1f5f9" stroke="#64748b"/><text x="1297" y="68" text-anchor="middle">+</text>
      <rect x="1318" y="45" width="34" height="34" rx="5" fill="#f1f5f9" stroke="#64748b"/><text x="1335" y="68" text-anchor="middle">−</text>
      <rect x="1356" y="45" width="34" height="34" rx="5" fill="#f1f5f9" stroke="#64748b"/><text x="1373" y="68" text-anchor="middle">↔</text>
    </g>
    <script><![CDATA[
    (function(){
      const svg=document.currentScript.ownerSVGElement, g=svg.getElementById('schematicContent'), controls=svg.getElementById('zoomControls'); const W=__CANVAS_W__, H=__CANVAS_H__;
      let scale=1, tx=0, ty=0, dragging=false, sx=0, sy=0, ox=0, oy=0;
      function apply(){g.setAttribute('transform','translate('+tx+' '+ty+') scale('+scale+')');}
      function zoom(f,cx=600,cy=700){const old=scale;scale=Math.max(0.5,Math.min(5,scale*f));tx=cx-(cx-tx)*(scale/old);ty=cy-(cy-ty)*(scale/old);apply();}
      svg.addEventListener('wheel',e=>{e.preventDefault();const p=svg.createSVGPoint();p.x=e.clientX;p.y=e.clientY;const q=p.matrixTransform(svg.getScreenCTM().inverse());zoom(e.deltaY<0?1.12:0.89,q.x,q.y);},{passive:false});
      controls.addEventListener('click',e=>{const target=e.target.closest('g#zoomControls');if(!target)return;const box=e.target.closest('rect');const t=(e.target.textContent||'').trim();const x=box?Number(box.getAttribute('x')):0;if(t==='+'||x===1080)zoom(1.25);else if(t==='−'||x===1118)zoom(0.8);else{scale=1;tx=0;ty=0;apply();}});
      svg.style.touchAction='none'; svg.style.cursor='grab'; svg.style.userSelect='none'; svg.style.webkitUserSelect='none';
      svg.addEventListener('pointerdown',e=>{
        if(e.target.closest('#zoomControls')) return;
        e.preventDefault(); dragging=true; sx=e.clientX; sy=e.clientY; ox=tx; oy=ty;
        try { svg.setPointerCapture(e.pointerId); } catch(err) {}
        svg.style.cursor='grabbing';
      });
      svg.addEventListener('pointermove',e=>{
        if(!dragging) return; e.preventDefault();
        const r=svg.getBoundingClientRect();
        tx=ox+(e.clientX-sx)*W/Math.max(r.width,1)/scale;
        ty=oy+(e.clientY-sy)*H/Math.max(r.height,1)/scale;
        apply();
      });
      const stopDrag=()=>{dragging=false;svg.style.cursor='grab';};
      svg.addEventListener('pointerup',stopDrag); svg.addEventListener('pointercancel',stopDrag); svg.addEventListener('lostpointercapture',stopDrag);
    })();
    ]]></script>''')
    parts.append('</svg>')
    return "".join(parts).replace("__CANVAS_W__", str(W)).replace("__CANVAS_H__", str(H))
