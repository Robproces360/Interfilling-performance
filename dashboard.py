# File: dashboard.py (Versie 2025-05-02, Incl. Order Target Calculator)

import streamlit as st
import pandas as pd
import plotly.express as px
import os
import datetime
import numpy as np # Nodig voor mean/std in performance

# === CONSTANTEN ===
DATA_PATH_DOWNTIME = "OEE_Dashboard_PowerBI_Finaal.csv"
DATA_PATH_ORDER = "Motivate  Performance.csv" # Pad naar order data
GEWENSTE_WORKFLOWS = ["VMPT1", "VMPT5", "COSMO"] # Workflows voor downtime analyse
SHIFT_START_TIME = datetime.time(7, 30)
SHIFT_END_TIME = datetime.time(16, 0)
PERFORMANCE_SHIFT_MINUTES = 8 * 60
# Filters en Top N instellingen
UITGESLOTEN_REDENEN_KEYWORDS = ['Pauze'] # Voor downtime reden analyse
TOP_N_IN_BARCHART = 10
TOP_N_IN_DONUT = 5
# Instelling voor Order Target Calculator
EFFECTIVE_CAPACITY = 19.6 # Stuks per minuut

# === PAGE CONFIG ===
st.set_page_config(page_title="Interfilling OEE Analyse", layout="wide")

# === HEADER ===
st.title("📊 Interfilling Dashboard") # Algemenere titel?
st.caption("Dashboard door www.proces360.com | rob@proces360.com")
st.markdown("---")

# === DATA LAAD FUNCTIE (Downtime) ===
@st.cache_data
def load_data(path: str) -> pd.DataFrame:
    """Laadt en voorbewerkt de downtime data."""
    if not os.path.exists(path): st.error(f"❌ Downtime bestand niet gevonden: {path}"); st.stop(); return pd.DataFrame()
    try:
        df = pd.read_csv(path, sep=",", quotechar='"', skipinitialspace=True, encoding="utf-8")
        if 'Unnamed: 0' in df.columns: df = df.drop('Unnamed: 0', axis=1)
        expected_cols_len = 12
        if len(df.columns) == expected_cols_len:
            df.columns = ["jobId", "Ordernummer", "Workflow", "Verklaard_door", "Reden", "Opmerking", "Starttijd", "Stoptijd", "Duur_txt", "excludedFromProductivity", "subType", "Opties"]
        else: st.error(f"Onverwacht aantal kolommen ({len(df.columns)}) in {path}."); st.stop(); return pd.DataFrame()
        df["Starttijd_dt"] = pd.to_datetime(df["Starttijd"], format="%d/%m/%y %H:%M:%S", errors="coerce", dayfirst=True)
        df["Stoptijd_dt"]  = pd.to_datetime(df["Stoptijd"], format="%d/%m/%y %H:%M:%S", errors="coerce", dayfirst=True)
        start_errors = df["Starttijd_dt"].isna().sum(); stop_errors = df["Stoptijd_dt"].isna().sum()
        if start_errors > 0 or stop_errors > 0: st.warning(f"Let op: {start_errors} Starttijd(en) en {stop_errors} Stoptijd(en) konden niet gelezen worden.")
        df["Duur_calc"] = (df["Stoptijd_dt"] - df["Starttijd_dt"]); df["Duur_sec"] = df["Duur_calc"].dt.total_seconds()
        neg_dur_count = (df["Duur_sec"] < 0).sum()
        if neg_dur_count > 0: st.warning(f"Let op: {neg_dur_count} rijen met negatieve duur genegeerd."); df = df[df["Duur_sec"] >= 0]
        df["Duur_min"] = df["Duur_sec"] / 60.0
        df["Datum"] = df["Starttijd_dt"].dt.date
        df["Workflow"] = df["Workflow"].astype(str).str.upper().str.replace(" ", "")
        df['Reden'] = df['Reden'].fillna('Onbekend').astype(str).str.strip()
        df.dropna(subset=["Starttijd_dt", "Datum", "Duur_min", "Reden"], inplace=True)
        return df
    except Exception as e: st.error(f"Fout bij laden downtime data: {path}."); st.exception(e); st.stop(); return pd.DataFrame()

# === NIEUW: DATA LAAD FUNCTIE (Order Performance) ===
@st.cache_data
def load_order_data(path: str) -> pd.DataFrame:
    """Laadt en voorbewerkt de order performance data."""
    if not os.path.exists(path):
        st.error(f"❌ Order bestand niet gevonden: {path}")
        # Geef leeg dataframe terug ipv st.stop() zodat de app niet crasht als alleen dit bestand mist
        return pd.DataFrame()
    try:
        # --- BELANGRIJK: Deze read_csv is ongetest door de tool ---
        # Controleer lokaal of het pad, sep=',' en skipinitialspace=True correct zijn.
        # Mogelijk moet je quotechar='"' of encoding toevoegen.
        df = pd.read_csv(path, sep=',', engine='python', skipinitialspace=True)
        st.success(f"Bestand {path} succesvol ingelezen (in theorie).") # Feedback

        # --- Kolom Selectie & Hernoemen (pas aan indien nodig) ---
        # Kolommen die we nodig hebben op basis van screenshot
        required_cols = ['Date', 'Work Center', 'WO #', 'Item', 'Build Qty']
        # Check of alle benodigde kolommen bestaan
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            st.error(f"De volgende vereiste kolommen missen in {path}: {', '.join(missing_cols)}")
            return pd.DataFrame()

        # Selecteer en hernoem
        df_selected = df[required_cols].copy()
        df_selected.rename(columns={'Work Center': 'Line', 'Build Qty': 'Quantity'}, inplace=True)

        # --- Data Type Conversie & Cleaning ---
        df_selected['Quantity'] = pd.to_numeric(df_selected['Quantity'], errors='coerce')
        # Converteer Datum indien nodig (pas format aan als het niet standaard is)
        try:
            df_selected['Date'] = pd.to_datetime(df_selected['Date'], errors='coerce')
        except Exception as date_err:
            st.warning(f"Kon 'Date' kolom niet converteren naar datum: {date_err}. Controleer het formaat.")

        # Verwijder rijen waar essentiële data (Line, Quantity) mist
        rows_before = len(df_selected)
        df_selected.dropna(subset=['Line', 'Quantity'], inplace=True)
        rows_after = len(df_selected)
        if rows_before > rows_after:
             st.info(f"{rows_before - rows_after} rijen verwijderd uit order data ivm missende Line/Quantity.")

        # Hernoem Line naar string om zeker te zijn
        df_selected['Line'] = df_selected['Line'].astype(str)

        return df_selected

    except FileNotFoundError:
         # Extra check, hoewel de check bovenaan dit al zou moeten vangen
         st.error(f"Kon bestand niet vinden (check pad): {path}")
         return pd.DataFrame()
    except Exception as e:
        st.error(f"Fout bij het laden of verwerken van order data: {path}.")
        st.exception(e) # Toon details van de fout
        return pd.DataFrame()


# === SIDEBAR FUNCTIE ===
def create_sidebar(df_downtime: pd.DataFrame, df_orders: pd.DataFrame) -> tuple:
    """Creëert de sidebar elementen en retourneert de selecties."""
    # --- Algemene Opties ---
    st.sidebar.title("Dashboard Opties")
    dashboard_choice = st.sidebar.radio("Kies dashboard:", ["Downtime Analyse", "Order Target Calculator"], key="dashboard_choice")

    # --- Filters voor Downtime Analyse ---
    st.sidebar.title("🔍 Filters (Downtime)")
    # Workflow filter (downtime)
    workflows_in_data = sorted([w for w in df_downtime["Workflow"].unique() if w in GEWENSTE_WORKFLOWS]) if not df_downtime.empty else []
    workflow_options = ["Alle lijnen"] + workflows_in_data
    workflow_select = st.sidebar.selectbox("Kies workflow (machine):", options=workflow_options, key="downtime_workflow_filter")
    # Datum filter (downtime)
    min_datum_dt = pd.to_datetime(df_downtime["Datum"]).min() if not df_downtime.empty else None
    max_datum_dt = pd.to_datetime(df_downtime["Datum"]).max() if not df_downtime.empty else None
    if pd.isna(min_datum_dt) or pd.isna(max_datum_dt):
         # st.sidebar.warning("Kan geen geldig datumbereik vinden voor downtime.")
         today = datetime.date.today(); default_start = today - datetime.timedelta(days=30); default_end = today
         date_range = st.sidebar.date_input("Datum bereik (Downtime):", value=(default_start, default_end), key="downtime_date_filter")
    else:
        min_datum = min_datum_dt.date(); max_datum = max_datum_dt.date()
        default_start = max(min_datum, max_datum - datetime.timedelta(days=30)); default_end = max_datum
        date_range = st.sidebar.date_input("Datum bereik (Downtime):", value=(default_start, default_end), min_value=min_datum, max_value=max_datum, key="downtime_date_filter")
    # Periode selectie (downtime)
    periode_selectie = st.sidebar.radio("Groepeer downtime per:", ["Dag", "Week", "Maand"], key="downtime_period_filter", horizontal=True)
    # Shift filter (downtime)
    apply_shift_filter_toggle = st.sidebar.toggle("Alleen downtime tijdens shift", value=True, key="downtime_shift_toggle")

    # --- Filters voor Order Target Calculator ---
    st.sidebar.title("🕒 Filters (Order Calc)")
    selected_order_line = None # Default
    if not df_orders.empty and 'Line' in df_orders.columns:
        lines_order = sorted(df_orders["Line"].dropna().unique().tolist())
        order_line_options = ["Alle lijnen"] + lines_order
        selected_order_line = st.sidebar.selectbox("Kies lijn (Order Calc):", options=order_line_options, key="order_line_filter")
    else:
         st.sidebar.caption("Geen order data geladen om op lijn te filteren.")

    return (dashboard_choice, workflow_select, date_range, periode_selectie, apply_shift_filter_toggle,
            selected_order_line) # Return order filter


# === FILTER DATA FUNCTIE (Downtime) ===
def filter_data(df: pd.DataFrame, workflow_select: str, date_range: tuple, apply_shift_filter: bool) -> pd.DataFrame:
    """Filtert de downtime dataframe op basis van selecties."""
    df_filtered = df.copy()
    if not date_range or len(date_range) != 2 or date_range[0] is None or date_range[1] is None:
        st.error("Ongeldig datumbereik geselecteerd."); return pd.DataFrame()
    start_date = pd.to_datetime(date_range[0]); end_date = pd.to_datetime(date_range[1])
    df_filtered["Datum"] = pd.to_datetime(df_filtered["Datum"])
    mask_date = (df_filtered["Datum"] >= start_date) & (df_filtered["Datum"] <= end_date)
    df_filtered = df_filtered[mask_date]
    if workflow_select != "Alle lijnen": df_filtered = df_filtered[df_filtered["Workflow"] == workflow_select]
    else: df_filtered = df_filtered[df_filtered["Workflow"].isin(GEWENSTE_WORKFLOWS)]
    if apply_shift_filter:
        mask_shift = ((df_filtered["Starttijd_dt"].dt.weekday < 5) & (df_filtered["Starttijd_dt"].dt.time >= SHIFT_START_TIME) & (df_filtered["Starttijd_dt"].dt.time < SHIFT_END_TIME))
        df_filtered = df_filtered[mask_shift]
    return df_filtered

# === DISPLAY FUNCTIES (Downtime Analyse) ===

def MaakKengetallenZichtbaar(df_filtered: pd.DataFrame):
    """Toont de Key Performance Indicators (KPIs) in kolommen."""
    st.subheader("📈 Kerncijfers") # Emoji kan helpen
    col1, col2, col3 = st.columns(3)
    if df_filtered.empty:
        col1.metric("Totale stilstand (uren)", "N/A"); col2.metric("Aantal stilstanden", 0); col3.metric("Langste stilstand (min)", "N/A")
    else:
        total_downtime_hrs = df_filtered["Duur_min"].sum() / 60; col1.metric("Totale stilstand (uren)", f"{total_downtime_hrs:.2f}")
        col2.metric("Aantal stilstanden", len(df_filtered)); max_stilstand = df_filtered["Duur_min"].max()
        col3.metric("Langste stilstand (min)", f"{max_stilstand:.1f}" if pd.notna(max_stilstand) else "N/A")

def display_tabbed_line_analysis(data_om_te_tonen):
    """Toont per lijn (in tabs) een staafdiagram en een donut+legenda."""
    st.subheader("📊 Analyse Stilstandsredenen per Lijn")
    lijnen_in_data = sorted([w for w in data_om_te_tonen["Workflow"].unique() if w in GEWENSTE_WORKFLOWS])
    tab_namen = ["Alle lijnen"] + lijnen_in_data
    tabs = st.tabs(tab_namen)
    color_sequence = px.colors.qualitative.Plotly

    for i, lijn_naam in enumerate(tab_namen):
        with tabs[i]:
            if lijn_naam == "Alle lijnen": data_voor_deze_lijn = data_om_te_tonen
            else: data_voor_deze_lijn = data_om_te_tonen[data_om_te_tonen["Workflow"] == lijn_naam]
            if data_voor_deze_lijn.empty: st.caption("Geen data beschikbaar."); continue

            data_gefilterd = data_voor_deze_lijn.copy(); filter_applied_info = []
            if UITGESLOTEN_REDENEN_KEYWORDS:
                mask_exclude = pd.Series(False, index=data_gefilterd.index)
                for keyword in UITGESLOTEN_REDENEN_KEYWORDS: mask_exclude |= data_gefilterd['Reden'].str.contains(keyword, case=False, na=False)
                rows_before = len(data_gefilterd); data_gefilterd = data_gefilterd[~mask_exclude]; rows_after = len(data_gefilterd)
                if rows_before > rows_after: filter_applied_info.append(f"{rows_before - rows_after} rijen met '{', '.join(UITGESLOTEN_REDENEN_KEYWORDS)}' verwijderd")
            if filter_applied_info: st.caption(f"Filter info: {'; '.join(filter_applied_info)}.", help="...")

            if data_gefilterd.empty or data_gefilterd["Duur_min"].sum() < 0.1: st.caption("Geen relevante data na filter."); continue

            df_reason_agg = data_gefilterd.groupby("Reden")["Duur_min"].sum().reset_index()
            df_reason_agg = df_reason_agg[df_reason_agg['Reden'] != ''].sort_values(by="Duur_min", ascending=False)
            totaal_duur_relevant = df_reason_agg["Duur_min"].sum()
            if totaal_duur_relevant > 0: df_reason_agg['percentage_totaal'] = (df_reason_agg['Duur_min'] / totaal_duur_relevant) * 100
            else: df_reason_agg['percentage_totaal'] = 0.0

            all_reasons_sorted = df_reason_agg['Reden'].tolist()
            color_map = {reason: color_sequence[i % len(color_sequence)] for i, reason in enumerate(all_reasons_sorted)}
            overig_label = f'Overige ({max(0, len(df_reason_agg) - TOP_N_IN_DONUT)})'
            color_map[overig_label] = '#bdbdbd'

            col_bar, col_donut_leg = st.columns(2)
            with col_bar:
                st.markdown(f"**Top {TOP_N_IN_BARCHART} Redenen (Staafdiagram)**")
                df_bar_display = df_reason_agg.head(TOP_N_IN_BARCHART).copy(); df_bar_display['percentage'] = df_bar_display['percentage_totaal']
                if df_bar_display.empty: st.caption("Geen data.")
                else:
                    try:
                        fig_bar = px.bar(df_bar_display, x="Duur_min", y="Reden", orientation='h', labels={"Duur_min": "Duur (min)", "Reden": ""}, text="Duur_min", color="Reden", color_discrete_map=color_map)
                        fig_bar.update_layout(showlegend=False, yaxis={'categoryorder':'total ascending'}, height=max(350, len(df_bar_display) * 28), margin=dict(l=10, r=10, t=10, b=10))
                        fig_bar.update_traces(texttemplate='%{text:.0f}', textposition='outside', hovertemplate="<b>%{y}</b><br>Duur: %{x:.1f} min<br>Percentage: %{customdata[0]:.1f}%<extra></extra>", customdata=df_bar_display[['percentage']])
                        st.plotly_chart(fig_bar, use_container_width=True)
                    except Exception as e: st.error("Kon staafdiagram niet maken."); st.exception(e)
            with col_donut_leg:
                st.markdown(f"**Top {TOP_N_IN_DONUT} + Overig (Donut)**")
                overig_duur = 0.0; df_donut_data = pd.DataFrame()
                if len(df_reason_agg) > TOP_N_IN_DONUT:
                    df_top_n_donut = df_reason_agg.head(TOP_N_IN_DONUT).copy()
                    if len(df_reason_agg) > TOP_N_IN_DONUT: overig_duur = float(df_reason_agg.iloc[TOP_N_IN_DONUT:]['Duur_min'].sum())
                    if overig_duur > 0.01:
                        df_overig = pd.DataFrame([{'Reden': overig_label, 'Duur_min': overig_duur}])
                        if isinstance(df_top_n_donut, pd.DataFrame) and isinstance(df_overig, pd.DataFrame):
                           try: df_donut_data = pd.concat([df_top_n_donut, df_overig], ignore_index=True)
                           except ValueError as ve: st.error(f"Concat Fout: {ve}"); df_donut_data = df_top_n_donut
                        else: df_donut_data = df_top_n_donut
                    else: df_donut_data = df_top_n_donut
                else: df_donut_data = df_reason_agg.copy()

                if not df_donut_data.empty and totaal_duur_relevant > 0:
                    df_donut_data['percentage'] = (df_donut_data['Duur_min'] / totaal_duur_relevant) * 100
                    top_3_legenda = df_reason_agg.head(3).copy()
                    try:
                        fig_donut = px.pie(df_donut_data, names="Reden", values="Duur_min", hole=0.45, color="Reden", color_discrete_map=color_map)
                        fig_donut.update_traces(textinfo='percent', textfont_size=11, hovertemplate = "<b>%{label}</b><br>Duur: %{value:.1f} min<br>Percentage: %{percent:.1%}<extra></extra>")
                        fig_donut.update_layout(showlegend=False, margin=dict(l=10, r=10, t=10, b=10), height=250)
                        st.plotly_chart(fig_donut, use_container_width=True)
                        st.markdown("**Top 3 Details:**")
                        if top_3_legenda.empty: st.caption("Geen top redenen.")
                        else:
                            for idx in range(len(top_3_legenda)):
                                 row = top_3_legenda.iloc[idx]; color = color_map.get(row['Reden'], '#808080'); display_reden = row['Reden'][:30] + '...' if len(row['Reden']) > 30 else row['Reden']
                                 st.markdown(f"<div style='margin-bottom: 4px; text-align: left;' title='{row['Reden']}'><span style='display: inline-block; width: 10px; height: 10px; background-color: {color}; margin-right: 5px; vertical-align: middle; border: 1px solid #ccc;'></span><span style='font-size: 0.9em; vertical-align: middle;'><b>{display_reden}</b></span><br><span style='font-size: 0.8em; padding-left: 15px;'>{row['percentage_totaal']:.1f}% ({row['Duur_min']:.0f} min)</span></div>", unsafe_allow_html=True)
                    except Exception as e: st.error("Kon donut/legenda niet maken."); st.exception(e)
                else: st.caption("Geen data voor donut.")

def display_period_analysis(df_filtered: pd.DataFrame, periode_selectie: str):
     """Toont de totale stilstand gegroepeerd per geselecteerde periode."""
     st.subheader(f"📆 Trend Niet-geplande stilstand")
     df_analysis = df_filtered.copy()
     try:
          if periode_selectie == "Dag": df_analysis["Periode"] = df_analysis["Starttijd_dt"].dt.strftime("%Y-%m-%d")
          elif periode_selectie == "Week": df_analysis["Periode"] = df_analysis["Starttijd_dt"].dt.strftime('%Y-W%V')
          else: df_analysis["Periode"] = df_analysis["Starttijd_dt"].dt.to_period("M").astype(str)
     except AttributeError as ae: st.error(f"Fout bij bepalen periode: {ae}"); return
     df_tijd = df_analysis.groupby("Periode")["Duur_min"].sum().reset_index()
     if df_tijd.empty: st.caption(f"Geen data per {periode_selectie.lower()}."); return
     df_tijd = df_tijd.sort_values("Periode")
     try:
          fig_tijd = px.bar(df_tijd, x="Periode", y="Duur_min", title=f"Totale Stilstand (min) per {periode_selectie.lower()}", labels={"Duur_min": "Stilstand (min)"})
          if len(df_tijd) > 15: fig_tijd.update_xaxes(tickangle=45)
          st.plotly_chart(fig_tijd, use_container_width=True)
     except Exception as e: st.error(f"Kon periode grafiek niet maken."); st.exception(e)

def display_order_analysis(df_filtered: pd.DataFrame):
    """Toont analyses gerelateerd aan orders uit downtime data."""
    st.subheader("📦 Analyse per Order (Downtime)")
    if df_filtered.empty: st.caption("Geen data."); return

    st.markdown("**Top 3 Orders (Totale Stilstand):**")
    try:
        df_order_downtime = (df_filtered.groupby("Ordernummer")["Duur_min"].sum().sort_values(ascending=False).head(3).reset_index())
        if not df_order_downtime.empty:
             df_order_downtime.index = range(1, len(df_order_downtime) + 1)
             st.dataframe(df_order_downtime.rename(columns={"Duur_min": "Totale Stilstand (min)"}), use_container_width=True, column_config={"Totale Stilstand (min)": st.column_config.NumberColumn(format="%.1f")})
             top_orders_list = df_order_downtime["Ordernummer"].tolist()
        else: st.caption("Geen orders gevonden."); top_orders_list = []
    except Exception as e: st.error("Berekening mislukt."); st.exception(e); top_orders_list = []

    st.markdown("---")
    st.markdown("**Langste Enkele Stilstand per Top 3 Order:**")
    if not top_orders_list: st.caption("Geen top orders gevonden.")
    else:
        try:
            df_top_events = df_filtered[df_filtered["Ordernummer"].isin(top_orders_list)].copy()
            if not df_top_events.empty:
                 idx = df_top_events.loc[df_top_events.groupby("Ordernummer")["Duur_min"].idxmax()].index
                 df_longest_events = df_top_events.loc[idx]
                 df_longest_display = df_longest_events[["Ordernummer", "Starttijd_dt", "Stoptijd_dt", "Duur_min", "Reden"]].copy()
                 df_longest_display.rename(columns={"Starttijd_dt": "Start", "Stoptijd_dt": "Stop", "Duur_min": "Duur (min)"}, inplace=True)
                 st.dataframe(df_longest_display, use_container_width=True, column_config={"Start": st.column_config.DatetimeColumn(format="DD-MM-YY HH:mm"), "Stop": st.column_config.DatetimeColumn(format="DD-MM-YY HH:mm"), "Duur (min)": st.column_config.NumberColumn(format="%.1f")})
            else: st.caption("Geen stilstanden voor top 3 orders.")
        except Exception as e: st.error("Berekening mislukt."); st.exception(e)

    st.markdown("---")
    st.markdown("**Top 3 Orders per Werkdag (Ma-Vr):**")
    try:
        df_daily_analysis = df_filtered.copy()
        if 'Starttijd_dt' not in df_daily_analysis.columns: st.error("'Starttijd_dt' kolom mist."); return
        weekday_map = {0: 'Maandag', 1: 'Dinsdag', 2: 'Woensdag', 3: 'Donderdag', 4: 'Vrijdag'}
        df_daily_analysis['Weekdag'] = df_daily_analysis['Starttijd_dt'].dt.weekday.map(weekday_map)
        if 'Weekdag' in df_daily_analysis.columns:
             df_daily_analysis = df_daily_analysis[df_daily_analysis['Starttijd_dt'].dt.weekday < 5]
             werkdagen = ['Maandag', 'Dinsdag', 'Woensdag', 'Donderdag', 'Vrijdag']
             for dag in werkdagen:
                 df_dag = df_daily_analysis[df_daily_analysis['Weekdag'] == dag]
                 if df_dag.empty: continue
                 st.markdown(f"**{dag}:**")
                 df_top_dag = (df_dag.groupby('Ordernummer')['Duur_min'].sum().sort_values(ascending=False).head(3).reset_index())
                 if df_top_dag.empty: st.caption("Geen data."); continue
                 df_reason_order = (df_dag.groupby(['Ordernummer', 'Reden'])['Duur_min'].sum().reset_index())
                 if not df_reason_order.empty:
                      idx_res = df_reason_order.loc[df_reason_order.groupby('Ordernummer')['Duur_min'].idxmax()]
                      df_top_reason = idx_res[['Ordernummer', 'Reden']]
                      df_top_dag = df_top_dag.merge(df_top_reason, on='Ordernummer', how='left')
                 else: df_top_dag['Reden'] = 'N/A'
                 df_top_dag['Totale stilstand (uur)'] = (df_top_dag['Duur_min'] / 60)
                 df_top_dag.index = range(1, len(df_top_dag) + 1)
                 st.dataframe(df_top_dag[["Ordernummer", "Reden", "Duur_min", "Totale stilstand (uur)"]], use_container_width=True, column_config={"Duur_min": st.column_config.NumberColumn("Minuten", format="%.1f"), "Totale stilstand (uur)": st.column_config.NumberColumn("Uren", format="%.2f")})
        else: st.error("Kon 'Weekdag' kolom niet maken.")
    except Exception as e: st.error("Analyse per werkdag mislukt."); st.exception(e)

def display_performance_outliers(df_filtered: pd.DataFrame):
    """ Toont dagelijkse performance grafiek en detecteert outliers."""
    st.subheader("⏱️ Performance & Uitschieters (Dagelijks)")
    if df_filtered.empty: st.caption("Geen data."); return
    try:
        if 'Starttijd_dt' not in df_filtered.columns: st.error("'Starttijd_dt' kolom mist."); return
        df_daily = df_filtered.copy()
        df_daily["Dag"] = df_daily["Starttijd_dt"].dt.strftime("%Y-%m-%d")
        df_performance = df_daily.groupby("Dag")["Duur_min"].sum().reset_index()
        df_performance.rename(columns={"Duur_min": "Total_downtime_min"}, inplace=True)
        df_performance["Performance (%)"] = (100 * (1 - (df_performance["Total_downtime_min"] / PERFORMANCE_SHIFT_MINUTES))).clip(lower=0)

        st.markdown("**Performance over tijd:**"); st.caption(f"Gebaseerd op vaste shift van {PERFORMANCE_SHIFT_MINUTES / 60:.1f} uur.")
        if df_performance.empty: st.caption("Geen data."); return
        fig_perf = px.line(df_performance.sort_values("Dag"), x="Dag", y="Performance (%)", markers=True, title="Performance over tijd (%)")
        fig_perf.update_layout(yaxis_range=[0, 105])
        st.plotly_chart(fig_perf, use_container_width=True)

        st.markdown("---"); st.markdown("**Uitschieters in dagelijkse stilstand:**")
        if len(df_performance) < 2: st.caption("Te weinig data."); return
        mean_down = df_performance["Total_downtime_min"].mean(); std_down  = df_performance["Total_downtime_min"].std()
        if pd.isna(std_down) or std_down == 0: threshold = mean_down + 1
        else: threshold = mean_down + (1.5 * std_down)
        df_performance["Is_outlier"] = df_performance["Total_downtime_min"] > threshold
        df_outliers = df_performance[df_performance["Is_outlier"]].copy()

        st.caption(f"Drempel: > {threshold:.1f} min stilstand (gem + 1.5 * std dev).")
        if df_outliers.empty: st.success("✅ Geen uitschieters gevonden!")
        else:
            st.warning(f"🚨 {len(df_outliers)} dag(en) met uitzonderlijk hoge stilstand:")
            df_outliers['Uren Stilstand'] = (df_outliers['Total_downtime_min'] / 60)
            st.dataframe(df_outliers[["Dag","Total_downtime_min","Uren Stilstand","Performance (%)"]].sort_values("Dag"), use_container_width=True,
                         column_config={"Total_downtime_min": st.column_config.NumberColumn("Minuten", format="%.1f"), "Uren Stilstand": st.column_config.NumberColumn(format="%.2f"), "Performance (%)": st.column_config.NumberColumn(format="%.1f%%")})
    except Exception as e: st.error("Performance analyse mislukt."); st.exception(e)

def display_pareto_analysis(df_filtered: pd.DataFrame, periode_selectie: str, workflow_select: str):
    """ Toont een Pareto analyse (Top 3 tabel) voor een geselecteerde periode. """
    st.subheader(f"🔎 Pareto Top 3 Redenen per {periode_selectie}")
    if df_filtered.empty: st.caption("Geen data."); return
    try:
        df_pareto_base = df_filtered.copy()
        try:
             if periode_selectie == "Dag": df_pareto_base["Periode"] = df_pareto_base["Starttijd_dt"].dt.strftime("%Y-%m-%d")
             elif periode_selectie == "Week": df_pareto_base["Periode"] = df_pareto_base["Starttijd_dt"].dt.strftime('%Y-W%V')
             else: df_pareto_base["Periode"] = df_pareto_base["Starttijd_dt"].dt.to_period("M").astype(str)
        except AttributeError as ae: st.error(f"Fout bij bepalen periode: {ae}"); return

        periodes = sorted(df_pareto_base["Periode"].unique(), reverse=True)
        if not periodes: st.caption("Geen periodes gevonden."); return
        selected_periode = st.selectbox(f"Kies {periode_selectie.lower()} voor Pareto:", periodes, key="pareto_period_select")

        if selected_periode:
            df_pareto_period = df_pareto_base[df_pareto_base["Periode"] == selected_periode]
            if UITGESLOTEN_REDENEN_KEYWORDS: # Filter ook hier
                mask_exclude = pd.Series(False, index=df_pareto_period.index)
                for keyword in UITGESLOTEN_REDENEN_KEYWORDS: mask_exclude |= df_pareto_period['Reden'].str.contains(keyword, case=False, na=False)
                df_pareto_period = df_pareto_period[~mask_exclude]
            if df_pareto_period.empty: st.caption(f"Geen relevante data voor {selected_periode} (na filter)."); return

            df_top_reasons = (df_pareto_period.groupby("Reden")["Duur_min"].sum().sort_values(ascending=False).head(3).reset_index())
            if df_top_reasons.empty: st.caption(f"Geen top redenen voor {selected_periode}.")
            else:
                 df_top_reasons.index = range(1, len(df_top_reasons) + 1)
                 st.markdown(f"**Top 3 Redenen ({workflow_select}) in {selected_periode}:**")
                 st.dataframe(df_top_reasons.rename(columns={"Duur_min":"Totaal Minuten"}), use_container_width=True, column_config={"Totaal Minuten": st.column_config.NumberColumn(format="%.1f")})
        else: st.caption("Selecteer een periode.")
    except Exception as e: st.error("Pareto analyse mislukt."); st.exception(e)

# === HOOFD APPLICATIE LOGICA ===
def main():
    """Hoofdfunctie die de applicatie runt."""
    # Laad beide datasets aan het begin (als ze bestaan)
    df_downtime_raw = load_data(DATA_PATH_DOWNTIME)
    df_orders_raw = load_order_data(DATA_PATH_ORDER) # Nieuwe laadfunctie aanroepen

    # Maak sidebar (heeft nu beide dataframes nodig voor filters)
    dashboard_choice, workflow_select, date_range, periode_selectie, apply_shift_filter, selected_order_line = create_sidebar(df_downtime_raw, df_orders_raw)

    # --- Downtime Analyse Dashboard ---
    if dashboard_choice == "Downtime Analyse":
        if df_downtime_raw.empty: st.warning("Kan Downtime Analyse niet tonen: geen downtime data geladen."); return # Check of data er is
        if not date_range or len(date_range) != 2: st.error("Selecteer een geldig datumbereik."); st.stop(); return
        df_filtered = filter_data(df_downtime_raw, workflow_select, date_range, apply_shift_filter)

        st.header(f"Downtime Analyse: {workflow_select}") # Aangepaste header
        date_info = f"Periode: {date_range[0].strftime('%d-%m-%Y')} tot {date_range[1].strftime('%d-%m-%Y')}"
        shift_info = " (Alleen tijdens shift)" if apply_shift_filter else " (Alle tijden)"
        st.caption(date_info + shift_info); st.markdown("---")

        if df_filtered.empty: st.warning("Geen downtime data gevonden voor de geselecteerde filters.")
        else:
            MaakKengetallenZichtbaar(df_filtered); st.markdown("---")
            display_tabbed_line_analysis(df_filtered); st.markdown("---")
            display_period_analysis(df_filtered, periode_selectie); st.markdown("---")
            display_order_analysis(df_filtered); st.markdown("---") # Order analyse (op downtime data)
            display_performance_outliers(df_filtered); st.markdown("---") # Performance (op downtime data)
            display_pareto_analysis(df_filtered, periode_selectie, workflow_select); st.markdown("---") # Pareto (op downtime data)

    # --- Order Target Calculator ---
    elif dashboard_choice == "Order Target Calculator":
        st.header("🕒 Order Target Calculator") # Aangepaste header
        if df_orders_raw.empty: st.warning(f"Kan Order Calculator niet tonen: Kon bestand '{DATA_PATH_ORDER}' niet laden of het is leeg."); return

        # Filter order data op geselecteerde lijn (uit sidebar)
        df_orders_filtered = df_orders_raw.copy()
        if selected_order_line and selected_order_line != "Alle lijnen":
            df_orders_filtered = df_orders_filtered[df_orders_filtered['Line'] == selected_order_line]
            st.caption(f"Filters: Lijn = {selected_order_line}")
        else:
             st.caption(f"Filters: Alle lijnen")


        if df_orders_filtered.empty:
            st.warning(f"Geen order data gevonden voor lijn: {selected_order_line}")
        else:
             # Bereken Target Time
             try:
                  if 'Quantity' not in df_orders_filtered.columns:
                        st.error("Kolom 'Quantity' (hernoemd van 'Build Qty') niet gevonden voor berekening.")
                  elif EFFECTIVE_CAPACITY <= 0:
                        st.error("Effective capacity moet groter dan 0 zijn.")
                  else:
                        df_orders_filtered['Target_Time_Min'] = df_orders_filtered['Quantity'] / EFFECTIVE_CAPACITY

                        st.write(f"**Standaard effective capacity:** {EFFECTIVE_CAPACITY} stuks/minuut")
                        st.markdown("---")

                        # Toon Tabel
                        st.subheader("Berekende Target Tijden")
                        display_df_orders = df_orders_filtered[['Line', 'WO #', 'Item', 'Quantity', 'Target_Time_Min']].copy()
                        display_df_orders.rename(columns={'Quantity': 'Order Aantal', 'Target_Time_Min': 'Target Tijd (min)'}, inplace=True)
                        st.dataframe(display_df_orders, use_container_width=True, column_config={
                             "Target Tijd (min)": st.column_config.NumberColumn(format="%.1f")
                        })

                        st.markdown("---")
                        # Toon Scatter Plot
                        st.subheader("Visualisatie Aantal vs Targettijd")
                        if len(df_orders_filtered) > 1000:
                              st.info("Te veel datapunten (>1000) om scatter plot interactief te tonen. Overweeg kortere periode of specifieke lijn.")
                              # Optioneel: sample tonen? fig_order = px.scatter(df_orders_filtered.sample(1000), ...)
                        else:
                              fig_order = px.scatter(
                                  df_orders_filtered, x='Quantity', y='Target_Time_Min',
                                  color='Line', hover_data=['WO #', 'Item'],
                                  labels={'Quantity': 'Order Aantal', 'Target_Time_Min': 'Target Tijd (min)'},
                                  title="Order Aantal versus Berekende Targettijd"
                              )
                              st.plotly_chart(fig_order, use_container_width=True)

             except ZeroDivisionError:
                   st.error("Fout: Deling door nul bij berekenen Target Tijd (Effective Capacity mag geen 0 zijn).")
             except Exception as e:
                   st.error("Fout bij berekenen of tonen van Target Tijd.")
                   st.exception(e)

    # === FOOTER ===
    st.markdown("--# File: dashboard.py (Versie 2025-05-02, Incl. Order Target Calculator)

import streamlit as st
import pandas as pd
import plotly.express as px
import os
import datetime
import numpy as np # Nodig voor mean/std in performance

# === CONSTANTEN ===
DATA_PATH_DOWNTIME = "OEE_Dashboard_PowerBI_Finaal.csv"
DATA_PATH_ORDER = "Motivate  Performance.csv" # Pad naar order data
GEWENSTE_WORKFLOWS = ["VMPT1", "VMPT5", "COSMO"] # Workflows voor downtime analyse
SHIFT_START_TIME = datetime.time(7, 30)
SHIFT_END_TIME = datetime.time(16, 0)
PERFORMANCE_SHIFT_MINUTES = 8 * 60
# Filters en Top N instellingen
UITGESLOTEN_REDENEN_KEYWORDS = ['Pauze'] # Voor downtime reden analyse
TOP_N_IN_BARCHART = 10
TOP_N_IN_DONUT = 5
# Instelling voor Order Target Calculator
EFFECTIVE_CAPACITY = 19.6 # Stuks per minuut

# === PAGE CONFIG ===
st.set_page_config(page_title="Interfilling OEE Analyse", layout="wide")

# === HEADER ===
st.title("📊 Interfilling Dashboard") # Algemenere titel?
st.caption("Dashboard door www.proces360.com | rob@proces360.com")
st.markdown("---")

# === DATA LAAD FUNCTIE (Downtime) ===
@st.cache_data
def load_data(path: str) -> pd.DataFrame:
    """Laadt en voorbewerkt de downtime data."""
    if not os.path.exists(path): st.error(f"❌ Downtime bestand niet gevonden: {path}"); st.stop(); return pd.DataFrame()
    try:
        df = pd.read_csv(path, sep=",", quotechar='"', skipinitialspace=True, encoding="utf-8")
        if 'Unnamed: 0' in df.columns: df = df.drop('Unnamed: 0', axis=1)
        expected_cols_len = 12
        if len(df.columns) == expected_cols_len:
            df.columns = ["jobId", "Ordernummer", "Workflow", "Verklaard_door", "Reden", "Opmerking", "Starttijd", "Stoptijd", "Duur_txt", "excludedFromProductivity", "subType", "Opties"]
        else: st.error(f"Onverwacht aantal kolommen ({len(df.columns)}) in {path}."); st.stop(); return pd.DataFrame()
        df["Starttijd_dt"] = pd.to_datetime(df["Starttijd"], format="%d/%m/%y %H:%M:%S", errors="coerce", dayfirst=True)
        df["Stoptijd_dt"]  = pd.to_datetime(df["Stoptijd"], format="%d/%m/%y %H:%M:%S", errors="coerce", dayfirst=True)
        start_errors = df["Starttijd_dt"].isna().sum(); stop_errors = df["Stoptijd_dt"].isna().sum()
        if start_errors > 0 or stop_errors > 0: st.warning(f"Let op: {start_errors} Starttijd(en) en {stop_errors} Stoptijd(en) konden niet gelezen worden.")
        df["Duur_calc"] = (df["Stoptijd_dt"] - df["Starttijd_dt"]); df["Duur_sec"] = df["Duur_calc"].dt.total_seconds()
        neg_dur_count = (df["Duur_sec"] < 0).sum()
        if neg_dur_count > 0: st.warning(f"Let op: {neg_dur_count} rijen met negatieve duur genegeerd."); df = df[df["Duur_sec"] >= 0]
        df["Duur_min"] = df["Duur_sec"] / 60.0
        df["Datum"] = df["Starttijd_dt"].dt.date
        df["Workflow"] = df["Workflow"].astype(str).str.upper().str.replace(" ", "")
        df['Reden'] = df['Reden'].fillna('Onbekend').astype(str).str.strip()
        df.dropna(subset=["Starttijd_dt", "Datum", "Duur_min", "Reden"], inplace=True)
        return df
    except Exception as e: st.error(f"Fout bij laden downtime data: {path}."); st.exception(e); st.stop(); return pd.DataFrame()

# === NIEUW: DATA LAAD FUNCTIE (Order Performance) ===
@st.cache_data
def load_order_data(path: str) -> pd.DataFrame:
    """Laadt en voorbewerkt de order performance data."""
    if not os.path.exists(path):
        st.error(f"❌ Order bestand niet gevonden: {path}")
        # Geef leeg dataframe terug ipv st.stop() zodat de app niet crasht als alleen dit bestand mist
        return pd.DataFrame()
    try:
        # --- BELANGRIJK: Deze read_csv is ongetest door de tool ---
        # Controleer lokaal of het pad, sep=',' en skipinitialspace=True correct zijn.
        # Mogelijk moet je quotechar='"' of encoding toevoegen.
        df = pd.read_csv(path, sep=',', engine='python', skipinitialspace=True)
        st.success(f"Bestand {path} succesvol ingelezen (in theorie).") # Feedback

        # --- Kolom Selectie & Hernoemen (pas aan indien nodig) ---
        # Kolommen die we nodig hebben op basis van screenshot
        required_cols = ['Date', 'Work Center', 'WO #', 'Item', 'Build Qty']
        # Check of alle benodigde kolommen bestaan
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            st.error(f"De volgende vereiste kolommen missen in {path}: {', '.join(missing_cols)}")
            return pd.DataFrame()

        # Selecteer en hernoem
        df_selected = df[required_cols].copy()
        df_selected.rename(columns={'Work Center': 'Line', 'Build Qty': 'Quantity'}, inplace=True)

        # --- Data Type Conversie & Cleaning ---
        df_selected['Quantity'] = pd.to_numeric(df_selected['Quantity'], errors='coerce')
        # Converteer Datum indien nodig (pas format aan als het niet standaard is)
        try:
            df_selected['Date'] = pd.to_datetime(df_selected['Date'], errors='coerce')
        except Exception as date_err:
            st.warning(f"Kon 'Date' kolom niet converteren naar datum: {date_err}. Controleer het formaat.")

        # Verwijder rijen waar essentiële data (Line, Quantity) mist
        rows_before = len(df_selected)
        df_selected.dropna(subset=['Line', 'Quantity'], inplace=True)
        rows_after = len(df_selected)
        if rows_before > rows_after:
             st.info(f"{rows_before - rows_after} rijen verwijderd uit order data ivm missende Line/Quantity.")

        # Hernoem Line naar string om zeker te zijn
        df_selected['Line'] = df_selected['Line'].astype(str)

        return df_selected

    except FileNotFoundError:
         # Extra check, hoewel de check bovenaan dit al zou moeten vangen
         st.error(f"Kon bestand niet vinden (check pad): {path}")
         return pd.DataFrame()
    except Exception as e:
        st.error(f"Fout bij het laden of verwerken van order data: {path}.")
        st.exception(e) # Toon details van de fout
        return pd.DataFrame()


# === SIDEBAR FUNCTIE ===
def create_sidebar(df_downtime: pd.DataFrame, df_orders: pd.DataFrame) -> tuple:
    """Creëert de sidebar elementen en retourneert de selecties."""
    # --- Algemene Opties ---
    st.sidebar.title("Dashboard Opties")
    dashboard_choice = st.sidebar.radio("Kies dashboard:", ["Downtime Analyse", "Order Target Calculator"], key="dashboard_choice")

    # --- Filters voor Downtime Analyse ---
    st.sidebar.title("🔍 Filters (Downtime)")
    # Workflow filter (downtime)
    workflows_in_data = sorted([w for w in df_downtime["Workflow"].unique() if w in GEWENSTE_WORKFLOWS]) if not df_downtime.empty else []
    workflow_options = ["Alle lijnen"] + workflows_in_data
    workflow_select = st.sidebar.selectbox("Kies workflow (machine):", options=workflow_options, key="downtime_workflow_filter")
    # Datum filter (downtime)
    min_datum_dt = pd.to_datetime(df_downtime["Datum"]).min() if not df_downtime.empty else None
    max_datum_dt = pd.to_datetime(df_downtime["Datum"]).max() if not df_downtime.empty else None
    if pd.isna(min_datum_dt) or pd.isna(max_datum_dt):
         # st.sidebar.warning("Kan geen geldig datumbereik vinden voor downtime.")
         today = datetime.date.today(); default_start = today - datetime.timedelta(days=30); default_end = today
         date_range = st.sidebar.date_input("Datum bereik (Downtime):", value=(default_start, default_end), key="downtime_date_filter")
    else:
        min_datum = min_datum_dt.date(); max_datum = max_datum_dt.date()
        default_start = max(min_datum, max_datum - datetime.timedelta(days=30)); default_end = max_datum
        date_range = st.sidebar.date_input("Datum bereik (Downtime):", value=(default_start, default_end), min_value=min_datum, max_value=max_datum, key="downtime_date_filter")
    # Periode selectie (downtime)
    periode_selectie = st.sidebar.radio("Groepeer downtime per:", ["Dag", "Week", "Maand"], key="downtime_period_filter", horizontal=True)
    # Shift filter (downtime)
    apply_shift_filter_toggle = st.sidebar.toggle("Alleen downtime tijdens shift", value=True, key="downtime_shift_toggle")

    # --- Filters voor Order Target Calculator ---
    st.sidebar.title("🕒 Filters (Order Calc)")
    selected_order_line = None # Default
    if not df_orders.empty and 'Line' in df_orders.columns:
        lines_order = sorted(df_orders["Line"].dropna().unique().tolist())
        order_line_options = ["Alle lijnen"] + lines_order
        selected_order_line = st.sidebar.selectbox("Kies lijn (Order Calc):", options=order_line_options, key="order_line_filter")
    else:
         st.sidebar.caption("Geen order data geladen om op lijn te filteren.")

    return (dashboard_choice, workflow_select, date_range, periode_selectie, apply_shift_filter_toggle,
            selected_order_line) # Return order filter


# === FILTER DATA FUNCTIE (Downtime) ===
def filter_data(df: pd.DataFrame, workflow_select: str, date_range: tuple, apply_shift_filter: bool) -> pd.DataFrame:
    """Filtert de downtime dataframe op basis van selecties."""
    df_filtered = df.copy()
    if not date_range or len(date_range) != 2 or date_range[0] is None or date_range[1] is None:
        st.error("Ongeldig datumbereik geselecteerd."); return pd.DataFrame()
    start_date = pd.to_datetime(date_range[0]); end_date = pd.to_datetime(date_range[1])
    df_filtered["Datum"] = pd.to_datetime(df_filtered["Datum"])
    mask_date = (df_filtered["Datum"] >= start_date) & (df_filtered["Datum"] <= end_date)
    df_filtered = df_filtered[mask_date]
    if workflow_select != "Alle lijnen": df_filtered = df_filtered[df_filtered["Workflow"] == workflow_select]
    else: df_filtered = df_filtered[df_filtered["Workflow"].isin(GEWENSTE_WORKFLOWS)]
    if apply_shift_filter:
        mask_shift = ((df_filtered["Starttijd_dt"].dt.weekday < 5) & (df_filtered["Starttijd_dt"].dt.time >= SHIFT_START_TIME) & (df_filtered["Starttijd_dt"].dt.time < SHIFT_END_TIME))
        df_filtered = df_filtered[mask_shift]
    return df_filtered

# === DISPLAY FUNCTIES (Downtime Analyse) ===

def MaakKengetallenZichtbaar(df_filtered: pd.DataFrame):
    """Toont de Key Performance Indicators (KPIs) in kolommen."""
    st.subheader("📈 Kerncijfers") # Emoji kan helpen
    col1, col2, col3 = st.columns(3)
    if df_filtered.empty:
        col1.metric("Totale stilstand (uren)", "N/A"); col2.metric("Aantal stilstanden", 0); col3.metric("Langste stilstand (min)", "N/A")
    else:
        total_downtime_hrs = df_filtered["Duur_min"].sum() / 60; col1.metric("Totale stilstand (uren)", f"{total_downtime_hrs:.2f}")
        col2.metric("Aantal stilstanden", len(df_filtered)); max_stilstand = df_filtered["Duur_min"].max()
        col3.metric("Langste stilstand (min)", f"{max_stilstand:.1f}" if pd.notna(max_stilstand) else "N/A")

def display_tabbed_line_analysis(data_om_te_tonen):
    """Toont per lijn (in tabs) een staafdiagram en een donut+legenda."""
    st.subheader("📊 Analyse Stilstandsredenen per Lijn")
    lijnen_in_data = sorted([w for w in data_om_te_tonen["Workflow"].unique() if w in GEWENSTE_WORKFLOWS])
    tab_namen = ["Alle lijnen"] + lijnen_in_data
    tabs = st.tabs(tab_namen)
    color_sequence = px.colors.qualitative.Plotly

    for i, lijn_naam in enumerate(tab_namen):
        with tabs[i]:
            if lijn_naam == "Alle lijnen": data_voor_deze_lijn = data_om_te_tonen
            else: data_voor_deze_lijn = data_om_te_tonen[data_om_te_tonen["Workflow"] == lijn_naam]
            if data_voor_deze_lijn.empty: st.caption("Geen data beschikbaar."); continue

            data_gefilterd = data_voor_deze_lijn.copy(); filter_applied_info = []
            if UITGESLOTEN_REDENEN_KEYWORDS:
                mask_exclude = pd.Series(False, index=data_gefilterd.index)
                for keyword in UITGESLOTEN_REDENEN_KEYWORDS: mask_exclude |= data_gefilterd['Reden'].str.contains(keyword, case=False, na=False)
                rows_before = len(data_gefilterd); data_gefilterd = data_gefilterd[~mask_exclude]; rows_after = len(data_gefilterd)
                if rows_before > rows_after: filter_applied_info.append(f"{rows_before - rows_after} rijen met '{', '.join(UITGESLOTEN_REDENEN_KEYWORDS)}' verwijderd")
            if filter_applied_info: st.caption(f"Filter info: {'; '.join(filter_applied_info)}.", help="...")

            if data_gefilterd.empty or data_gefilterd["Duur_min"].sum() < 0.1: st.caption("Geen relevante data na filter."); continue

            df_reason_agg = data_gefilterd.groupby("Reden")["Duur_min"].sum().reset_index()
            df_reason_agg = df_reason_agg[df_reason_agg['Reden'] != ''].sort_values(by="Duur_min", ascending=False)
            totaal_duur_relevant = df_reason_agg["Duur_min"].sum()
            if totaal_duur_relevant > 0: df_reason_agg['percentage_totaal'] = (df_reason_agg['Duur_min'] / totaal_duur_relevant) * 100
            else: df_reason_agg['percentage_totaal'] = 0.0

            all_reasons_sorted = df_reason_agg['Reden'].tolist()
            color_map = {reason: color_sequence[i % len(color_sequence)] for i, reason in enumerate(all_reasons_sorted)}
            overig_label = f'Overige ({max(0, len(df_reason_agg) - TOP_N_IN_DONUT)})'
            color_map[overig_label] = '#bdbdbd'

            col_bar, col_donut_leg = st.columns(2)
            with col_bar:
                st.markdown(f"**Top {TOP_N_IN_BARCHART} Redenen (Staafdiagram)**")
                df_bar_display = df_reason_agg.head(TOP_N_IN_BARCHART).copy(); df_bar_display['percentage'] = df_bar_display['percentage_totaal']
                if df_bar_display.empty: st.caption("Geen data.")
                else:
                    try:
                        fig_bar = px.bar(df_bar_display, x="Duur_min", y="Reden", orientation='h', labels={"Duur_min": "Duur (min)", "Reden": ""}, text="Duur_min", color="Reden", color_discrete_map=color_map)
                        fig_bar.update_layout(showlegend=False, yaxis={'categoryorder':'total ascending'}, height=max(350, len(df_bar_display) * 28), margin=dict(l=10, r=10, t=10, b=10))
                        fig_bar.update_traces(texttemplate='%{text:.0f}', textposition='outside', hovertemplate="<b>%{y}</b><br>Duur: %{x:.1f} min<br>Percentage: %{customdata[0]:.1f}%<extra></extra>", customdata=df_bar_display[['percentage']])
                        st.plotly_chart(fig_bar, use_container_width=True)
                    except Exception as e: st.error("Kon staafdiagram niet maken."); st.exception(e)
            with col_donut_leg:
                st.markdown(f"**Top {TOP_N_IN_DONUT} + Overig (Donut)**")
                overig_duur = 0.0; df_donut_data = pd.DataFrame()
                if len(df_reason_agg) > TOP_N_IN_DONUT:
                    df_top_n_donut = df_reason_agg.head(TOP_N_IN_DONUT).copy()
                    if len(df_reason_agg) > TOP_N_IN_DONUT: overig_duur = float(df_reason_agg.iloc[TOP_N_IN_DONUT:]['Duur_min'].sum())
                    if overig_duur > 0.01:
                        df_overig = pd.DataFrame([{'Reden': overig_label, 'Duur_min': overig_duur}])
                        if isinstance(df_top_n_donut, pd.DataFrame) and isinstance(df_overig, pd.DataFrame):
                           try: df_donut_data = pd.concat([df_top_n_donut, df_overig], ignore_index=True)
                           except ValueError as ve: st.error(f"Concat Fout: {ve}"); df_donut_data = df_top_n_donut
                        else: df_donut_data = df_top_n_donut
                    else: df_donut_data = df_top_n_donut
                else: df_donut_data = df_reason_agg.copy()

                if not df_donut_data.empty and totaal_duur_relevant > 0:
                    df_donut_data['percentage'] = (df_donut_data['Duur_min'] / totaal_duur_relevant) * 100
                    top_3_legenda = df_reason_agg.head(3).copy()
                    try:
                        fig_donut = px.pie(df_donut_data, names="Reden", values="Duur_min", hole=0.45, color="Reden", color_discrete_map=color_map)
                        fig_donut.update_traces(textinfo='percent', textfont_size=11, hovertemplate = "<b>%{label}</b><br>Duur: %{value:.1f} min<br>Percentage: %{percent:.1%}<extra></extra>")
                        fig_donut.update_layout(showlegend=False, margin=dict(l=10, r=10, t=10, b=10), height=250)
                        st.plotly_chart(fig_donut, use_container_width=True)
                        st.markdown("**Top 3 Details:**")
                        if top_3_legenda.empty: st.caption("Geen top redenen.")
                        else:
                            for idx in range(len(top_3_legenda)):
                                 row = top_3_legenda.iloc[idx]; color = color_map.get(row['Reden'], '#808080'); display_reden = row['Reden'][:30] + '...' if len(row['Reden']) > 30 else row['Reden']
                                 st.markdown(f"<div style='margin-bottom: 4px; text-align: left;' title='{row['Reden']}'><span style='display: inline-block; width: 10px; height: 10px; background-color: {color}; margin-right: 5px; vertical-align: middle; border: 1px solid #ccc;'></span><span style='font-size: 0.9em; vertical-align: middle;'><b>{display_reden}</b></span><br><span style='font-size: 0.8em; padding-left: 15px;'>{row['percentage_totaal']:.1f}% ({row['Duur_min']:.0f} min)</span></div>", unsafe_allow_html=True)
                    except Exception as e: st.error("Kon donut/legenda niet maken."); st.exception(e)
                else: st.caption("Geen data voor donut.")

def display_period_analysis(df_filtered: pd.DataFrame, periode_selectie: str):
     """Toont de totale stilstand gegroepeerd per geselecteerde periode."""
     st.subheader(f"📆 Trend Niet-geplande stilstand")
     df_analysis = df_filtered.copy()
     try:
          if periode_selectie == "Dag": df_analysis["Periode"] = df_analysis["Starttijd_dt"].dt.strftime("%Y-%m-%d")
          elif periode_selectie == "Week": df_analysis["Periode"] = df_analysis["Starttijd_dt"].dt.strftime('%Y-W%V')
          else: df_analysis["Periode"] = df_analysis["Starttijd_dt"].dt.to_period("M").astype(str)
     except AttributeError as ae: st.error(f"Fout bij bepalen periode: {ae}"); return
     df_tijd = df_analysis.groupby("Periode")["Duur_min"].sum().reset_index()
     if df_tijd.empty: st.caption(f"Geen data per {periode_selectie.lower()}."); return
     df_tijd = df_tijd.sort_values("Periode")
     try:
          fig_tijd = px.bar(df_tijd, x="Periode", y="Duur_min", title=f"Totale Stilstand (min) per {periode_selectie.lower()}", labels={"Duur_min": "Stilstand (min)"})
          if len(df_tijd) > 15: fig_tijd.update_xaxes(tickangle=45)
          st.plotly_chart(fig_tijd, use_container_width=True)
     except Exception as e: st.error(f"Kon periode grafiek niet maken."); st.exception(e)

def display_order_analysis(df_filtered: pd.DataFrame):
    """Toont analyses gerelateerd aan orders uit downtime data."""
    st.subheader("📦 Analyse per Order (Downtime)")
    if df_filtered.empty: st.caption("Geen data."); return

    st.markdown("**Top 3 Orders (Totale Stilstand):**")
    try:
        df_order_downtime = (df_filtered.groupby("Ordernummer")["Duur_min"].sum().sort_values(ascending=False).head(3).reset_index())
        if not df_order_downtime.empty:
             df_order_downtime.index = range(1, len(df_order_downtime) + 1)
             st.dataframe(df_order_downtime.rename(columns={"Duur_min": "Totale Stilstand (min)"}), use_container_width=True, column_config={"Totale Stilstand (min)": st.column_config.NumberColumn(format="%.1f")})
             top_orders_list = df_order_downtime["Ordernummer"].tolist()
        else: st.caption("Geen orders gevonden."); top_orders_list = []
    except Exception as e: st.error("Berekening mislukt."); st.exception(e); top_orders_list = []

    st.markdown("---")
    st.markdown("**Langste Enkele Stilstand per Top 3 Order:**")
    if not top_orders_list: st.caption("Geen top orders gevonden.")
    else:
        try:
            df_top_events = df_filtered[df_filtered["Ordernummer"].isin(top_orders_list)].copy()
            if not df_top_events.empty:
                 idx = df_top_events.loc[df_top_events.groupby("Ordernummer")["Duur_min"].idxmax()].index
                 df_longest_events = df_top_events.loc[idx]
                 df_longest_display = df_longest_events[["Ordernummer", "Starttijd_dt", "Stoptijd_dt", "Duur_min", "Reden"]].copy()
                 df_longest_display.rename(columns={"Starttijd_dt": "Start", "Stoptijd_dt": "Stop", "Duur_min": "Duur (min)"}, inplace=True)
                 st.dataframe(df_longest_display, use_container_width=True, column_config={"Start": st.column_config.DatetimeColumn(format="DD-MM-YY HH:mm"), "Stop": st.column_config.DatetimeColumn(format="DD-MM-YY HH:mm"), "Duur (min)": st.column_config.NumberColumn(format="%.1f")})
            else: st.caption("Geen stilstanden voor top 3 orders.")
        except Exception as e: st.error("Berekening mislukt."); st.exception(e)

    st.markdown("---")
    st.markdown("**Top 3 Orders per Werkdag (Ma-Vr):**")
    try:
        df_daily_analysis = df_filtered.copy()
        if 'Starttijd_dt' not in df_daily_analysis.columns: st.error("'Starttijd_dt' kolom mist."); return
        weekday_map = {0: 'Maandag', 1: 'Dinsdag', 2: 'Woensdag', 3: 'Donderdag', 4: 'Vrijdag'}
        df_daily_analysis['Weekdag'] = df_daily_analysis['Starttijd_dt'].dt.weekday.map(weekday_map)
        if 'Weekdag' in df_daily_analysis.columns:
             df_daily_analysis = df_daily_analysis[df_daily_analysis['Starttijd_dt'].dt.weekday < 5]
             werkdagen = ['Maandag', 'Dinsdag', 'Woensdag', 'Donderdag', 'Vrijdag']
             for dag in werkdagen:
                 df_dag = df_daily_analysis[df_daily_analysis['Weekdag'] == dag]
                 if df_dag.empty: continue
                 st.markdown(f"**{dag}:**")
                 df_top_dag = (df_dag.groupby('Ordernummer')['Duur_min'].sum().sort_values(ascending=False).head(3).reset_index())
                 if df_top_dag.empty: st.caption("Geen data."); continue
                 df_reason_order = (df_dag.groupby(['Ordernummer', 'Reden'])['Duur_min'].sum().reset_index())
                 if not df_reason_order.empty:
                      idx_res = df_reason_order.loc[df_reason_order.groupby('Ordernummer')['Duur_min'].idxmax()]
                      df_top_reason = idx_res[['Ordernummer', 'Reden']]
                      df_top_dag = df_top_dag.merge(df_top_reason, on='Ordernummer', how='left')
                 else: df_top_dag['Reden'] = 'N/A'
                 df_top_dag['Totale stilstand (uur)'] = (df_top_dag['Duur_min'] / 60)
                 df_top_dag.index = range(1, len(df_top_dag) + 1)
                 st.dataframe(df_top_dag[["Ordernummer", "Reden", "Duur_min", "Totale stilstand (uur)"]], use_container_width=True, column_config={"Duur_min": st.column_config.NumberColumn("Minuten", format="%.1f"), "Totale stilstand (uur)": st.column_config.NumberColumn("Uren", format="%.2f")})
        else: st.error("Kon 'Weekdag' kolom niet maken.")
    except Exception as e: st.error("Analyse per werkdag mislukt."); st.exception(e)

def display_performance_outliers(df_filtered: pd.DataFrame):
    """ Toont dagelijkse performance grafiek en detecteert outliers."""
    st.subheader("⏱️ Performance & Uitschieters (Dagelijks)")
    if df_filtered.empty: st.caption("Geen data."); return
    try:
        if 'Starttijd_dt' not in df_filtered.columns: st.error("'Starttijd_dt' kolom mist."); return
        df_daily = df_filtered.copy()
        df_daily["Dag"] = df_daily["Starttijd_dt"].dt.strftime("%Y-%m-%d")
        df_performance = df_daily.groupby("Dag")["Duur_min"].sum().reset_index()
        df_performance.rename(columns={"Duur_min": "Total_downtime_min"}, inplace=True)
        df_performance["Performance (%)"] = (100 * (1 - (df_performance["Total_downtime_min"] / PERFORMANCE_SHIFT_MINUTES))).clip(lower=0)

        st.markdown("**Performance over tijd:**"); st.caption(f"Gebaseerd op vaste shift van {PERFORMANCE_SHIFT_MINUTES / 60:.1f} uur.")
        if df_performance.empty: st.caption("Geen data."); return
        fig_perf = px.line(df_performance.sort_values("Dag"), x="Dag", y="Performance (%)", markers=True, title="Performance over tijd (%)")
        fig_perf.update_layout(yaxis_range=[0, 105])
        st.plotly_chart(fig_perf, use_container_width=True)

        st.markdown("---"); st.markdown("**Uitschieters in dagelijkse stilstand:**")
        if len(df_performance) < 2: st.caption("Te weinig data."); return
        mean_down = df_performance["Total_downtime_min"].mean(); std_down  = df_performance["Total_downtime_min"].std()
        if pd.isna(std_down) or std_down == 0: threshold = mean_down + 1
        else: threshold = mean_down + (1.5 * std_down)
        df_performance["Is_outlier"] = df_performance["Total_downtime_min"] > threshold
        df_outliers = df_performance[df_performance["Is_outlier"]].copy()

        st.caption(f"Drempel: > {threshold:.1f} min stilstand (gem + 1.5 * std dev).")
        if df_outliers.empty: st.success("✅ Geen uitschieters gevonden!")
        else:
            st.warning(f"🚨 {len(df_outliers)} dag(en) met uitzonderlijk hoge stilstand:")
            df_outliers['Uren Stilstand'] = (df_outliers['Total_downtime_min'] / 60)
            st.dataframe(df_outliers[["Dag","Total_downtime_min","Uren Stilstand","Performance (%)"]].sort_values("Dag"), use_container_width=True,
                         column_config={"Total_downtime_min": st.column_config.NumberColumn("Minuten", format="%.1f"), "Uren Stilstand": st.column_config.NumberColumn(format="%.2f"), "Performance (%)": st.column_config.NumberColumn(format="%.1f%%")})
    except Exception as e: st.error("Performance analyse mislukt."); st.exception(e)

def display_pareto_analysis(df_filtered: pd.DataFrame, periode_selectie: str, workflow_select: str):
    """ Toont een Pareto analyse (Top 3 tabel) voor een geselecteerde periode. """
    st.subheader(f"🔎 Pareto Top 3 Redenen per {periode_selectie}")
    if df_filtered.empty: st.caption("Geen data."); return
    try:
        df_pareto_base = df_filtered.copy()
        try:
             if periode_selectie == "Dag": df_pareto_base["Periode"] = df_pareto_base["Starttijd_dt"].dt.strftime("%Y-%m-%d")
             elif periode_selectie == "Week": df_pareto_base["Periode"] = df_pareto_base["Starttijd_dt"].dt.strftime('%Y-W%V')
             else: df_pareto_base["Periode"] = df_pareto_base["Starttijd_dt"].dt.to_period("M").astype(str)
        except AttributeError as ae: st.error(f"Fout bij bepalen periode: {ae}"); return

        periodes = sorted(df_pareto_base["Periode"].unique(), reverse=True)
        if not periodes: st.caption("Geen periodes gevonden."); return
        selected_periode = st.selectbox(f"Kies {periode_selectie.lower()} voor Pareto:", periodes, key="pareto_period_select")

        if selected_periode:
            df_pareto_period = df_pareto_base[df_pareto_base["Periode"] == selected_periode]
            if UITGESLOTEN_REDENEN_KEYWORDS: # Filter ook hier
                mask_exclude = pd.Series(False, index=df_pareto_period.index)
                for keyword in UITGESLOTEN_REDENEN_KEYWORDS: mask_exclude |= df_pareto_period['Reden'].str.contains(keyword, case=False, na=False)
                df_pareto_period = df_pareto_period[~mask_exclude]
            if df_pareto_period.empty: st.caption(f"Geen relevante data voor {selected_periode} (na filter)."); return

            df_top_reasons = (df_pareto_period.groupby("Reden")["Duur_min"].sum().sort_values(ascending=False).head(3).reset_index())
            if df_top_reasons.empty: st.caption(f"Geen top redenen voor {selected_periode}.")
            else:
                 df_top_reasons.index = range(1, len(df_top_reasons) + 1)
                 st.markdown(f"**Top 3 Redenen ({workflow_select}) in {selected_periode}:**")
                 st.dataframe(df_top_reasons.rename(columns={"Duur_min":"Totaal Minuten"}), use_container_width=True, column_config={"Totaal Minuten": st.column_config.NumberColumn(format="%.1f")})
        else: st.caption("Selecteer een periode.")
    except Exception as e: st.error("Pareto analyse mislukt."); st.exception(e)

# === HOOFD APPLICATIE LOGICA ===
def main():
    """Hoofdfunctie die de applicatie runt."""
    # Laad beide datasets aan het begin (als ze bestaan)
    df_downtime_raw = load_data(DATA_PATH_DOWNTIME)
    df_orders_raw = load_order_data(DATA_PATH_ORDER) # Nieuwe laadfunctie aanroepen

    # Maak sidebar (heeft nu beide dataframes nodig voor filters)
    dashboard_choice, workflow_select, date_range, periode_selectie, apply_shift_filter, selected_order_line = create_sidebar(df_downtime_raw, df_orders_raw)

    # --- Downtime Analyse Dashboard ---
    if dashboard_choice == "Downtime Analyse":
        if df_downtime_raw.empty: st.warning("Kan Downtime Analyse niet tonen: geen downtime data geladen."); return # Check of data er is
        if not date_range or len(date_range) != 2: st.error("Selecteer een geldig datumbereik."); st.stop(); return
        df_filtered = filter_data(df_downtime_raw, workflow_select, date_range, apply_shift_filter)

        st.header(f"Downtime Analyse: {workflow_select}") # Aangepaste header
        date_info = f"Periode: {date_range[0].strftime('%d-%m-%Y')} tot {date_range[1].strftime('%d-%m-%Y')}"
        shift_info = " (Alleen tijdens shift)" if apply_shift_filter else " (Alle tijden)"
        st.caption(date_info + shift_info); st.markdown("---")

        if df_filtered.empty: st.warning("Geen downtime data gevonden voor de geselecteerde filters.")
        else:
            MaakKengetallenZichtbaar(df_filtered); st.markdown("---")
            display_tabbed_line_analysis(df_filtered); st.markdown("---")
            display_period_analysis(df_filtered, periode_selectie); st.markdown("---")
            display_order_analysis(df_filtered); st.markdown("---") # Order analyse (op downtime data)
            display_performance_outliers(df_filtered); st.markdown("---") # Performance (op downtime data)
            display_pareto_analysis(df_filtered, periode_selectie, workflow_select); st.markdown("---") # Pareto (op downtime data)

    # --- Order Target Calculator ---
    elif dashboard_choice == "Order Target Calculator":
        st.header("🕒 Order Target Calculator") # Aangepaste header
        if df_orders_raw.empty: st.warning(f"Kan Order Calculator niet tonen: Kon bestand '{DATA_PATH_ORDER}' niet laden of het is leeg."); return

        # Filter order data op geselecteerde lijn (uit sidebar)
        df_orders_filtered = df_orders_raw.copy()
        if selected_order_line and selected_order_line != "Alle lijnen":
            df_orders_filtered = df_orders_filtered[df_orders_filtered['Line'] == selected_order_line]
            st.caption(f"Filters: Lijn = {selected_order_line}")
        else:
             st.caption(f"Filters: Alle lijnen")


        if df_orders_filtered.empty:
            st.warning(f"Geen order data gevonden voor lijn: {selected_order_line}")
        else:
             # Bereken Target Time
             try:
                  if 'Quantity' not in df_orders_filtered.columns:
                        st.error("Kolom 'Quantity' (hernoemd van 'Build Qty') niet gevonden voor berekening.")
                  elif EFFECTIVE_CAPACITY <= 0:
                        st.error("Effective capacity moet groter dan 0 zijn.")
                  else:
                        df_orders_filtered['Target_Time_Min'] = df_orders_filtered['Quantity'] / EFFECTIVE_CAPACITY

                        st.write(f"**Standaard effective capacity:** {EFFECTIVE_CAPACITY} stuks/minuut")
                        st.markdown("---")

                        # Toon Tabel
                        st.subheader("Berekende Target Tijden")
                        display_df_orders = df_orders_filtered[['Line', 'WO #', 'Item', 'Quantity', 'Target_Time_Min']].copy()
                        display_df_orders.rename(columns={'Quantity': 'Order Aantal', 'Target_Time_Min': 'Target Tijd (min)'}, inplace=True)
                        st.dataframe(display_df_orders, use_container_width=True, column_config={
                             "Target Tijd (min)": st.column_config.NumberColumn(format="%.1f")
                        })

                        st.markdown("---")
                        # Toon Scatter Plot
                        st.subheader("Visualisatie Aantal vs Targettijd")
                        if len(df_orders_filtered) > 1000:
                              st.info("Te veel datapunten (>1000) om scatter plot interactief te tonen. Overweeg kortere periode of specifieke lijn.")
                              # Optioneel: sample tonen? fig_order = px.scatter(df_orders_filtered.sample(1000), ...)
                        else:
                              fig_order = px.scatter(
                                  df_orders_filtered, x='Quantity', y='Target_Time_Min',
                                  color='Line', hover_data=['WO #', 'Item'],
                                  labels={'Quantity': 'Order Aantal', 'Target_Time_Min': 'Target Tijd (min)'},
                                  title="Order Aantal versus Berekende Targettijd"
                              )
                              st.plotly_chart(fig_order, use_container_width=True)

             except ZeroDivisionError:
                   st.error("Fout: Deling door nul bij berekenen Target Tijd (Effective Capacity mag geen 0 zijn).")
             except Exception as e:
                   st.error("Fout bij berekenen of tonen van Target Tijd.")
                   st.exception(e)

    # === FOOTER ===
    st.markdown("---")
    st.info("Einde dashboard. Vragen? Neem contact op met rob@proces360.com")

# === RUN DE APP ===
if __name__ == "__main__":
    main()
-")
    st.info("Einde dashboard. Vragen? Neem contact op met rob@proces360.com")

# === RUN DE APP ===
if __name__ == "__main__":
    main()
