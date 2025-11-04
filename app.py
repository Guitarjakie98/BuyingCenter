import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

# =====================================================
# PAGE CONFIG
# =====================================================
st.set_page_config(
    page_title="Citrix Data Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📊 Citrix Data Dashboard")

# =====================================================
# LOAD DATA FUNCTIONS
# =====================================================
@st.cache_data(show_spinner=False)
def load_data(path):
    df = pd.read_csv(path)

    # Handle date columns flexibly
    date_col = None
    for col in ["Activity Date", "Activity_DateOnly", "Date"]:
        if col in df.columns:
            date_col = col
            break

    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce", utc=True)
    else:
        st.error("No date column found (expected one of: Activity Date, Activity_DateOnly, Date).")
        st.stop()

    df["__date_col__"] = df[date_col]
    return df


@st.cache_data(show_spinner=False)
def load_demandbase_data(path):
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip()
    return df


# =====================================================
# FILE PATHS
# =====================================================
default_path = "/Applications/WorkDataSets/combined_cleaned_full.csv"
default_demandbase_path = "/Applications/WorkDataSets/Database/Demandbase_techno_F5_analysis.csv"

DATA_PATH = st.sidebar.text_input("Enter Main CSV path:", default_path)
DB_PATH = st.sidebar.text_input("Enter Demandbase CSV path:", default_demandbase_path)

if not DATA_PATH or not DB_PATH:
    st.stop()

# =====================================================
# LOAD DATA
# =====================================================
df = load_data(DATA_PATH)
db_df = load_demandbase_data(DB_PATH)

st.success(f"✅ Main dataset loaded: {len(df):,} rows, {len(df.columns)} columns")
st.success(f"✅ Demandbase dataset loaded: {len(db_df):,} rows, {len(db_df.columns)} columns")

# =====================================================
# MERGE DATASETS
# =====================================================
if "CustomerId_NAR" in df.columns and "CustomerId_NAR" in db_df.columns:
    merged = pd.merge(df, db_df, on="CustomerId_NAR", how="left", suffixes=("", "_DB"))
else:
    st.error("Could not find matching 'CustomerId_NAR' column in both datasets.")
    st.stop()

# =====================================================
# SIDEBAR FILTERS
# =====================================================
st.sidebar.header("🔍 Filters")

if "Type" in merged.columns:
    type_options = sorted(merged["Type"].dropna().unique())
    selected_types = st.sidebar.multiselect("Activity Type", type_options, default=type_options[:10])
else:
    selected_types = []

if "Account Name" in merged.columns:
    account_options = sorted(merged["Account Name"].dropna().unique())
    selected_accounts = st.sidebar.multiselect("Account", account_options, default=account_options[:10])
else:
    selected_accounts = []

min_date = merged["__date_col__"].min()
max_date = merged["__date_col__"].max()
start, end = st.sidebar.date_input("Date Range", [min_date, max_date])

filtered = merged.copy()

if selected_types:
    filtered = filtered[filtered["Type"].isin(selected_types)]
if selected_accounts:
    filtered = filtered[filtered["Account Name"].isin(selected_accounts)]
if start and end:
    filtered = filtered[(filtered["__date_col__"] >= pd.Timestamp(start, tz="UTC")) &
                        (filtered["__date_col__"] <= pd.Timestamp(end, tz="UTC"))]

st.write(f"**Filtered Results:** {len(filtered):,} rows")
st.dataframe(filtered.head(100))

# =====================================================
# CHART 1 — TOP 10 ACCOUNTS BY NAMED ENGAGEMENTS
# =====================================================
st.subheader("🏆 Top 10 Accounts by Named Engagements")

named = filtered[
    (filtered["First Name"].notna()) & (filtered["First Name"].str.strip() != "")
]

if not named.empty:
    top_accounts = (
        named.groupby("Account Name")
        .size()
        .reset_index(name="Activity Count")
        .sort_values(by="Activity Count", ascending=False)
        .head(10)
    )

    fig1 = px.bar(
        top_accounts,
        x="Account Name",
        y="Activity Count",
        text="Activity Count",
        color="Activity Count",
        color_continuous_scale="Tealgrn",
        title="Top 10 Accounts with the Most Named Activities"
    )

    fig1.update_traces(textposition="outside")
    fig1.update_layout(
        xaxis_title="Account Name",
        yaxis_title="Activity Count",
        showlegend=False,
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis_tickangle=-30,
        height=500
    )
    st.plotly_chart(fig1, use_container_width=True)
else:
    st.info("No records found with associated names.")

# =====================================================
# CHART 2 — ACCOUNT TIMELINE (NAMED ACTIVITIES)
# =====================================================
st.subheader("👤 Account-Level Engagement Timeline")

if "Account Name" in filtered.columns:
    account_choice = st.selectbox(
        "Select an Account to Explore",
        sorted(filtered["Account Name"].dropna().unique())
    )

    account_data = filtered[
        (filtered["Account Name"] == account_choice) &
        (filtered["First Name"].notna()) & (filtered["First Name"].str.strip() != "")
    ].copy()

    if not account_data.empty:
        # Combine Name + Buying Role
        account_data["Name + Role"] = account_data.apply(
            lambda x: f"{x['First Name']} {x['Last Name']} - {x['Buying Role']}"
            if pd.notna(x["Buying Role"]) and str(x["Buying Role"]).strip() != ""
            else f"{x['First Name']} {x['Last Name']}", axis=1
        )

        # Timeline scatter
        fig2 = px.scatter(
            account_data,
            x="__date_col__",
            y="Name + Role",
            color="First Name",
            symbol="Type",
            hover_data={
                "Type": True,
                "Details": True,
                "Buying Role": True,
                "__date_col__": "|%Y-%m-%d"
            },
            title=f"Engagement Timeline for {account_choice}",
            height=600
        )

        fig2.update_layout(
            yaxis_title="Name + Buying Role",
            xaxis_title="Engagement Date",
            plot_bgcolor="rgba(0,0,0,0)",
            legend_title="Person / Type",
            hovermode="closest"
        )
        st.plotly_chart(fig2, use_container_width=True)

        # =====================================================
        # 🏢 FIRMOGRAPHICS TABLE
        # =====================================================
        st.subheader("🏢 Firmographics")

        firmographic_cols = [
            "Account Name", "Technographics",
            "f5_core_adc_matches", "f5_core_adc_summary",
            "f5_security_matches", "f5_security_summary",
            "f5_cloud_services_matches", "f5_cloud_services_summary",
            "complementary_cloud_matches", "complementary_cloud_summary",
            "complementary_identity_matches", "complementary_identity_summary",
            "complementary_workspace_matches", "complementary_workspace_summary"
        ]

        if "CustomerId_NAR" in account_data.columns:
            firmographics = db_df[db_df["CustomerId_NAR"].isin(account_data["CustomerId_NAR"].unique())][
                [c for c in firmographic_cols if c in db_df.columns]
            ]

            if not firmographics.empty:
                st.dataframe(
                    firmographics.style.set_properties(**{
                        'white-space': 'pre-wrap',
                        'word-wrap': 'break-word'
                    }),
                    use_container_width=True
                )
            else:
                st.info("No Firmographics data available for this account.")
    else:
        st.warning("No named activities for this account.")
else:
    st.warning("No Account column found in dataset.")