from pathlib import Path
from io import BytesIO
import base64
import re
import zipfile
import math
import pandas as pd
import numpy as np
import streamlit as st
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from schematic import generate_jtype_survey, minimum_curvature_survey, validate_survey, build_well_schematic_svg, _format_inches

BASE_DIR = Path(__file__).resolve().parent
LOGO_PATH = BASE_DIR / "RIGSIS Logo.png"


def clean_svg_for_export(svg: str) -> str:
    """Remove interactive zoom/pan controls and script from exported artwork."""
    svg = re.sub(r'<g\s+id=["\']zoomControls["\'][^>]*>.*?</g>', '', svg, flags=re.S | re.I)
    svg = re.sub(r'<script\b[^>]*>.*?</script\s*>', '', svg, flags=re.S | re.I)
    return svg
st.set_page_config(page_title="RIGSIS Well Schematic", page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else "🛢️", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: .8rem; padding-bottom: 1rem;}
.st-key-input_panel {height: 900px; max-height: 900px; overflow-y: auto; padding-right: 1rem;}
.st-key-preview_panel {position: sticky; top: .5rem;}
.st-key-preview_panel iframe {border: 1px solid #e5e7eb; border-radius: 8px;}
div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"] {scroll-margin-top: 1rem;}
.section-card {padding: .45rem .65rem; border: 1px solid #e2e8f0; border-radius: 8px; margin-bottom: .35rem;}
</style>
""", unsafe_allow_html=True)

h1, h2 = st.columns([1, 6], vertical_alignment="center")
with h1:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), width=100)
with h2:
    st.title("RIGSIS Well Schematic")
    st.caption("Survey-based trajectory • Flexible section builder • SVG preview")

CASING_DATABASE = {
    "30 in × 156.50 ppf | ID 29.000 in": (30.000, 156.50, 29.000, "X-56"),
    "20 in × 94.00 ppf | ID 18.730 in": (20.000, 94.00, 18.730, "K-55"),
    "20 in × 106.00 ppf | ID 18.560 in": (20.000, 106.00, 18.560, "K-55"),
    "20 in × 133.00 ppf | ID 18.376 in": (20.000, 133.00, 18.376, "K-55"),
    "13-3/8 in × 54.50 ppf | ID 12.615 in": (13.375, 54.50, 12.615, "K-55"),
    "13-3/8 in × 61.00 ppf | ID 12.515 in": (13.375, 61.00, 12.515, "K-55"),
    "13-3/8 in × 68.00 ppf | ID 12.415 in": (13.375, 68.00, 12.415, "K-55"),
    "13-3/8 in × 72.00 ppf | ID 12.347 in": (13.375, 72.00, 12.347, "K-55"),
    "10-3/4 in × 40.50 ppf | ID 10.050 in": (10.750, 40.50, 10.050, "K-55"),
    "10-3/4 in × 51.00 ppf | ID 9.850 in": (10.750, 51.00, 9.850, "K-55"),
    "8-5/8 in × 24.00 ppf | ID 8.097 in": (8.625, 24.00, 8.097, "K-55"),
    "8-5/8 in × 32.00 ppf | ID 7.921 in": (8.625, 32.00, 7.921, "K-55"),
    "8-5/8 in × 36.00 ppf | ID 7.825 in": (8.625, 36.00, 7.825, "K-55"),
    "7 in × 20.00 ppf | ID 6.456 in": (7.000, 20.00, 6.456, "K-55"),
    "7 in × 23.00 ppf | ID 6.366 in": (7.000, 23.00, 6.366, "K-55"),
    "7 in × 26.00 ppf | ID 6.276 in": (7.000, 26.00, 6.276, "K-55"),
    "7 in × 29.00 ppf | ID 6.184 in": (7.000, 29.00, 6.184, "K-55"),
    "7 in × 32.00 ppf | ID 6.094 in": (7.000, 32.00, 6.094, "K-55"),
    "9-5/8 in × 36.00 ppf | ID 8.921 in": (9.625, 36.00, 8.921, "K-55"),
    "9-5/8 in × 40.00 ppf | ID 8.835 in": (9.625, 40.00, 8.835, "K-55"),
    "9-5/8 in × 47.00 ppf | ID 8.681 in": (9.625, 47.00, 8.681, "K-55"),
}

CASING_DRIFT_DATABASE = {
    "30 in × 156.50 ppf | ID 29.000 in": 29.000,
    "20 in × 94.00 ppf | ID 18.730 in": 18.936,
    "20 in × 106.00 ppf | ID 18.560 in": 18.812,
    "20 in × 133.00 ppf | ID 18.376 in": 18.542,
    "13-3/8 in × 54.50 ppf | ID 12.615 in": 12.459,
    "13-3/8 in × 61.00 ppf | ID 12.515 in": 12.359,
    "13-3/8 in × 68.00 ppf | ID 12.415 in": 12.259,
    "13-3/8 in × 72.00 ppf | ID 12.347 in": 12.191,
    "10-3/4 in × 40.50 ppf | ID 10.050 in": 9.894,
    "10-3/4 in × 51.00 ppf | ID 9.850 in": 9.694,
    "8-5/8 in × 24.00 ppf | ID 8.097 in": 7.972,
    "8-5/8 in × 32.00 ppf | ID 7.921 in": 7.796,
    "8-5/8 in × 36.00 ppf | ID 7.825 in": 7.700,
    "7 in × 20.00 ppf | ID 6.456 in": 6.331,
    "7 in × 23.00 ppf | ID 6.366 in": 6.241,
    "7 in × 26.00 ppf | ID 6.276 in": 6.151,
    "7 in × 29.00 ppf | ID 6.184 in": 6.059,
    "7 in × 32.00 ppf | ID 6.094 in": 5.969,
    "9-5/8 in × 36.00 ppf | ID 8.921 in": 8.765,
    "9-5/8 in × 40.00 ppf | ID 8.835 in": 8.679,
    "9-5/8 in × 47.00 ppf | ID 8.681 in": 8.525,
}
HOLE_DIAMETERS = [36.0, 26.0, 17.5, 12.25, 9.875, 8.5, 7.875, 6.5]
SECTION_TYPES = [
    "Cemented Casing", "Cemented Liner", "Tie-Back Casing", "Blank Casing",
    "Blank Liner", "Pre-Perforated Liner", "Blank + Pre-Perforated Liner", "Open Hole",
]
LINER_TYPES = {"Cemented Liner", "Blank Liner", "Pre-Perforated Liner", "Blank + Pre-Perforated Liner"}
CASING_TYPES = {"Cemented Casing", "Tie-Back Casing", "Blank Casing"}
CEMENTED_TYPES = {"Cemented Casing", "Cemented Liner", "Tie-Back Casing"}


def _clean_cell(v, default=None):
    return default if pd.isna(v) else v

def _match_catalog(od, weight):
    candidates = []
    for label, (c_od, c_wt, c_id, c_grade) in CASING_DATABASE.items():
        score = abs(float(od)-c_od)*100 + abs(float(weight)-c_wt)
        candidates.append((score, label))
    return min(candidates)[1] if candidates else list(CASING_DATABASE)[0]

def _validate_and_render_workbook(file_bytes):
    """Parse one worksheet per well using the Multiwell Excel Template v1 layout."""
    import resvg_py
    from zipfile import ZIP_DEFLATED
    xl = pd.ExcelFile(BytesIO(file_bytes))
    output = BytesIO()
    report = []
    png_count = 0
    with zipfile.ZipFile(output, 'w', ZIP_DEFLATED) as zf:
        for sheet in xl.sheet_names:
            if sheet.strip().lower() in {'instructions', '_lists', 'casing catalog'}:
                continue
            errors = []
            try:
                raw = pd.read_excel(BytesIO(file_bytes), sheet_name=sheet, header=None)
                well_name = str(_clean_cell(raw.iat[2,1], sheet)).strip()
                if not well_name or well_name.lower() == 'nan': well_name = sheet
                mode = str(_clean_cell(raw.iat[2,4], 'CALCULATE')).strip().upper()
                td = float(_clean_cell(raw.iat[2,7], 3000))
                kop = float(_clean_cell(raw.iat[3,1], 400))
                eob = float(_clean_cell(raw.iat[3,3], 700))
                inc = float(_clean_cell(raw.iat[3,5], 30))
                azi = float(_clean_cell(raw.iat[3,7], 250))
                if mode == 'SURVEY':
                    survey = pd.read_excel(BytesIO(file_bytes), sheet_name=sheet, header=35, usecols='A:C')
                    survey.columns = ['MD_m','Inclination_deg','Azimuth_deg']
                    survey = survey.dropna(how='all').dropna(subset=['MD_m'])
                    survey = survey.astype(float)
                    errors.extend(validate_survey(survey, td))
                    if not errors:
                        if float(survey.MD_m.max()) > td:
                            orig=survey.copy(); survey=orig[orig.MD_m<td].copy(); row={'MD_m':td}
                            for c in ['Inclination_deg','Azimuth_deg']: row[c]=float(np.interp(td,orig.MD_m,orig[c]))
                            survey=pd.concat([survey,pd.DataFrame([row])],ignore_index=True)
                        trajectory=minimum_curvature_survey(survey)
                elif mode == 'CALCULATE':
                    if not (0 <= kop < eob <= td): errors.append('Require 0 ≤ KOP < EOB ≤ TD.')
                    if not (0 <= inc <= 90): errors.append('Final inclination must be 0–90 degrees.')
                    if not (0 <= azi <= 360): errors.append('Build azimuth must be 0–360 degrees.')
                    if not errors:
                        survey=generate_jtype_survey(td,kop,eob,inc,azi,30.0)
                        trajectory=minimum_curvature_survey(survey)
                else:
                    errors.append(f'Unknown Trajectory Mode: {mode}. Use CALCULATE or SURVEY.')
                sections=[]
                prev_end=0.0
                if not errors:
                    for r in range(8,18):
                        name=_clean_cell(raw.iat[r,0]); stype=_clean_cell(raw.iat[r,1])
                        if name is None and stype is None: continue
                        name=str(name if name is not None else f'Section {len(sections)+1}').strip()
                        stype=str(stype or '').strip()
                        if stype not in SECTION_TYPES:
                            errors.append(f'{name}: invalid section type "{stype}".'); continue
                        try:
                            hole=float(raw.iat[r,2]); end=float(raw.iat[r,7])
                        except (TypeError,ValueError):
                            errors.append(f'{name}: Hole Dia and End Depth must be numeric.'); continue
                        if end <= prev_end or end > td:
                            errors.append(f'{name}: End Depth must increase and not exceed TD.'); continue
                        connection=str(_clean_cell(raw.iat[r,6], '') or '').strip()
                        tol=float(_clean_cell(raw.iat[r,8],0) or 0)
                        tieback=float(_clean_cell(raw.iat[r,9],0) or 0)
                        perf=_clean_cell(raw.iat[r,10],None)
                        perf=float(perf) if perf is not None else None
                        tubular=None; spec=None
                        if stype != 'Open Hole':
                            try: od=float(raw.iat[r,3]); weight=float(raw.iat[r,4])
                            except (TypeError,ValueError):
                                errors.append(f'{name}: Casing/Liner OD and Weight are required.'); continue
                            grade=str(_clean_cell(raw.iat[r,5],'K-55'))
                            spec=_match_catalog(od,weight)
                            c_od,c_wt,c_id,_=CASING_DATABASE[spec]
                            tubular=(c_od,c_wt,c_id,grade,CASING_DRIFT_DATABASE[spec])
                        is_liner=stype in LINER_TYPES
                        start=max(0.0,prev_end-tol) if is_liner else (0.0 if stype in CASING_TYPES else prev_end)
                        if stype=='Open Hole': start=prev_end
                        if end <= start: errors.append(f'{name}: End Depth must be deeper than start/TOL.'); continue
                        if stype=='Tie-Back Casing' and not 0 <= tieback <= end: errors.append(f'{name}: Tie-back Depth must be between 0 and End Depth.')
                        if is_liner and not 0 <= tol <= 60: errors.append(f'{name}: TOL Overlap must be 0–60 m.')
                        sections.append({'name':name,'type':stype,'start_md':start,'end_md':end,'hole_diameter':hole,'tubular':tubular,'casing_connection':connection,'tieback_md':tieback,'blank_tol_md':tol if stype=='Blank + Pre-Perforated Liner' else None,'perf_tol_md':perf,'half_width':5 if stype=='Open Hole' else max(7,min(20,float(tubular[0])*0.65))})
                        prev_end=end
                anns=[]
                for r in range(22,32):
                    txt=_clean_cell(raw.iat[r,0]); depth=_clean_cell(raw.iat[r,1])
                    if txt is None or not str(txt).strip(): continue
                    try: depth=float(depth)
                    except (TypeError,ValueError): errors.append(f'Annotation row {r+1}: Depth MD is required and must be numeric.'); continue
                    if not 0 <= depth <= td: errors.append(f'Annotation "{txt}": depth must be within 0–TD.')
                    anns.append({'text':str(txt).strip(),'depth_md':depth})
                if errors:
                    report.append({'sheet':sheet,'well':well_name,'status':'Invalid','details':' '.join(errors)})
                    continue
                if not sections: raise ValueError('No section rows found in columns A:J, rows 9–18.')
                if abs(float(sections[-1]['end_md'])-td)>1e-6: errors.append('Last section End Depth should equal TD.')
                if errors:
                    report.append({'sheet':sheet,'well':well_name,'status':'Invalid','details':' '.join(errors)}); continue
                if mode=='CALCULATE':
                    anns.extend([{'text':'KOP','depth_md':kop},{'text':f'EOB, Inc {inc:g}°, Azi {azi:g}°','depth_md':eob}])
                svg=build_well_schematic_svg(td=td,trajectory_df=trajectory,sections=sections,annotations=anns,title=well_name)
                export_svg = clean_svg_for_export(svg)
                png=resvg_py.svg_to_bytes(svg_string=export_svg, width=1400, height=1370, background='#ffffff')
                safe=re.sub(r'[^A-Za-z0-9_-]+','_',well_name).strip('_') or sheet
                fname=f'{safe}_Well_Schematic.png'
                zf.writestr(fname,png); png_count+=1
                report.append({'sheet':sheet,'well':well_name,'status':'Valid','details':f'PNG generated: {fname}'})
            except Exception as exc:
                report.append({'sheet':sheet,'well':sheet,'status':'Invalid','details':str(exc)})
    return output.getvalue(), pd.DataFrame(report), png_count



with st.expander("Multi-Well Batch Export — Excel to PNG ZIP", expanded=False):
    st.markdown("Upload workbook berdasarkan template multi-well. Setiap worksheet sumur akan divalidasi dan diekspor sebagai satu PNG.")
    template_path = BASE_DIR / "RIGSIS_Well_Schematic_Multiwell_Excel_Template_v1.xlsx"
    if template_path.exists():
        with open(template_path, "rb") as template_file:
            st.download_button(
                "⬇ Download Multi-Well Excel Template (.XLSX)",
                data=template_file.read(),
                file_name="RIGSIS_Well_Schematic_Multiwell_Excel_Template_v1.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="download_multiwell_template",
            )
    else:
        st.warning("File template multi-well tidak ditemukan di folder aplikasi.")
    batch_file = st.file_uploader("Upload multi-well Excel workbook (.xlsx)", type=["xlsx"], key="multiwell_batch_upload")
    if batch_file is not None:
        try:
            names = pd.ExcelFile(batch_file).sheet_names
            wells = [n for n in names if n.strip().lower() not in {"instructions", "_lists"}]
            st.write(f"**Worksheet terdeteksi: {len(wells)} sumur**")
            st.dataframe(pd.DataFrame({"Worksheet": wells}), use_container_width=True, hide_index=True)
            if st.button("Validate Workbook", key="validate_batch", use_container_width=True):
                _, batch_report, _ = _validate_and_render_workbook(batch_file.getvalue())
                st.session_state["batch_validation_report"] = batch_report
            if "batch_validation_report" in st.session_state:
                st.dataframe(st.session_state["batch_validation_report"], use_container_width=True, hide_index=True)
            if st.button("Generate All PNGs and Download ZIP", type="primary", key="generate_batch_zip", use_container_width=True):
                with st.spinner("Validating wells and generating PNG files…"):
                    zip_bytes, batch_report, count = _validate_and_render_workbook(batch_file.getvalue())
                st.session_state["batch_validation_report"] = batch_report
                if count and (batch_report["status"] == "Invalid").sum() == 0:
                    st.success(f"Berhasil membuat {count} PNG schematic.")
                    st.download_button("Download All Well Schematics (.ZIP)", data=zip_bytes, file_name="RIGSIS_Well_Schematic_Export.zip", mime="application/zip", use_container_width=True, key="download_batch_zip")
                else:
                    st.error(f"Batch belum lengkap: {count} PNG berhasil, {(batch_report['status'] == 'Invalid').sum()} worksheet perlu diperbaiki. Tidak ada ZIP final yang ditawarkan agar tidak ada sumur yang terlewat.")
                    st.dataframe(batch_report, use_container_width=True, hide_index=True)
        except Exception as exc:
            st.error(f"Workbook tidak dapat dibaca: {exc}")


def make_excel_template():
    wb = Workbook()
    ws = wb.active
    ws.title = "Survey"
    ws.append(["MD_m", "Inclination_deg", "Azimuth_deg"])
    for row in [[0, 0, 0], [400, 0, 0], [500, 10, 0], [600, 20, 0], [700, 30, 0], [1000, 30, 0], [1500, 30, 0], [2000, 30, 0], [2500, 30, 0]]:
        ws.append(row)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="243B83")
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()

def normalize_survey_columns(df):
    rename = {}
    for c in df.columns:
        k = str(c).strip().lower().replace(" ", "").replace("(", "").replace(")", "").replace("°", "")
        if k in {"md", "mdm", "measureddepth", "md_m"}: rename[c] = "MD_m"
        elif k in {"inclination", "inc", "incdeg", "inclinationdeg", "inclination_deg"}: rename[c] = "Inclination_deg"
        elif k in {"azimuth", "azi", "azideg", "azimuthdeg", "azimuth_deg"}: rename[c] = "Azimuth_deg"
    return df.rename(columns=rename)

def default_sections():
    return [
        {"name": "Conductor Casing", "type": "Cemented Casing", "hole": 36.0, "spec": "30 in × 156.50 ppf | ID 29.000 in", "grade": "X-56", "connection": "ERW", "end": 60.0, "tol": 0.0, "tieback": 0.0, "blank_tol": 0.0, "perf_tol": 0.0},
        {"name": "Surface Casing", "type": "Cemented Casing", "hole": 26.0, "spec": "20 in × 133.00 ppf | ID 18.376 in", "grade": "K-55", "connection": "GeoConn", "end": 500.0, "tol": 0.0, "tieback": 0.0, "blank_tol": 0.0, "perf_tol": 0.0},
        {"name": "Production Casing", "type": "Tie-Back Casing", "hole": 17.5, "spec": "13-3/8 in × 72.00 ppf | ID 12.191 in", "grade": "L-80", "connection": "VAM-TOP", "end": 1300.0, "tol": 0.0, "tieback": 450.0, "blank_tol": 0.0, "perf_tol": 0.0},
        {"name": "Liner 1", "type": "Blank + Pre-Perforated Liner", "hole": 12.25, "spec": "10-3/4 in × 40.50 ppf | ID 9.950 in", "grade": "K-55", "connection": "DWC/C-IS", "end": 2100.0, "tol": 30.0, "tieback": 0.0, "blank_tol": 0.0, "perf_tol": 1400.0},
        {"name": "Liner 2", "type": "Pre-Perforated Liner", "hole": 9.875, "spec": "8-5/8 in × 24.00 ppf | ID 7.921 in", "grade": "K-55", "connection": "DWC/C-IS", "end": 3000.0, "tol": 30.0, "tieback": 0.0, "blank_tol": 0.0, "perf_tol": 0.0},
    ]

if "sections_data" not in st.session_state:
    st.session_state.sections_data = default_sections()
if "active_section" not in st.session_state:
    st.session_state.active_section = 0
if "extra_annotations" not in st.session_state:
    st.session_state.extra_annotations = pd.DataFrame([{"Annotation": "", "Depth_MD_m": 0.0}])

# Header outside the scrollable panels. Inputs scroll independently; preview stays beside them.
input_col, preview_col = st.columns([60, 40], gap="large")
with input_col:
    with st.container(key="input_panel"):
        st.subheader("1. Well Trajectory")
        well_name = st.text_input("Well Name", "WP-01")
        trajectory_mode = st.radio(
            "Trajectory input method",
            ["Calculate from TD / KOP / EOB / Inclination", "Upload Excel survey"],
            key="trajectory_mode",
        )
        td = st.number_input("Total Depth — TD (mMD)", min_value=100.0, max_value=15000.0, value=3000.0, step=50.0, key="td")
        azimuth = 250.0
        kop = min(400.0, td * 0.2)
        eob = min(700.0, td * 0.4)
        final_inc = 30.0
        annotations = []

        if trajectory_mode == "Calculate from TD / KOP / EOB / Inclination":
            a, b = st.columns(2)
            with a:
                kop = st.number_input("KOP (mMD)", min_value=0.0, max_value=float(td), value=min(400.0, td * 0.2), step=25.0, key="calc_kop")
                final_inc = st.number_input("Final Inclination (°)", min_value=0.0, max_value=90.0, value=30.0, step=0.5, key="calc_inc")
            with b:
                eob = st.number_input("EOB (mMD)", min_value=0.0, max_value=float(td), value=min(700.0, td * 0.4), step=25.0, key="calc_eob")
                azimuth = st.number_input("Build Azimuth (°)", min_value=0.0, max_value=360.0, value=250.0, step=5.0, key="calc_azimuth")
            try:
                survey_df = generate_jtype_survey(td, kop, eob, final_inc, azimuth, 30.0)
            except Exception as exc:
                st.error(str(exc))
                st.stop()
            annotations.extend([
                {"text": "KOP", "depth_md": float(kop)},
                {"text": "EOB", "depth_md": float(eob)},
                {"text": f"Inclination {final_inc:g}°", "depth_md": float(eob)},
            ])
        else:
            st.download_button(
                "⬇ Download Excel Survey Template",
                data=make_excel_template(),
                file_name="RIGSIS_Well_Schematic_Survey_Template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
            upload = st.file_uploader("Upload Excel survey (.xlsx)", type=["xlsx"], key="survey_upload")
            if upload is None:
                st.info("Upload the Survey workbook to build the trajectory. You can download the template above.")
                survey_df = None
            else:
                try:
                    survey_df = normalize_survey_columns(pd.read_excel(upload, sheet_name="Survey"))
                    survey_df = survey_df[["MD_m", "Inclination_deg", "Azimuth_deg"]].copy()
                except Exception as exc:
                    st.error(f"Could not read Survey sheet: {exc}")
                    survey_df = None
            ac1, ac2, ac3 = st.columns(3)
            with ac1:
                kop = st.number_input("KOP annotation (mMD)", min_value=0.0, max_value=float(td), value=min(400.0, td), step=25.0, key="upload_kop")
            with ac2:
                eob = st.number_input("EOB annotation (mMD)", min_value=0.0, max_value=float(td), value=min(700.0, td), step=25.0, key="upload_eob")
            with ac3:
                final_inc = st.number_input("Inclination annotation (°)", min_value=0.0, max_value=180.0, value=30.0, step=0.5, key="upload_inc")
            annotations.extend([
                {"text": "KOP", "depth_md": float(kop)},
                {"text": "EOB", "depth_md": float(eob)},
                {"text": f"Inclination {final_inc:g}°", "depth_md": float(eob)},
            ])

        st.subheader("2. Section Details")
        st.caption("Add sections in sequence. Each section ends at its specified depth; liner TOL can overlap the preceding section.")
        section_inputs = []
        for idx, sec0 in enumerate(st.session_state.sections_data):
            with st.expander(f"Section {idx+1}: {sec0.get('name', 'Section')}", expanded=(idx == st.session_state.active_section)):
                # Row 1: Section Name + Section Type
                r_name, r_type = st.columns([1.2, 1.0])
                with r_name:
                    sec_name = st.text_input("Section Name", value=sec0["name"], key=f"sec_name_{idx}")
                with r_type:
                    sec_type = st.selectbox("Section Type", SECTION_TYPES, index=SECTION_TYPES.index(sec0["type"]), key=f"sec_type_{idx}", on_change=lambda i=idx: st.session_state.update(active_section=i))

                # Row 2: Hole Dia + Casing Catalog + Casing Grade + End Depth
                r_hole, r_catalog, r_grade, r_end = st.columns([0.8, 1.55, 0.85, 1.0])
                with r_hole:
                    hole = st.selectbox("Hole Dia (in)", HOLE_DIAMETERS, format_func=lambda v: f"{_format_inches(v)} in", index=HOLE_DIAMETERS.index(sec0["hole"]) if sec0["hole"] in HOLE_DIAMETERS else 2, key=f"sec_hole_{idx}")
                spec = sec0.get("spec", list(CASING_DATABASE)[1])
                tubular = None
                grade = sec0.get("grade", "K-55")
                with r_catalog:
                    if sec_type != "Open Hole":
                        spec = st.selectbox("Casing Catalog (OD / Weight)", list(CASING_DATABASE), index=list(CASING_DATABASE).index(spec) if spec in CASING_DATABASE else 1, key=f"sec_spec_{idx}")
                    else:
                        st.text_input("Casing Catalog", value="— Open Hole —", disabled=True, key=f"sec_catalog_display_{idx}")
                with r_grade:
                    if sec_type != "Open Hole":
                        grade_options = ["X-56"] if float(CASING_DATABASE[spec][0]) == 30.0 else ["H-40", "J-55", "K-55", "N-80", "L-80", "C-90", "T-95", "P-110", "Q-125"]
                        if grade_options == ["X-56"]:
                            grade = "X-56"
                            st.selectbox("Casing Grade", grade_options, index=0, disabled=True, key=f"sec_grade_{idx}")
                        else:
                            grade = st.selectbox("Casing Grade", grade_options, index=grade_options.index(grade) if grade in grade_options else 2, key=f"sec_grade_{idx}")
                    else:
                        st.text_input("Casing Grade", value="—", disabled=True, key=f"sec_grade_display_{idx}")
                with r_end:
                    end_depth = st.number_input("End Depth (mMD)", min_value=1.0, max_value=float(td), value=min(float(td), max(1.0, float(sec0["end"]))), step=25.0, key=f"sec_end_{idx}")
                if sec_type != "Open Hole":
                    od, weight, inner_dia, _catalog_grade = CASING_DATABASE[spec]
                    tubular = (od, weight, inner_dia, grade, CASING_DRIFT_DATABASE[spec])
                    casing_connection = st.text_input("Casing Connection", value=str(sec0.get("connection", "") or ""), placeholder="e.g. Semi Premium Connection", key=f"sec_connection_{idx}")
                else:
                    casing_connection = ""

                # Additional inputs appear only when relevant to the chosen section type.
                if sec_type in LINER_TYPES:
                    tol = st.number_input("TOL Overlap (m)", min_value=0.0, max_value=60.0, value=min(60.0, max(0.0, float(sec0.get("tol", 30.0)))), step=5.0, key=f"sec_tol_{idx}", help="Overlap into the previous casing/liner. TOL is calculated as previous shoe depth minus overlap.")
                else:
                    tol = 0.0
                if sec_type == "Tie-Back Casing":
                    tieback = st.number_input("Tie-back Depth (mMD)", min_value=0.0, max_value=float(td), value=min(float(td), float(sec0.get("tieback", 0.0) or 0.0)), step=25.0, key=f"sec_tieback_{idx}")
                else:
                    tieback = 0.0
                if sec_type == "Blank + Pre-Perforated Liner":
                    perf_tol = st.number_input("TOL Pre-Perforated (mMD)", min_value=0.0, max_value=float(end_depth), value=min(float(end_depth), max(0.0, float(sec0.get("perf_tol", 0.0)))), step=10.0, key=f"sec_perf_tol_{idx}")
                    blank_tol = tol  # TOL Overlap is also the blank-liner overlap for this combined type.
                elif sec_type == "Pre-Perforated Liner":
                    # The entire liner is pre-perforated; no separate TOL input is needed.
                    perf_tol = None
                    blank_tol = None
                else:
                    blank_tol = perf_tol = None
                rm1, rm2 = st.columns([1, 3])
                with rm1:
                    if st.button("Remove section", key=f"remove_section_{idx}", disabled=len(st.session_state.sections_data) <= 1):
                        st.session_state.sections_data.pop(idx)
                        st.session_state.active_section = max(0, min(idx, len(st.session_state.sections_data)-1))
                        # Re-index widget keys on the next rerun by clearing section widget state.
                        for key in list(st.session_state.keys()):
                            if key.startswith(("sec_name_", "sec_type_", "sec_hole_", "sec_end_", "sec_tol_", "sec_tieback_", "sec_spec_", "sec_grade_", "sec_blank_tol_", "sec_perf_tol_")):
                                del st.session_state[key]
                        st.rerun()
                # Persist current inputs in the model before section-list mutations.
                st.session_state.sections_data[idx] = {
                    "name": sec_name.strip() or f"Section {idx+1}", "type": sec_type,
                    "hole": float(hole), "spec": spec, "grade": grade, "connection": casing_connection, "end": float(end_depth),
                    "tol": float(tol), "tieback": float(tieback),
                    "blank_tol": float(blank_tol) if blank_tol is not None else 0.0,
                    "perf_tol": float(perf_tol) if perf_tol is not None else 0.0,
                }
                section_inputs.append({
                    "name": sec_name.strip() or f"Section {idx+1}", "type": sec_type,
                    "hole_diameter": float(hole), "spec": spec, "tubular": tubular, "casing_connection": casing_connection,
                    "end_md": float(end_depth), "tol_md": float(tol), "tieback_md": float(tieback),
                    "blank_tol_md": blank_tol, "perf_tol_md": perf_tol,
                })

        # Button below the last section; edited values above are already saved to session_state.
        if st.button("＋ Add Section", type="primary", use_container_width=True, key="add_section"):
            last_end = float(st.session_state.sections_data[-1]["end"]) if st.session_state.sections_data else 0.0
            new_idx = len(st.session_state.sections_data) + 1
            st.session_state.sections_data.append({
                "name": f"Section {new_idx}", "type": "Open Hole", "hole": 12.25,
                "spec": list(CASING_DATABASE)[8], "connection": "", "end": min(float(td), max(last_end + 500.0, last_end + 1.0)),
                "tol": 30.0, "tieback": 0.0, "blank_tol": 0.0, "perf_tol": 0.0,
            })
            st.session_state.active_section = len(st.session_state.sections_data) - 1
            st.rerun()

        st.subheader("3. Additional Annotation")
        st.caption("KOP/EOB/inclination are annotations only in uploaded-survey mode. Add any other annotation below.")
        # Use stable keyed inputs instead of st.data_editor here. This avoids
        # Streamlit's editor draft state reverting a depth when focus changes.
        extra = st.session_state.extra_annotations.copy().reset_index(drop=True)
        updated_rows = []
        for ann_idx, row in extra.iterrows():
            ann_col, depth_col = st.columns([2.2, 1.0])
            text_key = f"extra_annotation_text_{ann_idx}"
            depth_key = f"extra_annotation_depth_{ann_idx}"
            if text_key not in st.session_state:
                st.session_state[text_key] = str(row.get("Annotation", "") or "")
            if depth_key not in st.session_state:
                try:
                    st.session_state[depth_key] = float(row.get("Depth_MD_m", 0.0) or 0.0)
                except (TypeError, ValueError):
                    st.session_state[depth_key] = 0.0
            ann_text = ann_col.text_input("Annotation", key=text_key, label_visibility="visible")
            ann_depth = depth_col.number_input("Depth MD (m)", min_value=0.0, max_value=float(td), step=10.0, key=depth_key)
            updated_rows.append({"Annotation": ann_text, "Depth_MD_m": float(ann_depth)})
        st.session_state.extra_annotations = pd.DataFrame(updated_rows, columns=["Annotation", "Depth_MD_m"])
        if st.button("＋ Add Annotation", key="add_annotation"):
            new_idx = len(st.session_state.extra_annotations)
            st.session_state.extra_annotations = pd.concat([
                st.session_state.extra_annotations,
                pd.DataFrame([{"Annotation": "", "Depth_MD_m": 0.0}])
            ], ignore_index=True)
            st.session_state[f"extra_annotation_text_{new_idx}"] = ""
            st.session_state[f"extra_annotation_depth_{new_idx}"] = 0.0
            st.rerun()
        for _, row in st.session_state.extra_annotations.iterrows():
            if pd.notna(row.get("Annotation")) and str(row["Annotation"]).strip() and pd.notna(row.get("Depth_MD_m")):
                annotations.append({"text": str(row["Annotation"]).strip(), "depth_md": float(row["Depth_MD_m"])})

with preview_col:
    with st.container(key="preview_panel"):
        st.subheader("Well Schematic Preview")
        st.caption("Preview stays alongside the input panel. Scroll the input panel on the left.")
        if "survey_df" not in locals() or survey_df is None:
            st.info("Upload a survey workbook in the input panel to display the schematic.")
        else:
            survey_errors = validate_survey(survey_df, td)
            if survey_errors:
                for err in survey_errors:
                    st.error(err)
            else:
                survey_df = survey_df.astype(float).sort_values("MD_m").reset_index(drop=True)
                # Interpolate at TD if there is a station beyond TD.
                if float(survey_df.MD_m.max()) > td:
                    original = survey_df.copy()
                    survey_df = original[original.MD_m < td].copy()
                    tdrow = {"MD_m": float(td)}
                    for col in ["Inclination_deg", "Azimuth_deg"]:
                        tdrow[col] = float(np.interp(td, original.MD_m, original[col]))
                    survey_df = pd.concat([survey_df, pd.DataFrame([tdrow])], ignore_index=True)
                trajectory = minimum_curvature_survey(survey_df)
                errors = []
                render_sections = []
                previous_end = 0.0
                previous_hole = None
                for i, sec in enumerate(section_inputs):
                    end_md = sec["end_md"]
                    stype = sec["type"]
                    is_liner = stype in LINER_TYPES
                    is_open = stype == "Open Hole"
                    if stype in {"Cemented Casing", "Tie-Back Casing", "Blank Casing"}:
                        start_md = 0.0
                    elif is_liner:
                        start_md = max(0.0, previous_end - float(sec["tol_md"]))
                    else:
                        start_md = previous_end
                    if is_open:
                        start_md = previous_end
                    if end_md <= start_md:
                        errors.append(f"{sec['name']}: end depth must be deeper than its start/TOL.")
                    if end_md > td:
                        errors.append(f"{sec['name']}: end depth exceeds TD.")
                    if (is_liner or stype == "Tie-Back Casing") and i > 0 and not (0.0 <= sec["tol_md"] <= 60.0):
                        errors.append(f"{sec['name']}: TOL overlap must be between 0 and 60 m.")
                    if stype == "Tie-Back Casing" and not (0 <= sec["tieback_md"] <= end_md):
                        errors.append(f"{sec['name']}: tie-back depth must be between surface and end depth.")
                    half_width = 5 if is_open else max(7, min(20, float(sec["tubular"][0]) * 0.65))
                    render_sections.append({
                        "name": sec["name"], "type": stype, "start_md": float(start_md), "end_md": float(end_md),
                        "hole_diameter": sec["hole_diameter"], "tubular": sec["tubular"],
                        "tieback_md": sec["tieback_md"], "blank_tol_md": sec["blank_tol_md"],
                        "perf_tol_md": sec["perf_tol_md"], "casing_connection": sec.get("casing_connection", ""), "half_width": half_width,
                    })
                    previous_end = end_md
                if errors:
                    for err in errors:
                        st.error(err)
                else:
                    try:
                        svg = build_well_schematic_svg(
                            td=float(td), trajectory_df=trajectory, sections=render_sections,
                            annotations=annotations, title=well_name.strip() or "Well Schematic",
                        )
                        st.components.v1.html(svg, height=620, scrolling=False)
                        # Export the exact current SVG as a high-resolution PNG in the browser.
                        # This avoids native Cairo/system dependencies on Windows.
                        # PNG export should contain only the engineering drawing,
                        # never the interactive zoom/pan controls or their script.
                        export_svg = clean_svg_for_export(svg)
                        svg_b64 = base64.b64encode(export_svg.encode("utf-8")).decode("ascii")
                        safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", (well_name.strip() or "Well_Schematic")).strip("_") or "Well_Schematic"
                        export_html = f'''
                        <div style="font-family:Arial,sans-serif; padding:4px 0 8px;">
                          <button id="exportPngBtn" style="background:#0f766e;color:white;border:0;border-radius:8px;padding:9px 14px;font-size:14px;font-weight:600;cursor:pointer;">
                            Export Schematic as PNG
                          </button>
                          <span id="exportStatus" style="margin-left:10px;color:#64748b;font-size:12px;"></span>
                        </div>
                        <script>
                        (() => {{
                          const svgBase64 = "{svg_b64}";
                          const button = document.getElementById('exportPngBtn');
                          const status = document.getElementById('exportStatus');
                          button.addEventListener('click', () => {{
                            button.disabled = true;
                            status.textContent = 'Preparing PNG at canvas size…';
                            try {{
                              const raw = atob(svgBase64);
                              const bytes = new Uint8Array(raw.length);
                              for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
                              const svgBlob = new Blob([bytes], {{type: 'image/svg+xml;charset=utf-8'}});
                              const svgUrl = URL.createObjectURL(svgBlob);
                              const img = new Image();
                              img.onload = () => {{
                                const canvas = document.createElement('canvas');
                                canvas.width = 1400;
                                canvas.height = 1370;
                                const ctx = canvas.getContext('2d');
                                ctx.fillStyle = '#ffffff';
                                ctx.fillRect(0, 0, canvas.width, canvas.height);
                                ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                                URL.revokeObjectURL(svgUrl);
                                canvas.toBlob((blob) => {{
                                  if (!blob) {{
                                    status.textContent = 'PNG export failed. Please try again.';
                                    button.disabled = false;
                                    return;
                                  }}
                                  const pngUrl = URL.createObjectURL(blob);
                                  const a = document.createElement('a');
                                  a.href = pngUrl;
                                  a.download = '{safe_name}_Well_Schematic.png';
                                  document.body.appendChild(a);
                                  a.click();
                                  a.remove();
                                  setTimeout(() => URL.revokeObjectURL(pngUrl), 1000);
                                  status.textContent = 'PNG exported at 1400 × 1370 px.';
                                  button.disabled = false;
                                }}, 'image/png');
                              }};
                              img.onerror = () => {{
                                URL.revokeObjectURL(svgUrl);
                                status.textContent = 'Could not render SVG to PNG.';
                                button.disabled = false;
                              }};
                              img.src = svgUrl;
                            }} catch (err) {{
                              status.textContent = 'PNG export failed: ' + err.message;
                              button.disabled = false;
                            }}
                          }});
                        }})();
                        </script>
                        '''
                        st.components.v1.html(export_html, height=52, scrolling=False)
                        with st.expander("Calculated trajectory table", expanded=False):
                            st.dataframe(trajectory, use_container_width=True, hide_index=True)
                    except Exception as exc:
                        st.error(f"Could not draw schematic: {exc}")

st.caption("Minimum Curvature trajectory calculation. Schematic horizontal departure is illustrative, not to scale. Verify tubular data and section geometry before formal engineering use.")
