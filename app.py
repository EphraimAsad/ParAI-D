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
FIXED_MAX_SCORE = 113  # Maximum total possible test weight

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
# UTILITIES
# -----------------------------
def fmt_time(ts):
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    except Exception:
        return "Unknown"


@st.cache_data(show_spinner=False)
def load_data_with_mtime(path: str):
    """Load Excel and return (df, mtime). Cache busts when path or mtime changes."""
    mtime = os.path.getmtime(path)
    df = pd.read_excel(path)
    df.columns = [c.strip() for c in df.columns]
    return df, mtime


def get_unique_values(df: pd.DataFrame, column: str):
    vals = []
    for x in df[column].dropna().unique():
        for part in str(x).split(";"):
            part = part.strip()
            if part:
                vals.append(part)
    vals = sorted(set(vals))
    vals.insert(0, "Unknown")
    return vals


def pct_to_color(pct: float) -> str:
    """Map 0–100% to red→amber→green gradient."""
    pct = max(0.0, min(100.0, pct)) / 100.0
    r = int(255 * (1 - pct))
    g = int(150 + 105 * pct)
    b = int(60 * (1 - pct))
    return f"#{r:02x}{g:02x}{b:02x}"


def pill(text: str, color_hex: str):
    return f"""
    <span style="
        display:inline-block;
        padding:4px 10px;
        border-radius:999px;
        background:{color_hex};
        color:white;
        font-weight:600;
        font-size:12px;">
        {text}
    </span>
    """


def progress_bar_html(percent: float, color_hex: str):
    return f"""
    <div style="background:#ddd; height:6px; border-radius:999px; overflow:hidden; margin-top:6px;">
        <div style="width:{percent:.1f}%; background:{color_hex}; height:100%;"></div>
    </div>
    """


def generate_reasoning(row, user_input):
    """Simple interpretive reasoning summary."""
    highlights = []

    def mlist(field):
        return [s.strip().lower() for s in str(row.get(field, "Unknown")).split(";")]

    if any(x.lower() in mlist("Vector Exposure") for x in user_input.get("Vector Exposure", [])):
        highlights.append("Vector exposure aligns")
    if any(x.lower() in mlist("Anatomy Involvement") for x in user_input.get("Anatomy Involvement", [])):
        highlights.append("Organ involvement matches")
    if any(x.lower() in mlist("Countries Visited") for x in user_input.get("Countries Visited", [])):
        highlights.append("Geography consistent")
    if user_input.get("Eosinophilia", ["Unknown"])[0].lower() in mlist("Eosinophilia"):
        highlights.append("Eosinophilia pattern fits")
    if user_input.get("Blood Film Result", ["Unknown"])[0].lower() in mlist("Blood Film Result"):
        highlights.append("Blood film result supportive")
    if user_input.get("Cysts on Imaging", ["Unknown"])[0].lower() in mlist("Cysts on Imaging"):
        highlights.append("Imaging pattern consistent")

    if not highlights:
        return "Few direct matches; alignment primarily partial or indirect."
    return " / ".join(highlights) + "."


def compare_with_runner_up(top_row, runner_row):
    """Key difference summary for top 2 within a group."""
    diffs = []
    fields = [
        "Vector Exposure", "Anatomy Involvement", "Countries Visited",
        "Eosinophilia", "Blood Film Result", "Cysts on Imaging", "Symptoms"
    ]
    for f in fields:
        a = str(top_row.get(f, "")).lower()
        b = str(runner_row.get(f, "")).lower()
        if a != b:
            diffs.append(f)
    if not diffs:
        return "Very similar overall pattern to next candidate."
    return "Key differentiators vs #2: " + ", ".join(diffs[:5]) + ("." if len(diffs) <= 5 else ", …")


# -----------------------------
# DATA LOADING (auto-reload)
# -----------------------------
df, mtime = load_data_with_mtime(DATA_PATH)

# Add group fallback column
df["Group"] = pd.to_numeric(df.get("Group"), errors="coerce")
df["Group_filled"] = df["Group"].fillna(-1)

if "db_mtime" not in st.session_state:
    st.session_state["db_mtime"] = mtime
elif mtime != st.session_state["db_mtime"]:
    st.session_state["db_mtime"] = mtime
    load_data_with_mtime.clear()
    st.experimental_rerun()

eng = ParasiteIdentifier(df)

# -----------------------------
# SIDEBAR INPUTS
# -----------------------------
with st.sidebar:
    st.markdown("### 📦 Database Info")
    st.caption(f"**ParasiteMasterData.xlsx** last updated: `{fmt_time(mtime)}`")
    st.divider()
    st.header("⚙️ Input Parameters")

    def multisel(label, col):
        return st.multiselect(label, get_unique_values(df, col))

    def selbox(label, col):
        return st.selectbox(label, get_unique_values(df, col), index=0)

    countries = multisel("Countries Visited", "Countries Visited")
    anatomy = multisel("Anatomy Involvement", "Anatomy Involvement")
    vector = multisel("Vector Exposure", "Vector Exposure")

    st.markdown("---")
    symptoms = multisel("Symptoms", "Symptoms")
    duration = st.multiselect("Duration of Illness", get_unique_values(df, "Duration of Illness"))

    st.markdown("---")
    animal = st.multiselect("Animal Contact Type", get_unique_values(df, "Animal Contact Type"))
    immune = selbox("Immune Status", "Immune Status")

    st.markdown("---")
    blood_film = selbox("Blood Film Result", "Blood Film Result")
    lft = selbox("Liver Function Tests", "Liver Function Tests")
    cysts_imaging = selbox("Cysts on Imaging", "Cysts on Imaging")

    neuro = selbox("Neurological Involvement", "Neurological Involvement")
    eos = selbox("Eosinophilia", "Eosinophilia")
    fever = selbox("Fever", "Fever")
    diarrhea = selbox("Diarrhea", "Diarrhea")
    bloody = selbox("Bloody Diarrhea", "Bloody Diarrhea")
    stool = selbox("Stool Cysts or Ova", "Stool Cysts or Ova")
    anemia = selbox("Anemia", "Anemia")
    ige = selbox("High IgE Level", "High IgE Level")

    st.markdown("---")
    go = st.button("🔍 Analyze", use_container_width=True)

# -----------------------------
# MAIN OUTPUT AREA
# -----------------------------
st.title("🦠 ParAI-D")
st.caption("AI-assisted differential diagnosis for parasitic infections.")
st.divider()

if go:
    # Prepare inputs
    user_inputs = {
        "Countries Visited": countries if countries else ["Unknown"],
        "Anatomy Involvement": anatomy if anatomy else ["Unknown"],
        "Vector Exposure": vector if vector else ["Unknown"],
        "Symptoms": symptoms if symptoms else ["Unknown"],
        "Duration of Illness": duration if duration else ["Unknown"],
        "Animal Contact Type": animal if animal else ["Unknown"],
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

    # Run engine
    results = eng.score_entry(user_inputs)
    results["Total Confidence (%)"] = (results["Score"] / FIXED_MAX_SCORE) * 100

    # Attach group mapping
    results = results.merge(df[["Parasite", "Group_filled"]], on="Parasite", how="left")

    grouped = []
    for g, sub in results.groupby("Group_filled", dropna=False):
        sub = sub.sort_values("Likelihood (%)", ascending=False)
        top = sub.iloc[0]
        group_name = GROUP_NAMES.get(int(g), f"Group {g}")
        grouped.append({
            "Group": int(g),
            "Group Name": group_name,
            "Top Rows": sub.head(5).copy(),
            "Group Likelihood": float(top["Likelihood (%)"]),
            "User Confidence": float(top["Likelihood (%)"]),
            "Total Confidence": float(top["Total Confidence (%)"]),
        })

    grouped = sorted(grouped, key=lambda x: x["Group Likelihood"], reverse=True)

    # -----------------------------
    # Render each group block
    # -----------------------------
    for gbloc in grouped:
        color = pct_to_color(gbloc["Group Likelihood"])
        chip = pill(f"{gbloc['Group Likelihood']:.1f}% likely", color)
        prog = progress_bar_html(gbloc["Group Likelihood"], color)

        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:12px;margin:8px 0 2px 0;">
                <div style="font-size:20px;font-weight:700;line-height:1.2;">
                    {gbloc['Group Name']}
                </div>
                {chip}
            </div>
            {prog}
            """,
            unsafe_allow_html=True,
        )

        with st.expander("Expand group details", expanded=False):
            st.markdown(
                f"**User Confidence:** {gbloc['User Confidence']:.1f}%  |  "
                f"**Total Confidence:** {gbloc['Total Confidence']:.1f}%"
            )

            top_rows = gbloc["Top Rows"]
            if len(top_rows) >= 2:
                cmp_txt = compare_with_runner_up(top_rows.iloc[0], top_rows.iloc[1])
                st.markdown(f"**Comparison to similar values/subtypes:** {cmp_txt}")
            else:
                st.markdown("**Comparison to similar values/subtypes:** Not enough candidates in this group.")
            st.markdown("---")
            st.markdown("#### Species in this group")

            for _, row in top_rows.iterrows():
                sp_color = pct_to_color(row["Likelihood (%)"])
                sp_chip = pill(f"{row['Likelihood (%)']:.1f}%", sp_color)
                st.markdown(
                    f"**{row['Parasite']}** {sp_chip}  ·  Subtype: {row.get('Subtype', '')}",
                    unsafe_allow_html=True,
                )
                reason = generate_reasoning(row, user_inputs)
                st.markdown(f"- **Reasoning:** {reason}")
                kt = str(row.get("Key Test", "")).strip()
                if kt:
                    st.markdown(f"- **Key tests:** {kt}")
                st.markdown(
                    f"- **User Confidence:** {row['Likelihood (%)']:.1f}%"
                    f"  ·  **Total Confidence:** {row['Total Confidence (%)']:.1f}%"
                )
                st.markdown(" ")

            st.markdown(" ")

        st.markdown("---")

else:
    st.info("Use the sidebar to enter parameters and click **Analyze** to generate results.")

# -----------------------------
# FOOTER
# -----------------------------
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
