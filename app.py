import streamlit as st
import pandas as pd
import os
import time
from engine import ParasiteIdentifier

# -----------------------------
# CONFIG
# -----------------------------
st.set_page_config(page_title="🦠 ParAI-D: Intelligent Parasite Diagnostic Assistant", layout="wide")

DATA_PATH = "ParasiteMasterData.xlsx"
FIXED_MAX_SCORE = 113  # overall normalization

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


# -----------------------------
# UTILS
# -----------------------------
def fmt_time(ts):
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    except Exception:
        return "Unknown"

def get_unique_values(df, column, extra=None):
    vals = []
    for x in df[column].dropna().unique():
        vals.extend([p.strip() for p in str(x).split(";") if p.strip()])
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


# -----------------------------
# LIVE DATA RELOAD
# -----------------------------
@st.cache_resource(show_spinner=False)
def _init_identifier():
    """Initialize once, kept as global resource object."""
    df = pd.read_excel(DATA_PATH)
    df.columns = [c.strip() for c in df.columns]
    df["Group"] = pd.to_numeric(df.get("Group"), errors="coerce")
    df["Group_filled"] = df["Group"].fillna(-1)
    eng = ParasiteIdentifier(df)
    return eng, df

def reload_if_changed():
    """Force reload when file timestamp changes."""
    mtime = os.path.getmtime(DATA_PATH)
    last = st.session_state.get("_db_mtime")
    if not last or mtime != last:
        st.session_state["_db_mtime"] = mtime
        # fully reload from disk
        df = pd.read_excel(DATA_PATH)
        df.columns = [c.strip() for c in df.columns]
        df["Group"] = pd.to_numeric(df.get("Group"), errors="coerce")
        df["Group_filled"] = df["Group"].fillna(-1)
        eng = ParasiteIdentifier(df)
        st.session_state["_engine"] = eng
        st.session_state["_df"] = df
        st.session_state["_mtime"] = mtime
        return eng, df, mtime, True
    else:
        eng = st.session_state.get("_engine")
        df = st.session_state.get("_df")
        mtime = st.session_state.get("_mtime")
        return eng, df, mtime, False


# Initialize
if "_engine" not in st.session_state:
    eng, df = _init_identifier()
    st.session_state["_engine"] = eng
    st.session_state["_df"] = df
    st.session_state["_mtime"] = os.path.getmtime(DATA_PATH)
    st.session_state["_db_mtime"] = st.session_state["_mtime"]

# Each run → check for changes
eng, df, mtime, refreshed = reload_if_changed()
if refreshed:
    st.toast("🔄 Database reloaded automatically!", icon="✅")

# -----------------------------
# SIDEBAR
# -----------------------------
with st.sidebar:
    st.markdown("### 📦 Database Info")
    st.caption(f"**ParasiteMasterData.xlsx** last updated: `{fmt_time(mtime)}`")
    st.divider()
    st.header("⚙️ Input Parameters")

    def multisel(label, col, extra=None): return st.multiselect(label, get_unique_values(df, col, extra))
    def selbox(label, col, extra=None):
        opts = get_unique_values(df, col, extra)
        return st.selectbox(label, opts, index=0)

    with st.expander("🌍 Environmental Data", expanded=False):
        countries = multisel("Countries Visited", "Countries Visited")
        anatomy = multisel("Anatomy Involvement", "Anatomy Involvement")
        vector = multisel("Vector Exposure", "Vector Exposure")

    with st.expander("🧬 Symptomatic Data", expanded=False):
        symptoms = multisel("Symptoms", "Symptoms")
        duration = st.multiselect("Duration of Illness", get_unique_values(df, "Duration of Illness"))

    with st.expander("🧫 Laboratory Data", expanded=False):
        blood_film = selbox("Blood Film Result", "Blood Film Result")
        lft = selbox("Liver Function Tests", "Liver Function Tests")
        cysts_imaging = selbox("Cysts on Imaging", "Cysts on Imaging", extra=["None"])
        neuro = selbox("Neurological Involvement", "Neurological Involvement")
        eos = selbox("Eosinophilia", "Eosinophilia")
        fever = selbox("Fever", "Fever")
        diarrhea = selbox("Diarrhea", "Diarrhea")
        bloody = selbox("Bloody Diarrhea", "Bloody Diarrhea")
        stool = selbox("Stool Cysts or Ova", "Stool Cysts or Ova")
        anemia = selbox("Anemia", "Anemia")
        ige = selbox("High IgE Level", "High IgE Level")

    with st.expander("🧩 Other", expanded=False):
        animal = st.multiselect("Animal Contact Type", get_unique_values(df, "Animal Contact Type"))
        immune = selbox("Immune Status", "Immune Status")

    st.markdown("---")
    go = st.button("🔍 Analyze", use_container_width=True)

# -----------------------------
# MAIN
# -----------------------------
st.title("🦠 ParAI-D")
st.caption("AI-assisted differential diagnosis for parasitic infections.")
st.divider()

if go:
    # Prepare input
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
    df_merge = df[["Parasite", "Group_filled"]]
    results = results.merge(df_merge, on="Parasite", how="left")
    results["Total Confidence (%)"] = (results["Score"] / FIXED_MAX_SCORE) * 100

    grouped = []
    for g, sub in results.groupby("Group_filled", dropna=False):
        top = sub.sort_values("Likelihood (%)", ascending=False).iloc[0]
        grouped.append({
            "Group": int(g),
            "Group Name": GROUP_NAMES.get(int(g), f"Group {g}"),
            "Top Rows": sub.sort_values("Likelihood (%)", ascending=False).head(5).copy(),
            "Group Likelihood": float(top["Likelihood (%)"]),
            "Total Confidence": float(top["Total Confidence (%)"]),
        })

    grouped = sorted(grouped, key=lambda x: x["Group Likelihood"], reverse=True)

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
        with st.expander("Expand group details", expanded=False):
            st.markdown(f"**Total Confidence:** {grp['Total Confidence']:.1f}%")
            for _, row in grp["Top Rows"].iterrows():
                st.markdown(f"**{row['Parasite']}** – {row.get('Key Test','')}")
        st.markdown("---")

else:
    st.info("Use the sidebar to enter data and click **Analyze** to generate results.")

st.markdown(
    "<hr><div style='font-size:12px;color:#888;text-align:center;'>"
    "<strong>Disclaimer:</strong> For assistance and training purposes only. Created by Zain.</div>",
    unsafe_allow_html=True
)
