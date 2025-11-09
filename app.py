import streamlit as st
import pandas as pd
import os
import time
from engine import ParasiteIdentifier

# =========================================
# CONFIG
# =========================================
st.set_page_config(page_title="🦠 ParAI-D: Intelligent Parasite Diagnostic Assistant", layout="wide")
DATA_PATH = "ParasiteMasterData.xlsx"
FIXED_MAX_SCORE = 113  # keep aligned with engine weights

GROUP_NAMES = {
    1: "Intestinal Protozoa",
    2: "Opportunistic Protozoa",
    3: "Blood & Tissue Protozoa",
    4: "Intestinal Nematodes",
    5: "Tissue / Migratory Nematodes",
    6: "Filarial Nematodes",
    7: "Trematodes (Flukes)",
    8: "Cestodes (Tapeworms)",
    9: "Myiasis / Arthropod Parasites",
    10: "Rare / Zoonotic Special Parasites",
    -1: "Unassigned / Unknown Group",
}

# =========================================
# UTILITIES
# =========================================
def fmt_time(ts):
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    except Exception:
        return "Unknown"

def get_unique_values(df, column, extra=None):
    vals = []
    for x in df[column].dropna().unique():
        for part in str(x).split(";"):
            part = part.strip()
            if part:
                vals.append(part)
    vals = sorted(set(vals))
    if extra:
        for e in extra:
            if e not in vals:
                vals.append(e)
    vals.insert(0, "Unknown")
    return vals

def pct_to_color(pct: float):
    pct = max(0.0, min(100.0, pct)) / 100.0
    r = int(255 * (1 - pct))
    g = int(150 + 105 * pct)
    b = int(60 * (1 - pct))
    return f"#{r:02x}{g:02x}{b:02x}"

def pill(text, color):
    return f"""
    <span style='display:inline-block;padding:4px 10px;border-radius:999px;
    background:{color};color:white;font-weight:600;font-size:12px;'>{text}</span>
    """

def progress_bar_html(percent, color):
    return f"""
    <div style='background:#ddd;height:6px;border-radius:999px;overflow:hidden;margin-top:6px;'>
        <div style='width:{percent:.1f}%;background:{color};height:100%;'></div>
    </div>
    """

def split_vals(v):
    return [s.strip().lower() for s in str(v).split(";") if s.strip()]

# =========================================
# REASONING HELPERS
# =========================================
KEY_FIELDS_FOR_DIFF = [
    "Blood Film Result", "Cysts on Imaging", "Eosinophilia",
    "Vector Exposure", "Anatomy Involvement", "Countries Visited", "Symptoms"
]

FIELD_TO_NEXT_TEST = {
    "Blood Film Result": "Blood film (thick/thin smear) or PCR",
    "Stool Cysts or Ova": "Stool O&P (concentration, trichrome), antigen or PCR",
    "Cysts on Imaging": "Targeted ultrasound/CT/MRI",
    "Eosinophilia": "CBC with differential; consider total IgE",
    "Neurological Involvement": "Neurological exam ± MRI/CT; CSF if indicated",
    "Vector Exposure": "Structured exposure history (ticks, insects, fish/meat/produce/soil)",
    "Anatomy Involvement": "Focused exam or imaging of the organ system",
    "Symptoms": "Structured symptom review (GI pattern, RUQ pain, skin lesions)",
    "Liver Function Tests": "LFT panel",
    "Fever": "Fever charting; malaria RDT if febrile + travel",
}

def summarize_reasoning(top_row, user_input, nearby_rows):
    """
    Produce adaptive reasoning text comparing the top species to other close candidates.
    - nearby_rows: DataFrame of competitors within +/- 10% likelihood (excluding top_row)
    Returns (reasoning_text, next_tests_list)
    """
    notes = []

    # Positive matches (supporting the top species)
    def ui_has(field):
        val = user_input.get(field, ["Unknown"])
        if isinstance(val, list):
            return any(v.lower() != "unknown" for v in val)
        return str(val).lower() != "unknown"

    def matches(field):
        ds = split_vals(top_row.get(field, ""))
        ui_vals = user_input.get(field, ["Unknown"])
        ui_vals = [x.lower() for x in ui_vals] if isinstance(ui_vals, list) else [str(ui_vals).lower()]
        return any(u in ds for u in ui_vals)

    positive_bits = []
    if ui_has("Vector Exposure") and matches("Vector Exposure"):
        positive_bits.append("vector exposure aligns")
    if ui_has("Anatomy Involvement") and matches("Anatomy Involvement"):
        positive_bits.append("organ involvement matches")
    if ui_has("Countries Visited") and matches("Countries Visited"):
        positive_bits.append("geography is consistent")
    if ui_has("Eosinophilia") and matches("Eosinophilia"):
        positive_bits.append("eosinophilia pattern is supportive")
    if ui_has("Blood Film Result") and matches("Blood Film Result"):
        positive_bits.append("blood film pattern is supportive")
    if ui_has("Cysts on Imaging") and matches("Cysts on Imaging"):
        positive_bits.append("imaging pattern is consistent")

    if positive_bits:
        notes.append("The " + ", ".join(positive_bits[:-1]) + ("," if len(positive_bits) > 1 else "") +
                     (f" and {positive_bits[-1]}" if len(positive_bits) > 1 else f" {positive_bits[0]}") +
                     f" for **{top_row['Parasite']}**.")
    else:
        notes.append(f"The overall pattern is compatible with **{top_row['Parasite']}**, but direct matches are limited.")

    # Differences versus close competitors
    if not nearby_rows.empty:
        diffs_sentences = []
        for _, comp in nearby_rows.iterrows():
            differing = []
            for f in KEY_FIELDS_FOR_DIFF:
                a = str(top_row.get(f, "")).lower()
                b = str(comp.get(f, "")).lower()
                if a != b:
                    differing.append(f)
            if differing:
                diffs_sentences.append(
                    f"Compared with **{comp['Parasite']}**, key differences include: " +
                    ", ".join(differing[:3]) + ("" if len(differing) <= 3 else ", …") + "."
                )
        if diffs_sentences:
            notes.append(" ".join(diffs_sentences))

    # Next tests based on missing inputs
    next_tests = []
    for f, t in FIELD_TO_NEXT_TEST.items():
        val = user_input.get(f, ["Unknown"])
        is_unknown = (isinstance(val, list) and all(v == "Unknown" for v in val)) or (isinstance(val, str) and val.lower() == "unknown")
        if is_unknown:
            next_tests.append(t)

    reasoning_text = " ".join(notes)
    return reasoning_text, sorted(set(next_tests))

def compute_user_confidence(row: pd.Series, ui: dict) -> float:
    """
    Recompute % using ONLY fields the user actually entered (ignores 'Unknown').
    Mirrors engine weights.
    """
    def any_match(u_list, field):
        ds = split_vals(row.get(field, ""))
        return any(u.lower() in ds for u in u_list)

    score = 0.0
    max_sc = 0.0

    # Countries (5)
    if ui.get("Countries Visited") and ui["Countries Visited"] != ["Unknown"]:
        max_sc += 5
        if any_match(ui["Countries Visited"], "Countries Visited"):
            score += 5
    # Anatomy (5)
    if ui.get("Anatomy Involvement") and ui["Anatomy Involvement"] != ["Unknown"]:
        max_sc += 5
        if any_match(ui["Anatomy Involvement"], "Anatomy Involvement"):
            score += 5
    # Vector (8) — full credit if ONLY Other(Including Unknown)
    if ui.get("Vector Exposure") and ui["Vector Exposure"] != ["Unknown"]:
        max_sc += 8
        lower_vec = [x.lower() for x in ui["Vector Exposure"]]
        if lower_vec == ["other(including unknown)"]:
            score += 8
        elif any_match(ui["Vector Exposure"], "Vector Exposure"):
            score += 8
    # Symptoms (10) proportional
    if ui.get("Symptoms") and ui["Symptoms"] != ["Unknown"]:
        max_sc += 10
        ds = split_vals(row.get("Symptoms", ""))
        n_user = len(ui["Symptoms"])
        matches = sum(1 for s in ui["Symptoms"] if s.lower() in ds)
        score += (10.0 / max(1, n_user)) * matches
    # Duration (5)
    if ui.get("Duration of Illness") and ui["Duration of Illness"] != ["Unknown"]:
        max_sc += 5
        if any_match(ui["Duration of Illness"], "Duration of Illness"):
            score += 5
    # Animal contact (8)
    if ui.get("Animal Contact Type") and ui["Animal Contact Type"] != ["Unknown"]:
        max_sc += 8
        if any_match(ui["Animal Contact Type"], "Animal Contact Type"):
            score += 8
    # Blood film (15)
    if ui.get("Blood Film Result") and ui["Blood Film Result"][0].lower() != "unknown":
        max_sc += 15
        user_bf = ui["Blood Film Result"][0].lower()
        data_bf = split_vals(row.get("Blood Film Result", ""))
        if user_bf == "negative":
            if "negative" not in data_bf:
                score -= 10
        else:
            if any(x != "negative" for x in data_bf):
                score += 15
    # Immune (2)
    if ui.get("Immune Status") and ui["Immune Status"][0].lower() != "unknown":
        max_sc += 2
        if any_match(ui["Immune Status"], "Immune Status"):
            score += 2
    # LFT (5) with Variable rule
    if ui.get("Liver Function Tests") and ui["Liver Function Tests"][0].lower() != "unknown":
        max_sc += 5
        ds = split_vals(row.get("Liver Function Tests", ""))
        user_lft = ui["Liver Function Tests"][0].lower()
        if "variable" in ds or user_lft in ds:
            score += 5
    # Lab flags (5 each)
    lab_fields = [
        "Neurological Involvement", "Eosinophilia", "Fever",
        "Diarrhea", "Bloody Diarrhea", "Stool Cysts or Ova",
        "Anemia", "High IgE Level"
    ]
    for f in lab_fields:
        u = ui.get(f, ["Unknown"])[0].lower()
        if u != "unknown":
            max_sc += 5
            ds = split_vals(row.get(f, ""))
            if "variable" in ds or u in ds:
                score += 5
    # Cysts on Imaging (10)
    if ui.get("Cysts on Imaging") and ui["Cysts on Imaging"][0].lower() != "unknown":
        max_sc += 10
        u = ui["Cysts on Imaging"][0].lower()
        ds = split_vals(row.get("Cysts on Imaging", ""))
        if u == "negative":
            if "negative" not in ds:
                score -= 5
        else:
            if any(x != "negative" for x in ds):
                score += 10

    return (score / max_sc) * 100 if max_sc > 0 else 0.0

# =========================================
# LIVE DATA RELOAD (no manual cache clear)
# =========================================
@st.cache_resource(show_spinner=False)
def init_engine():
    df = pd.read_excel(DATA_PATH)
    df.columns = [c.strip() for c in df.columns]
    df["Group"] = pd.to_numeric(df.get("Group"), errors="coerce")
    df["Group_filled"] = df["Group"].fillna(-1)
    return ParasiteIdentifier(df), df

def reload_if_changed():
    mtime = os.path.getmtime(DATA_PATH)
    last = st.session_state.get("_mtime")
    if not last or mtime != last:
        df = pd.read_excel(DATA_PATH)
        df.columns = [c.strip() for c in df.columns]
        df["Group"] = pd.to_numeric(df.get("Group"), errors="coerce")
        df["Group_filled"] = df["Group"].fillna(-1)
        st.session_state["_engine"] = ParasiteIdentifier(df)
        st.session_state["_df"] = df
        st.session_state["_mtime"] = mtime
        st.toast("🔄 Database reloaded automatically!", icon="✅")
    return st.session_state["_engine"], st.session_state["_df"], st.session_state["_mtime"]

if "_engine" not in st.session_state:
    eng0, df0 = init_engine()
    st.session_state["_engine"] = eng0
    st.session_state["_df"] = df0
    st.session_state["_mtime"] = os.path.getmtime(DATA_PATH)

eng, df, mtime = reload_if_changed()

# =========================================
# SIDEBAR — Inputs + Reset/Analyze
# =========================================
with st.sidebar:
    st.markdown("### 📦 Database Info")
    st.caption(f"**ParasiteMasterData.xlsx** last updated: `{fmt_time(mtime)}`")
    st.divider()
    st.header("⚙️ Input Parameters")

    # Widget helpers with keys so we can reset
    def multisel(label, col, key, extra=None):
        return st.multiselect(label, get_unique_values(df, col, extra), key=key)

    def selbox(label, col, key, extra=None):
        opts = get_unique_values(df, col, extra)
        return st.selectbox(label, opts, index=0, key=key)

    with st.expander("🌍 Environmental Data", expanded=False):
        countries = multisel("Countries Visited", "Countries Visited", key="countries")
        anatomy = multisel("Anatomy Involvement", "Anatomy Involvement", key="anatomy")
        vector = multisel("Vector Exposure", "Vector Exposure", key="vector")

    with st.expander("🧬 Symptomatic Data", expanded=False):
        symptoms = multisel("Symptoms", "Symptoms", key="symptoms")
        duration = st.multiselect("Duration of Illness", get_unique_values(df, "Duration of Illness"), key="duration")

    with st.expander("🧫 Laboratory Data", expanded=False):
        blood_film = selbox("Blood Film Result", "Blood Film Result", key="blood_film")
        lft = selbox("Liver Function Tests", "Liver Function Tests", key="lft")
        cysts_imaging = selbox("Cysts on Imaging", "Cysts on Imaging", key="cysts_imaging", extra=["None"])
        neuro = selbox("Neurological Involvement", "Neurological Involvement", key="neuro")
        eos = selbox("Eosinophilia", "Eosinophilia", key="eos")
        fever = selbox("Fever", "Fever", key="fever")
        diarrhea = selbox("Diarrhea", "Diarrhea", key="diarrhea")
        bloody = selbox("Bloody Diarrhea", "Bloody Diarrhea", key="bloody")
        stool = selbox("Stool Cysts or Ova", "Stool Cysts or Ova", key="stool")
        anemia = selbox("Anemia", "Anemia", key="anemia")
        ige = selbox("High IgE Level", "High IgE Level", key="ige")

    with st.expander("🧩 Other", expanded=False):
        animal = st.multiselect("Animal Contact Type", get_unique_values(df, "Animal Contact Type"), key="animal")
        immune = selbox("Immune Status", "Immune Status", key="immune")

    st.markdown("---")
    colA, colB = st.columns(2)
    with colA:
        go = st.button("🔍 Analyze", use_container_width=True)
    with colB:
        if st.button("♻️ Reset all", use_container_width=True):
            # Clear sidebar inputs
            for k in ["countries","anatomy","vector","symptoms","duration","animal"]:
                st.session_state[k] = []
            for k in ["blood_film","lft","cysts_imaging","neuro","eos","fever","diarrhea","bloody","stool","anemia","ige","immune"]:
                st.session_state[k] = "Unknown"
            st.experimental_rerun()

# =========================================
# MAIN
# =========================================
st.title("🦠 ParAI-D")
st.caption("AI-assisted differential diagnosis for parasitic infections.")
st.divider()

if go:
    ui = {
        "Countries Visited": countries or ["Unknown"],
        "Anatomy Involvement": anatomy or ["Unknown"],
        "Vector Exposure": vector or ["Unknown"],
        "Symptoms": symptoms or ["Unknown"],
        "Duration of Illness": duration or ["Unknown"],
        "Animal Contact Type": animal or ["Unknown"],
        "Blood Film Result": [blood_film],
        "Immune Status": [immune],
        "Liver Function Tests": [lft],
        "Neurological Involvement": [neuro],
        "Eosinophilia": [eos],
        "Fever": [fever],
        "Diarrhea": [diarrhea],
        "Bloody Diarrhea": [bloody],
        "Stool Cysts or Ova": [stool],
        "Anemia": [anemia],
        "High IgE Level": [ige],
        "Cysts on Imaging": [cysts_imaging],
    }

    results = eng.score_entry(ui)
    results = results.merge(df[["Parasite", "Group_filled"]], on="Parasite", how="left")
    results["Total Confidence (%)"] = (results["Score"] / FIXED_MAX_SCORE) * 100
    results["User Confidence (%)"] = results.apply(lambda r: compute_user_confidence(r, ui), axis=1)

    # Grouping
    grouped = []
    for g, sub in results.groupby("Group_filled", dropna=False):
        sub = sub.sort_values("Likelihood (%)", ascending=False)
        top = sub.iloc[0]
        grouped.append({
            "Group": int(g),
            "Group Name": GROUP_NAMES.get(int(g), f"Group {g}"),
            "Top Rows": sub.head(5).copy(),
            "Group Likelihood": float(top["Likelihood (%)"]),
            "User Confidence": float(top["User Confidence (%)"]),
            "Total Confidence": float(top["Total Confidence (%)"]),
        })

    # Sort groups by likelihood
    grouped = sorted(grouped, key=lambda x: x["Group Likelihood"], reverse=True)

    # Auto-expand: only the first (top) group expanded; within it, only the top species expanded
    first_group = True

    for grp in grouped:
        color = pct_to_color(grp["Group Likelihood"])
        st.markdown(
            f"<div style='display:flex;flex-direction:column;gap:4px;margin:8px 0 2px 0;'>"
            f"<div style='display:flex;align-items:center;gap:12px;'>"
            f"<div style='font-size:20px;font-weight:700;line-height:1.2;'>{grp['Group Name']}</div>"
            f"{pill(f'{grp['Group Likelihood']:.1f}% likely', color)}</div>"
            f"{progress_bar_html(grp['Group Likelihood'], color)}</div>",
            unsafe_allow_html=True,
        )

        with st.expander("Expand group details", expanded=first_group):
            st.markdown(
                f"**User Confidence:** {grp['User Confidence']:.1f}%  |  "
                f"**Total Confidence:** {grp['Total Confidence']:.1f}%"
            )
            st.markdown("#### Species in this group")

            top_rows = grp["Top Rows"]
            # We'll render each species as its own expander
            first_species = True if first_group else False

            # Precompute “nearby” competitors for richer reasoning (±10% window)
            # Do this once per species inside the loop
            for idx, row in top_rows.iterrows():
                sp_color = pct_to_color(row["Likelihood (%)"])
                sp_title = f"**{row['Parasite']}** {pill(f'{row['Likelihood (%)']:.1f}%', sp_color)} · Subtype: {row.get('Subtype','')}"
                # Find nearby candidates in this group (within ±10% likelihood, excluding itself)
                window = top_rows[
                    (top_rows["Likelihood (%)"] >= row["Likelihood (%)"] - 10.0) &
                    (top_rows["Likelihood (%)"] <= row["Likelihood (%)"] + 10.0) &
                    (top_rows["Parasite"] != row["Parasite"])
                ]
                reasoning, next_tests = summarize_reasoning(row, ui, window)

                with st.expander(sp_title, expanded=first_species):
                    st.markdown(f"- **Reasoning:** {reasoning}")
                    if len(window) > 0:
                        comps = ", ".join(window["Parasite"].tolist())
                        st.markdown(f"- **Close competitors considered:** {comps}")
                    if next_tests:
                        st.markdown(f"- **Next tests to differentiate (based on missing inputs):** " + ", ".join(next_tests))

                    # Confirmatory tests from Key Test / Key test / Key Notes
                    key_text = str(row.get("Key Test", row.get("Key test", row.get("Key Notes", "")))).strip()
                    if key_text:
                        bullets = [b.strip() for b in key_text.split(";") if b.strip()]
                        if bullets:
                            st.markdown("- **Confirmatory / definitive tests:**")
                            for b in bullets:
                                st.markdown(f"  - {b}")

                    st.markdown(
                        f"- **User Confidence:** {row['User Confidence (%)']:.1f}%"
                        f"  ·  **Total Confidence:** {row['Total Confidence (%)']:.1f}%"
                    )

                # Only auto-expand the very first species (in the first group)
                first_species = False

        st.markdown("---")
        first_group = False

else:
    st.info("Open the sidebar, fill known fields, and click **Analyze** to generate results.")

# =========================================
# FOOTER
# =========================================
st.markdown(
    """
    <hr style="margin-top:28px;margin-bottom:8px"/>
    <div style="font-size:12px; color:#888; text-align:center; padding-bottom:8px;">
        <strong>Disclaimer:</strong> ParAI-D is for assistance and training purposes only and is not a substitute for clinical judgement.<br/>
        Created by Zain.
    </div>
    """,
    unsafe_allow_html=True
)
