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
FIXED_MAX_SCORE = 113

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
# RESET
# =========================================
if st.session_state.get("__RESET_ALL__", False):
    for k in list(st.session_state.keys()):
        if k not in ["_engine", "_df", "_mtime"]:
            del st.session_state[k]
    st.session_state["__RESET_ALL__"] = False
    st.rerun()

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

def split_vals(v):
    return [s.strip().lower() for s in str(v).split(";") if s.strip()]

def valid_field(val):
    if not val:
        return False
    if isinstance(val, list):
        return any(v.lower() not in ("unknown", "", None) for v in val)
    return str(val).lower() not in ("unknown", "", None)

# =========================================
# USER CONFIDENCE
# =========================================
def compute_user_confidence(row, ui):
    def match(u_list, field):
        ds = split_vals(row.get(field, ""))
        return any(u.lower() in ds for u in u_list)

    score = 0
    max_sc = 0

    # Countries (5)
    if valid_field(ui["Countries Visited"]):
        max_sc += 5
        if match(ui["Countries Visited"], "Countries Visited"): score += 5

    # Anatomy (5)
    if valid_field(ui["Anatomy Involvement"]):
        max_sc += 5
        if match(ui["Anatomy Involvement"], "Anatomy Involvement"): score += 5

    # Vector (8)
    if valid_field(ui["Vector Exposure"]):
        max_sc += 8
        v = [x.lower() for x in ui["Vector Exposure"]]
        if v == ["other(including unknown)"]: score += 8
        elif match(ui["Vector Exposure"], "Vector Exposure"): score += 8

    # Symptoms (10)
    if valid_field(ui["Symptoms"]):
        max_sc += 10
        db = split_vals(row.get("Symptoms", ""))
        m = sum(1 for s in ui["Symptoms"] if s.lower() in db)
        score += (10 / len(ui["Symptoms"])) * m

    # Duration (5)
    if valid_field(ui["Duration of Illness"]):
        max_sc += 5
        if match(ui["Duration of Illness"], "Duration of Illness"): score += 5

    # Animal (8)
    if valid_field(ui["Animal Contact Type"]):
        max_sc += 8
        if match(ui["Animal Contact Type"], "Animal Contact Type"): score += 8

    # Blood film (15)
    bf = [x.lower() for x in ui["Blood Film Result"]][0]
    db = split_vals(row.get("Blood Film Result", ""))
    if bf not in ("unknown", "", None):
        max_sc += 15
        if bf == "negative":
            if all(x != "negative" for x in db): score -= 10
        else:
            if any(x != "negative" for x in db): score += 15

    # Immune (2)
    if valid_field(ui["Immune Status"]):
        max_sc += 2
        if match(ui["Immune Status"], "Immune Status"): score += 2

    # LFT (5)
    lft = [x.lower() for x in ui["Liver Function Tests"]][0]
    if lft not in ("unknown", "", None):
        max_sc += 5
        db_l = split_vals(row.get("Liver Function Tests", ""))
        if "variable" in db_l or lft in db_l: score += 5

    # Binary (5)
    for f in ["Neurological Involvement","Eosinophilia","Fever","Diarrhea","Bloody Diarrhea","Stool Cysts or Ova","Anemia","High IgE Level"]:
        v = [x.lower() for x in ui[f]][0]
        if v not in ("unknown", "", None):
            max_sc += 5
            dbv = split_vals(row.get(f, ""))
            if "variable" in dbv or v in dbv: score += 5

    # Cysts on Imaging (10)
    c = [x.lower() for x in ui["Cysts on Imaging"]][0]
    db_c = split_vals(row.get("Cysts on Imaging", ""))
    if c not in ("unknown", "", None):
        max_sc += 10
        if c == "negative":
            if all(x != "negative" for x in db_c): score -= 5
        else:
            if any(x != "negative" for x in db_c): score += 10

    return (score / max_sc) * 100 if max_sc > 0 else 0.0

# =========================================
# ENGINE INITIALIZATION
# =========================================
@st.cache_resource
def init_engine():
    df = pd.read_excel(DATA_PATH)
    df.columns = [c.strip() for c in df.columns]
    df["Group"] = pd.to_numeric(df.get("Group"), errors="coerce")
    df["Group_filled"] = df["Group"].fillna(-1)
    return ParasiteIdentifier(df), df

def reload_if_changed():
    mtime = os.path.getmtime(DATA_PATH)
    if "_mtime" not in st.session_state or mtime != st.session_state["_mtime"]:
        df = pd.read_excel(DATA_PATH)
        df.columns = [c.strip() for c in df.columns]
        df["Group"] = pd.to_numeric(df.get("Group"), errors="coerce")
        df["Group_filled"] = df["Group"].fillna(-1)
        st.session_state["_engine"] = ParasiteIdentifier(df)
        st.session_state["_df"] = df
        st.session_state["_mtime"] = mtime
        st.toast("🔄 Database reloaded!", icon="✅")
    return st.session_state["_engine"], st.session_state["_df"], st.session_state["_mtime"]

if "_engine" not in st.session_state:
    eng0, df0 = init_engine()
    st.session_state["_engine"] = eng0
    st.session_state["_df"] = df0
    st.session_state["_mtime"] = os.path.getmtime(DATA_PATH)

eng, df, mtime = reload_if_changed()

# =========================================
# SIDEBAR
# =========================================
with st.sidebar:
    st.caption(f"**Database last updated:** `{fmt_time(mtime)}`")
    st.divider()

    st.subheader("🌍 Environmental Data")
    countries = st.multiselect("Countries Visited", get_unique_values(df,"Countries Visited"), key="countries")
    anatomy = st.multiselect("Anatomy Involvement", get_unique_values(df,"Anatomy Involvement"), key="anatomy")
    vector = st.multiselect("Vector Exposure", get_unique_values(df,"Vector Exposure"), key="vector")

    st.subheader("🧬 Symptomatic Data")
    symptoms = st.multiselect("Symptoms", get_unique_values(df,"Symptoms"), key="symptoms")
    duration = st.multiselect("Duration of Illness", get_unique_values(df,"Duration of Illness"), key="duration")

    st.subheader("🧫 Laboratory Data")
    blood_film = st.selectbox("Blood Film Result", get_unique_values(df,"Blood Film Result"), key="blood_film")
    lft = st.selectbox("Liver Function Tests", get_unique_values(df,"Liver Function Tests"), key="lft")
    cysts_imaging = st.selectbox("Cysts on Imaging", get_unique_values(df,"Cysts on Imaging",extra=["None"]), key="cysts_imaging")
    neuro = st.selectbox("Neurological Involvement", get_unique_values(df,"Neurological Involvement"), key="neuro")
    eos = st.selectbox("Eosinophilia", get_unique_values(df,"Eosinophilia"), key="eos")
    fever = st.selectbox("Fever", get_unique_values(df,"Fever"), key="fever")
    diarrhea = st.selectbox("Diarrhea", get_unique_values(df,"Diarrhea"), key="diarrhea")
    bloody = st.selectbox("Bloody Diarrhea", get_unique_values(df,"Bloody Diarrhea"), key="bloody")
    stool = st.selectbox("Stool Cysts or Ova", get_unique_values(df,"Stool Cysts or Ova"), key="stool")
    anemia = st.selectbox("Anemia", get_unique_values(df,"Anemia"), key="anemia")
    ige = st.selectbox("High IgE Level", get_unique_values(df,"High IgE Level"), key="ige")

    st.subheader("🧩 Other")
    animal = st.multiselect("Animal Contact Type", get_unique_values(df,"Animal Contact Type"), key="animal")
    immune = st.selectbox("Immune Status", get_unique_values(df,"Immune Status"), key="immune")

    st.divider()
    colA,colB=st.columns(2)
    with colA:
        go=st.button("🔍 Analyze",use_container_width=True)
    with colB:
        if st.button("♻ Reset All",use_container_width=True):
            st.session_state["__RESET_ALL__"]=True
            st.rerun()

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
    results = results.merge(df[["Parasite","Group_filled"]],on="Parasite",how="left")
    results["Total Confidence (%)"] = (results["Score"] / FIXED_MAX_SCORE) * 100
    results["User Confidence (%)"] = results.apply(lambda r: compute_user_confidence(r,ui), axis=1)

    st.caption("🟢 **User Confidence** = match quality based only on entered fields · ⚪ **Total Confidence** = model-wide fit (all fields)")
    st.divider()

    grouped = []
    for g,sub in results.groupby("Group_filled",dropna=False):
        sub=sub.sort_values("Likelihood (%)",ascending=False)
        top=sub.iloc[0]
        grouped.append({
            "Group":int(g),
            "Name":GROUP_NAMES.get(int(g),"Group"),
            "Rows":sub.head(5).copy(),
            "Likelihood":float(top["Likelihood (%)"]),
            "UserConf":float(top["User Confidence (%)"]),
            "TotalConf":float(top["Total Confidence (%)"])
        })

    grouped=sorted(grouped,key=lambda x:x["Likelihood"],reverse=True)
    first=True
    for grp in grouped:
        c=pct_to_color(grp["Likelihood"])
        st.markdown(f"<h4>{grp['Name']} {pill(f'{grp['Likelihood']:.1f}% likely',c)}</h4>{progress_bar_html(grp['Likelihood'],c)}",unsafe_allow_html=True)
        with st.expander("Expand details",expanded=first):
            st.markdown(f"**User Confidence:** {grp['UserConf']:.1f}% · **Total Confidence:** {grp['TotalConf']:.1f}%")
            for _,r in grp["Rows"].iterrows():
                with st.expander(f"{r['Parasite']} · Subtype {r.get('Subtype','')}",expanded=first):
                    st.markdown(pill(f"{r['Likelihood (%)']:.1f}%",pct_to_color(r["Likelihood (%)"])),unsafe_allow_html=True)
                    st.markdown(f"- **User Confidence:** {r['User Confidence (%)']:.1f}%")
                    st.markdown(f"- **Total Confidence:** {r['Total Confidence (%)']:.1f}%")
            first=False
else:
    st.info("Enter data in the sidebar and click **Analyze**.")
