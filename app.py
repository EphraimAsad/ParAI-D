import streamlit as st
import pandas as pd
from engine import ParasiteIdentifier

# --- CONFIG ---
st.set_page_config(page_title="🦠 ParAI-D: Intelligent Parasite Diagnostic Assistant", layout="wide")

# --- LOAD DATA ---
@st.cache_data
def load_data():
    df = pd.read_excel("ParasiteMasterData.xlsx")
    df.columns = [c.strip() for c in df.columns]
    return df

df = load_data()
eng = ParasiteIdentifier(df)

# --- UTILITY: Extract unique dropdown values ---
def get_unique_values(column):
    vals = []
    for x in df[column].dropna().unique():
        parts = [v.strip() for v in str(x).split(";")]
        vals.extend(parts)
    vals = sorted(set([v for v in vals if v != ""]))
    vals.insert(0, "Unknown")
    return vals


# --- PAGE HEADER ---
st.title("🦠 ParAI-D")
st.markdown("### AI-assisted differential diagnosis for parasitic infections.")
st.markdown("Enter observed findings below. All fields default to **Unknown** — only fill what’s known. ParAI-D will infer the most probable parasites and suggest next diagnostic steps.")

st.divider()

# --- SIDEBAR ---
st.sidebar.header("⚙️ Input Settings")
st.sidebar.markdown("All entries are optional. Unknowns are ignored in scoring.")
if st.sidebar.button("Clear All Inputs"):
    st.session_state.clear()

# --- MAIN FORM ---
with st.form("parasite_form"):
    st.subheader("🌍 Epidemiological Information")
    col1, col2, col3 = st.columns(3)
    countries = col1.multiselect("Countries Visited", get_unique_values("Countries Visited"))
    anatomy = col2.multiselect("Anatomy Involvement", get_unique_values("Anatomy Involvement"))
    vector = col3.multiselect("Vector Exposure", get_unique_values("Vector Exposure"))

    st.subheader("🧬 Clinical Presentation")
    col1, col2 = st.columns(2)
    symptoms = col1.multiselect("Symptoms", get_unique_values("Symptoms"))
    duration = col2.multiselect("Duration of Illness", get_unique_values("Duration of Illness"))

    st.subheader("🐾 Exposure History")
    col1, col2 = st.columns(2)
    animal = col1.multiselect("Animal Contact Type", get_unique_values("Animal Contact Type"))
    immune = col2.selectbox("Immune Status", get_unique_values("Immune Status"))

    st.subheader("🧫 Laboratory Findings")
    col1, col2, col3 = st.columns(3)
    blood_film = col1.selectbox("Blood Film Result", get_unique_values("Blood Film Result"))
    lft = col2.selectbox("Liver Function Tests", get_unique_values("Liver Function Tests"))
    cysts_imaging = col3.selectbox("Cysts on Imaging", get_unique_values("Cysts on Imaging"))

    st.subheader("🧪 Systemic Markers")
    col1, col2, col3 = st.columns(3)
    neuro = col1.selectbox("Neurological Involvement", get_unique_values("Neurological Involvement"))
    eos = col2.selectbox("Eosinophilia", get_unique_values("Eosinophilia"))
    fever = col3.selectbox("Fever", get_unique_values("Fever"))

    col1, col2, col3 = st.columns(3)
    diarrhea = col1.selectbox("Diarrhea", get_unique_values("Diarrhea"))
    bloody = col2.selectbox("Bloody Diarrhea", get_unique_values("Bloody Diarrhea"))
    stool = col3.selectbox("Stool Cysts or Ova", get_unique_values("Stool Cysts or Ova"))

    col1, col2, col3 = st.columns(3)
    anemia = col1.selectbox("Anemia", get_unique_values("Anemia"))
    igE = col2.selectbox("High IgE Level", get_unique_values("High IgE Level"))

    st.divider()

    submitted = st.form_submit_button("🔍 Analyze")

# --- BUILD INPUT DICTIONARY ---
if submitted:
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
        "High IgE Level": [igE],
        "Cysts on Imaging": [cysts_imaging],
    }

    st.divider()
    st.subheader("🧠 Diagnostic Inference")

    results = eng.score_entry(user_inputs)

    # Display top 10 parasites
    st.dataframe(
        results[["Parasite", "Likelihood (%)", "Group", "Subtype", "Key Test"]].head(10),
        use_container_width=True,
        hide_index=True
    )

    # Optional: visualize top 5
    st.bar_chart(results.head(5).set_index("Parasite")["Likelihood (%)"])
