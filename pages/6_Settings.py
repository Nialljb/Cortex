"""Meridian — Settings page (study config editor)."""
import copy
import json
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app_utils import load_config, save_config, page_header

st.set_page_config(page_title='Settings — Meridian', page_icon='⚙️', layout='wide')
cfg = load_config()
page_header(cfg, subtitle='Study Settings')

st.info(
    'Changes are saved to `config/study_config.json` and take effect immediately '
    'on all pages. The normative model pipeline is **not** affected by these settings.'
)

# Work on a deep copy so we can detect changes before saving
new_cfg = copy.deepcopy(cfg)

# ── Study Info ────────────────────────────────────────────────────────────────
with st.expander('📌 Study Information', expanded=True):
    c1, c2 = st.columns(2)
    new_cfg['study']['name']        = c1.text_input('Study name',    value=cfg['study']['name'])
    new_cfg['study']['institution'] = c2.text_input('Institution',   value=cfg['study'].get('institution', ''))
    new_cfg['study']['type']        = c1.text_input('Study type',    value=cfg['study'].get('type', ''))
    new_cfg['study']['description'] = st.text_area('Description',    value=cfg['study'].get('description', ''), height=70)

# ── Cohort ────────────────────────────────────────────────────────────────────
with st.expander('👥 Cohort Settings', expanded=False):
    c1, c2 = st.columns(2)
    new_cfg['cohort']['age_units'] = c1.selectbox(
        'Age units',
        ['months', 'years', 'days'],
        index=['months', 'years', 'days'].index(cfg['cohort'].get('age_units', 'months')),
    )
    new_cfg['cohort']['age_label'] = c2.text_input(
        'Age axis label', value=cfg['cohort'].get('age_label', 'Age (months)')
    )

# ── Structures ────────────────────────────────────────────────────────────────
with st.expander('🧠 Brain Structures', expanded=False):
    st.caption(
        'Define the structures modelled in this study. The **key** must match the '
        'column name in `normative_sample.csv` and `predictions.pkl`.'
    )

    structs = copy.deepcopy(cfg.get('structures', []))

    for i, s in enumerate(structs):
        row = st.columns([2, 2, 1, 0.5])
        structs[i]['key']    = row[0].text_input(f'Key #{i+1}',    value=s['key'],    key=f's_key_{i}')
        structs[i]['label']  = row[1].text_input(f'Label #{i+1}',  value=s['label'],  key=f's_lbl_{i}')
        structs[i]['colour'] = row[2].color_picker(f'Colour #{i+1}', value=s['colour'], key=f's_col_{i}')
        if row[3].button('✕', key=f's_del_{i}', help='Remove structure'):
            structs.pop(i)
            st.rerun()

    if st.button('+ Add structure'):
        structs.append({'key': 'new_structure_ml', 'label': 'New Structure', 'colour': '#888888'})
        st.rerun()

    new_cfg['structures'] = structs

# ── Flag Thresholds ───────────────────────────────────────────────────────────
with st.expander('🚩 Flag Thresholds (centile)', expanded=False):
    fc = cfg.get('flags', {})
    c1, c2, c3, c4 = st.columns(4)
    new_cfg['flags']['critical_low_pct']  = c1.number_input('Critical low',  min_value=1, max_value=20, value=int(fc.get('critical_low_pct', 5)))
    new_cfg['flags']['at_risk_low_pct']   = c2.number_input('At-risk low',   min_value=1, max_value=30, value=int(fc.get('at_risk_low_pct', 10)))
    new_cfg['flags']['at_risk_high_pct']  = c3.number_input('At-risk high',  min_value=70, max_value=99, value=int(fc.get('at_risk_high_pct', 90)))
    new_cfg['flags']['critical_high_pct'] = c4.number_input('Critical high', min_value=80, max_value=99, value=int(fc.get('critical_high_pct', 95)))

# ── Feedback Options ──────────────────────────────────────────────────────────
with st.expander('📝 Feedback Form Options', expanded=False):
    fb = cfg.get('feedback', {})
    st.caption('Comma-separated lists. These populate the dropdowns in the Subject Review form.')

    diag_str = st.text_area(
        'Diagnosis options (one per line)',
        value='\n'.join(fb.get('diagnosis_options', [])),
        height=140,
    )
    qc_str = st.text_input(
        'Clinician QC options (comma-separated)',
        value=', '.join(fb.get('clinician_qc_options', [])),
    )
    new_cfg['feedback']['diagnosis_options']   = [d.strip() for d in diag_str.splitlines() if d.strip()]
    new_cfg['feedback']['clinician_qc_options'] = [q.strip() for q in qc_str.split(',') if q.strip()]

# ── Proforma ──────────────────────────────────────────────────────────────────
with st.expander('📊 Overview Proforma', expanded=False):
    st.caption(
        'Choose which CSV columns appear as breakdown charts on the Overview page. '
        'Any column in `normative_sample.csv` is valid.'
    )
    try:
        import pandas as pd
        from app_utils import load_csv
        df_cols = list(load_csv().columns)
    except Exception:
        df_cols = ['sex_label', 'qc_pass', 'scan_date', 'site', 'diagnosis']

    current_vars = cfg.get('proforma', {}).get('overview_breakdown_vars', ['sex_label', 'qc_pass'])
    new_cfg['proforma']['overview_breakdown_vars'] = st.multiselect(
        'Breakdown variables',
        options=df_cols,
        default=[v for v in current_vars if v in df_cols],
    )

# ── Task Requirements ─────────────────────────────────────────────────────────
with st.expander('✅ Task Completion Requirements', expanded=False):
    st.caption(
        'A subject is marked "Reviewed" only when all required steps are complete. '
        '"clinician_feedback" = feedback form submitted. '
        '"image_qc" = image QC rating saved.'
    )
    current_steps = cfg.get('tasks', {}).get('required_steps', ['clinician_feedback'])
    new_steps = []
    if st.checkbox('Require clinician feedback',
                   value='clinician_feedback' in current_steps):
        new_steps.append('clinician_feedback')
    if st.checkbox('Require image QC rating',
                   value='image_qc' in current_steps):
        new_steps.append('image_qc')
    new_cfg['tasks']['required_steps'] = new_steps or ['clinician_feedback']

# ── Save ──────────────────────────────────────────────────────────────────────
st.markdown('---')
if st.button('💾 Save Settings', type='primary'):
    save_config(new_cfg)
    st.success('Settings saved. All pages will use the updated config.')
    st.rerun()
