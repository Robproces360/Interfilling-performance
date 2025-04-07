import streamlit as st
import pandas as pd
import plotly.express as px
import os

# === PAGE CONFIG ===
st.set_page_config(page_title="OEE Dashboard - Interfilling", layout="wide")

# === CUSTOM STYLING ===
st.markdown(
    """
    <style>
        .stApp {
            background: linear-gradient(135deg, #e6f0ff, #99c2ff);
            color: #003366;
        }
        .st-bd, .st-c6, .st-cg {
            background-color: rgba(255, 255, 255, 0.8) !important;
            border-radius: 10px;
            padding: 10px;
        }
        .metric-label, .metric-value {
            color: #003366 !important;
        }
        .css-1kyxreq {
            background: linear-gradient(to bottom, #ffffff, #cce0ff);
        }
        .st-cq {
            border-left: 5px solid #ff9933 !important;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# === SETTINGS: pas hieronder jouw CSV-bestandspad aan ===
DATA_PATH = r"C:\Users\robde\OneDrive\Bureaublad\Interfilling\OEE tool\OEE_Dashboard_PowerBI_Finaal.csv"

# Check of het bestand wel bestaat
if not os.path.exists(DATA_PATH):
    st.error(f"❌ Bestand niet gevonden op:\n{DATA_PATH}")
    st.stop()

# === LOAD DATA ===
@st.cache_data
def load_data(path: str) -> pd.DataFrame:
    # 1. Lees ruwe CSV in met ; en \" als quote
    df_raw = pd.read_csv(
        path,
        sep=",",
        quotechar='"',
        skipinitialspace=True,
        encoding='utf-8'
    )
    # 2. Drop de eerste (lege) kolom
    df_raw = df_raw.drop(df_raw.columns[0], axis=1)

    # 3. Kolomnamen corrigeren
    df_raw.columns = [
        "jobId", "Ordernummer", "Workflow", "Verklaard_door",
        "Reden", "Opmerking", "Starttijd", "Stoptijd",
        "Duur_txt", "excludedFromProductivity", "subType", "Opties"
    ]

    # 4. Parse Starttijd / Stoptijd (formaat dd/mm/yy HH:MM:SS, dayfirst=True)
    df_raw["Starttijd"] = pd.to_datetime(df_raw["Starttijd"], format="%d/%m/%y %H:%M:%S", errors="coerce", dayfirst=True)
    df_raw["Stoptijd"]  = pd.to_datetime(df_raw["Stoptijd"],  format="%d/%m/%y %H:%M:%S", errors="coerce", dayfirst=True)

    # 5. Parse Duur (HH:MM:SS) -> seconden -> minuten
    df_raw["Duur_sec"] = pd.to_timedelta(df_raw["Duur_txt"], errors="coerce").dt.total_seconds()
    df_raw["Duur_min"] = df_raw["Duur_sec"] / 60.0

    # 6. Creëer kolom Datum
    df_raw["Datum"] = df_raw["Starttijd"].dt.date

    return df_raw

df = load_data(DATA_PATH)

# === SIDEBAR FILTERS ===
st.sidebar.title("🔍 Filters")

# Gewenste workflows (zonder spaties, in hoofdletters)
gewenste_workflows = ["VMPT1", "VMPT5", "COSMO"]

# Transformeer Workflow kolom -> VMPT5, COSMO etc.
df["Workflow"] = df["Workflow"].astype(str).str.upper().str.replace(" ", "")

# Bepaal dropdown
workflows = [w for w in df["Workflow"].unique() if w in gewenste_workflows]
workflow_options = ["Alle lijnen"] + sorted(workflows)
workflow_select = st.sidebar.selectbox("Kies workflow (machine):", options=workflow_options)

# Datumrange
if not df.empty and df["Datum"].notna().sum() > 0:
    min_datum = pd.to_datetime(df["Datum"]).min()
    max_datum = pd.to_datetime(df["Datum"]).max()
    date_range = st.sidebar.date_input(
        "Datum bereik:",
        value=(min_datum, max_datum),
        min_value=min_datum,
        max_value=max_datum
    )
else:
    st.warning("Geen geldige datumwaarden in dataset.")
    st.stop()

# === FILTERED DATA ===
df["Datum"] = pd.to_datetime(df["Datum"])  # ensure datetime
if workflow_select == "Alle lijnen":
    df_filtered = df[
        df["Workflow"].isin(workflows) &
        (df["Datum"] >= pd.to_datetime(date_range[0])) &
        (df["Datum"] <= pd.to_datetime(date_range[1]))
    ]
else:
    df_filtered = df[
        (df["Workflow"] == workflow_select) &
        (df["Datum"] >= pd.to_datetime(date_range[0])) &
        (df["Datum"] <= pd.to_datetime(date_range[1]))
    ]

# === KPI'S ===
st.title("📊 OEE Dashboard - Interfilling")
col1, col2, col3 = st.columns(3)

# Totale stilstand (uren) op basis van Duur_min
col1.metric("Totale stilstand (uren)", round(df_filtered["Duur_min"].sum() / 60, 2))
col2.metric("Aantal stilstanden", len(df_filtered))

# Langste stilstand (min)
max_stilstand = df_filtered["Duur_min"].max() if not df_filtered.empty else 0
col3.metric("Langste stilstand (min)", round(max_stilstand, 1))

# === CHART: Donut per subType ===
st.subheader("🔸 Verdeling stilstand per subType")
fig_donut = px.pie(df_filtered, names="subType", values="Duur_min", hole=0.5,
                   title="Verdeling stilstand per subType")
st.plotly_chart(fig_donut)

# === CHART: Staafgrafiek per reden ===
st.subheader("📉 Stilstand per reden")
df_reason = df_filtered.groupby("Reden")["Duur_min"].sum().sort_values(ascending=False).reset_index()
fig_bar = px.bar(df_reason, x="Reden", y="Duur_min", title="Stilstand per reden (minuten)")
st.plotly_chart(fig_bar)

# === CHART: Pareto Top 3 ===
st.subheader("🔧 Top 3 Langste stilstanden")
top3 = df_reason.head(3)
st.table(top3)

# === TOGGLE: PERIODE SELECTIE ===
st.sidebar.subheader("Analyse opties")
periode_selectie = st.sidebar.radio(
    "Selecteer periode voor analyse niet-geplande stilstand:",
    ["Dag", "Week", "Maand"]
)

# Voeg kolom Periode toe
if periode_selectie == "Dag":
    df_filtered["Periode"] = df_filtered["Datum"].dt.strftime("%Y-%m-%d")
elif periode_selectie == "Week":
    df_filtered["Week"] = df_filtered["Datum"].dt.isocalendar().week
    df_filtered["Jaar"] = df_filtered["Datum"].dt.year
    df_filtered["Periode"] = df_filtered["Jaar"].astype(str) + "-W" + df_filtered["Week"].astype(str)
else:
    df_filtered["Periode"] = df_filtered["Datum"].dt.to_period("M").astype(str)

# === Periodeoverzicht ===
st.subheader(f"📆 Niet-geplande stilstand per {periode_selectie.lower()}")
df_tijd = df_filtered.groupby("Periode")["Duur_min"].sum().reset_index()
fig_tijd = px.bar(df_tijd, x="Periode", y="Duur_min", title=f"Niet-geplande stilstand per {periode_selectie.lower()}")
st.plotly_chart(fig_tijd)

# === Pareto per geselecteerde periode en lijn ===
st.subheader(f"🔎 Pareto van Top 3 redenen per {periode_selectie.lower()} voor {workflow_select}")
periodes = df_filtered["Periode"].unique()
selected_periode = st.selectbox(f"Kies {periode_selectie.lower()}:", sorted(periodes))

df_pareto = df_filtered[df_filtered["Periode"] == selected_periode]
df_top = df_pareto.groupby("Reden")["Duur_min"].sum().sort_values(ascending=False).head(3).reset_index()
st.table(df_top)

# === FOOTER ===
st.markdown("---")
st.caption("Proces360° | Powered by Streamlit | rob@proces360.com")
