import streamlit as st
import pandas as pd
import os, time
from engine import ParasiteIdentifier, SENTINEL

# ------------------------- CONFIG -------------------------
st.set_page_config(page_title="🦠 ParAI-D: Intelligent Parasite Diagnostic Assistant", layout="wide")
DATA_PATH = "ParasiteMasterData.xlsx"
FIXED_MAX_SCORE = 113  # model-wide baseline

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

# ------------------------- RESET FIRST -------------------------
if st.session_state.get("__RESET_ALL__", False):
    for k in list(st.session_state.keys()):
        if k not in ["_engine", "_df", "_mtime", "__RESET_ALL__"]:
            del st.session_state[k]
    st.session_state["__RESET_ALL__"] = False
    st.rerun()

# ------------------------- UTILS -------------------------
def fmt_time(ts):
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    except Exception:
        return "Unknown"

def split_vals(v):
    return [s.strip().lower() for s in str(v).split(";") if s and s.strip()]

def get_unique_values(df, column, prepend_choose=False, extra=None):
    vals = []
    if column in df.columns:
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
    if prepend_choose:
        vals = ["Choose…"] + vals  # maps to SENTINEL later
    return vals

def pct_to_color(pct):
    pct = max(0.0, min(100.0, pct)) / 100.0
    r = int(255 * (1 - pct))
    g = int(150 + 105 * pct)
    b = int(60 * (1 - pct))
    return f"#{r:02x}{g:02x}{b:02x}"

def pill(text, color):
    return f"<span style='display:inline-block;padding:4px 10px;border-radius:999px;background:{color};color:white;font-weight:600;font-size:12px;'>{text}</span>"

def progress_bar_html(percent, color):
    return f"<div style='background:#ddd;height:6px;border-radius:999px;overflow:hidden;margin-top:6px;'><div style='width:{percent:.1f}%;background:{color};height:100%;'></div></div>"

def valid_field(val):
    if not val:
        return False
    if isinstance(val, list):
        vals = [str(x).lower() for x in val if str(x).strip()]
        return any(x not in ("unknown", "choose…", "choose...", SENTINEL, "") for x in vals)
    v = str(val).lower()
    return v not in ("unknown", "choose…", "choose...", SENTINEL, "")

# ------------------------- REASONING -------------------------
KEY_FIELDS_FOR_DIFF = [
    "Blood Film Result", "Cysts on Imaging", "Eosinophilia",
    "Vector Exposure", "Anatomy Involvement", "Countries Visited", "Symptoms"
]
FIELD_TO_NEXT_TEST = {
    "Blood Film Result": "Blood film (thick/thin smear) or PCR",
    "Stool Cysts or Ova": "Stool O&P (concentration, trichrome); antigen or PCR",
    "Cysts on Imaging": "Targeted ultrasound/CT/MRI",
    "Eosinophilia": "CBC with differential; consider total IgE",
    "Neurological Involvement": "Neurological exam ± MRI/CT; CSF if indicated",
    "Vector Exposure": "Structured exposure history (ticks, insects, fish/meat/produce/soil)",
    "Anatomy Involvement": "Focused exam or imaging of the organ system",
    "Symptoms": "Structured symptom review (GI pattern, RUQ pain, skin lesions)",
    "Liver Function Tests": "LFT panel",
    "Fever": "Fever charting; malaria RDT when appropriate",
}

def summarize_reasoning(top_row, user_input, competitors_df):
    def ui_has(field):
        v = user_input.get(field, [])
        return valid_field(v)

    def matches(field):
        ds = split_vals(top_row.get(field, "") if field in top_row else top_row.get("ref_row", {}).get(field, ""))
        ui_vals = user_input.get(field, [])
        ui_vals = [x.lower() for x in ui_vals] if isinstance(ui_vals, list) else [str(ui_vals).lower()]
        ui_vals = [x for x in ui_vals if x not in ("unknown", "choose…", "choose...", SENTINEL, "")]
        return any(u in ds for u in ui_vals) if ui_vals else False

    positives = []
    if ui_has("Vector Exposure") and matches("Vector Exposure"):
        positives.append("vector exposure aligns")
    if ui_has("Anatomy Involvement") and matches("Anatomy Involvement"):
        positives.append("organ involvement matches")
    if ui_has("Countries Visited") and matches("Countries Visited"):
        positives.append("geography is consistent")
    if ui_has("Eosinophilia") and matches("Eosinophilia"):
        positives.append("eosinophilia pattern is supportive")
    if ui_has("Blood Film Result") and matches("Blood Film Result"):
        positives.append("blood film findings are supportive")
    if ui_has("Cysts on Imaging") and matches("Cysts on Imaging"):
        positives.append("imaging pattern is consistent")

    if positives:
        lead = ", ".join(positives[:-1]) + ("," if len(positives) > 1 else "")
        tail = f" and {positives[-1]}" if len(positives) > 1 else positives[0]
        reasoning = f"The {lead}{tail} for **{top_row['Parasite']}**."
    else:
        reasoning = f"The overall pattern is compatible with **{top_row['Parasite']}**, though direct matches are limited."

    comparisons = []
    if isinstance(competitors_df, pd.DataFrame) and not competitors_df.empty:
        for _, comp in competitors_df.iterrows():
            diffs = []
            for f in KEY_FIELDS_FOR_DIFF:
                a = str(top_row.get(f, top_row.get('ref_row', {}).get(f, ""))).lower()
                b = str(comp.get(f, comp.get('ref_row', {}).get(f, ""))).lower()
                if a != b:
                    diffs.append(f)
            if diffs:
                comparisons.append(
                    f"Compared with **{comp['Parasite']}**, key differentiators are: " +
                    ", ".join(diffs[:3]) + ("" if len(diffs) <= 3 else ", …") + "."
                )

    next_tests = []
    for f, t in FIELD_TO_NEXT_TEST.items():
        v = user_input.get(f, [])
        if not valid_field(v):
            next_tests.append(t)
    next_tests = sorted(set(next_tests))

    return reasoning, comparisons, next_tests

# ------------------------- LOAD ENGINE + DF (live reload) -------------------------
@st.cache_resource
def _init_engine_df(path: str):
    df = pd.read_excel(path)
    df.columns = [c.strip() for c in df.columns]
    # ensure numeric group and fallback
    df["Group"] = pd.to_numeric(df.get("Group"), errors="coerce")
    df["Group_filled"] = df["Group"].fillna(-1)
    eng = ParasiteIdentifier(df)
    return eng, df

def reload_if_changed():
    mtime = os.path.getmtime(DATA_PATH)
    if "_mtime" not in st.session_state or mtime != st.session_state["_mtime"]:
        eng, df = _init_engine_df(DATA_PATH)
        st.session_state["_engine"] = eng
        st.session_state["_df"] = df
        st.session_state["_mtime"] = mtime
        st.toast("🔄 Database reloaded!", icon="✅")
    return st.session_state["_engine"], st.session_state["_df"], st.session_state["_mtime"]

if "_engine" not in st.session_state:
    eng0, df0 = _init_engine_df(DATA_PATH)
    st.session_state["_engine"] = eng0
    st.session_state["_df"] = df0
    st.session_state["_mtime"] = os.path.getmtime(DATA_PATH)

eng, df, mtime = reload_if_changed()

# ------------------------- SIDEBAR -------------------------
with st.sidebar:
    st.markdown("### 📦 Database Info")
    st.caption(f"**ParasiteMasterData.xlsx** last updated: `{fmt_time(mtime)}`")
    st.divider()

    st.header("⚙️ Input Parameters")

    # Environmental
    with st.expander("🌍 Environmental Data", expanded=False):
        countries = st.multiselect("Countries Visited", get_unique_values(df, "Countries Visited"))
        anatomy   = st.multiselect("Anatomy Involvement", get_unique_values(df, "Anatomy Involvement"))
        vector    = st.multiselect("Vector Exposure", get_unique_values(df, "Vector Exposure"))

    # Symptoms
    with st.expander("🧬 Symptomatic Data", expanded=False):
        symptoms  = st.multiselect("Symptoms", get_unique_values(df, "Symptoms"))
        duration  = st.multiselect("Duration of Illness", get_unique_values(df, "Duration of Illness"))

    # Lab
    with st.expander("🧫 Laboratory Data", expanded=False):
        blood_film    = st.selectbox("Blood Film Result", get_unique_values(df, "Blood Film Result", prepend_choose=True))
        lft           = st.selectbox("Liver Function Tests", get_unique_values(df, "Liver Function Tests", prepend_choose=True))
        cysts_imaging = st.selectbox("Cysts on Imaging", get_unique_values(df, "Cysts on Imaging", prepend_choose=True, extra=["None"]))
        neuro         = st.selectbox("Neurological Involvement", get_unique_values(df, "Neurological Involvement", prepend_choose=True))
        eos           = st.selectbox("Eosinophilia", get_unique_values(df, "Eosinophilia", prepend_choose=True))
        fever         = st.selectbox("Fever", get_unique_values(df, "Fever", prepend_choose=True))
        diarrhea      = st.selectbox("Diarrhea", get_unique_values(df, "Diarrhea", prepend_choose=True))
        bloody        = st.selectbox("Bloody Diarrhea", get_unique_values(df, "Bloody Diarrhea", prepend_choose=True))
        stool         = st.selectbox("Stool Cysts or Ova", get_unique_values(df, "Stool Cysts or Ova", prepend_choose=True))
        anemia        = st.selectbox("Anemia", get_unique_values(df, "Anemia", prepend_choose=True))
        ige           = st.selectbox("High IgE Level", get_unique_values(df, "High IgE Level", prepend_choose=True))

    # Other
    with st.expander("🧩 Other", expanded=False):
        animal = st.multiselect("Animal Contact Type", get_unique_values(df, "Animal Contact Type"))
        immune = st.selectbox("Immune Status", get_unique_values(df, "Immune Status", prepend_choose=True))

    st.markdown("---")
    colA, colB = st.columns(2)
    with colA:
        go = st.button("🔍 Analyze", use_container_width=True)
    with colB:
        if st.button("♻️ Reset all", use_container_width=True):
            st.session_state["__RESET_ALL__"] = True
            st.rerun()

# ------------------------- MAIN -------------------------
st.title("🦠 ParAI-D")
st.caption("AI-assisted differential diagnosis for parasitic infections.")
st.divider()

if go:
    # Map single-selects "Choose…" to SENTINEL
    def as_single_list(v):
        if str(v).lower().startswith("choose"):
            return [SENTINEL]
        return [v]

    ui = {
        "Countries Visited": countries,
        "Anatomy Involvement": anatomy,
        "Vector Exposure": vector,
        "Symptoms": symptoms,
        "Duration of Illness": duration,
        "Animal Contact Type": animal,
        "Blood Film Result": as_single_list(blood_film),
        "Immune Status": as_single_list(immune),
        "Liver Function Tests": as_single_list(lft),
        "Neurological Involvement": as_single_list(neuro),
        "Eosinophilia": as_single_list(eos),
        "Fever": as_single_list(fever),
        "Diarrhea": as_single_list(diarrhea),
        "Bloody Diarrhea": as_single_list(bloody),
        "Stool Cysts or Ova": as_single_list(stool),
        "Anemia": as_single_list(anemia),
        "High IgE Level": as_single_list(ige),
        "Cysts on Imaging": as_single_list(cysts_imaging),
    }

    results = eng.score_entry(ui)

    # Ensure Group exists; engine already includes it, but guard just in case
    if "Group" not in results.columns:
        if "Group" in df.columns:
            results = results.merge(df[["Parasite", "Group"]], on="Parasite", how="left")
        else:
            results["Group"] = -1

    results["Group_filled"] = pd.to_numeric(results["Group"], errors="coerce").fillna(-1)

    # Confidence metrics
    results["Total Confidence (%)"] = (results["Score"] / FIXED_MAX_SCORE) * 100
    results["User Confidence (%)"] = results.apply(lambda r: eng.compute_user_confidence(ui, r), axis=1)

    st.caption("🟢 **User Confidence** = match quality based only on your entered fields · ⚪ **Total Confidence** = overall fit (normalised to all fields).")
    st.divider()

    # Build group panels
    groups = []
    for g, sub in results.groupby("Group_filled", dropna=False):
        sub = sub.sort_values("Likelihood (%)", ascending=False)
        top = sub.iloc[0]
        groups.append({
            "Group": int(g),
            "Name": GROUP_NAMES.get(int(g), f"Group {int(g)}"),
            "Rows": sub.head(5).copy(),
            "Likelihood": float(top["Likelihood (%)"]),
            "UserConf": float(top["User Confidence (%)"]),
            "TotalConf": float(top["Total Confidence (%)"])
        })

    groups = sorted(groups, key=lambda x: x["Likelihood"], reverse=True)

    # Render groups + species (with adaptive reasoning)
    first_group = True
    for grp in groups:
        color = pct_to_color(grp["Likelihood"])
        st.markdown(
            f"<div style='display:flex;flex-direction:column;gap:4px;margin:8px 0 2px 0;'>"
            f"<div style='display:flex;align-items:center;gap:12px;'>"
            f"<div style='font-size:20px;font-weight:700;line-height:1.2;'>{grp['Name']}</div>"
            f"{pill(f'{grp['Likelihood']:.1f}% likely', color)}</div>"
            f"{progress_bar_html(grp['Likelihood'], color)}</div>",
            unsafe_allow_html=True,
        )

        with st.expander("Expand group details", expanded=first_group):
            st.markdown(
                f"**User Confidence (top species):** {grp['UserConf']:.1f}%  |  "
                f"**Total Confidence (top species):** {grp['TotalConf']:.1f}%"
            )
            st.markdown("#### Species in this group")

            rows = grp["Rows"]
            first_species = True if first_group else False

            for _, row in rows.iterrows():
                title = f"{row['Parasite']} · Subtype {row.get('Subtype','')}"
                # Nearby competitors within ±10% likelihood from *this group's* rows
                nearby = rows[
                    (rows["Likelihood (%)"] >= row["Likelihood (%)"] - 10.0) &
                    (rows["Likelihood (%)"] <= row["Likelihood (%)"] + 10.0) &
                    (rows["Parasite"] != row["Parasite"])
                ]
                reasoning, comparisons, next_tests = summarize_reasoning(row, ui, nearby)

                with st.expander(title, expanded=first_species):
                    st.markdown(pill(f"{row['Likelihood (%)']:.1f}%", pct_to_color(row["Likelihood (%)"])), unsafe_allow_html=True)

                    # Reasoning
                    st.markdown(f"**Reasoning:** {reasoning}")

                    # Comparisons
                    if comparisons:
                        st.markdown("**Comparison to close candidates:**")
                        for line in comparisons:
                            st.markdown(f"- {line}")
                        st.caption("Close competitors considered: " + ", ".join(nearby["Parasite"].tolist()))

                    # Next tests (based on missing inputs)
                    if next_tests:
                        st.markdown("**Next tests to differentiate (based on missing inputs):**")
                        for t in next_tests:
                            st.markdown(f"- {t}")

                    # Confirmatory tests (split by ';')
                    key_text = str(row.get("Key Test", "")).strip()
                    if key_text:
                        bullets = [b.strip() for b in key_text.split(";") if b.strip()]
                        if bullets:
                            st.markdown("**Confirmatory / definitive tests:**")
                            for b in bullets:
                                st.markdown(f"- {b}")

                    # Confidence summary
                    st.markdown(
                        f"**User Confidence:** {row['User Confidence (%)']:.1f}%  ·  "
                        f"**Total Confidence:** {row['Total Confidence (%)']:.1f}%"
                    )

                first_species = False  # only first species auto-expands
        st.markdown("---")
        first_group = False

else:
    st.info("Open the sidebar, fill known fields, and click **Analyze** to generate results.")

# ------------------------- FOOTER -------------------------
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
