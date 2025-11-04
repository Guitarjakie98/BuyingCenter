import streamlit as st
import pandas as pd
import plotly.express as px
import os
from datetime import datetime
import re

# =====================================================
# PAGE CONFIG
# =====================================================
st.set_page_config(
    page_title="Citrix Data Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("Citrix Data Dashboard")

# =====================================================
# FILE LOAD — DIRECTLY FROM GITHUB (NO UPLOADS NEEDED)
# =====================================================

st.sidebar.header("🌐 Loading Data from GitHub")

@st.cache_data
def load_csv_from_github(url):
    try:
        return pd.read_csv(url, encoding='latin1')
    except UnicodeDecodeError:
        return pd.read_csv(url, encoding='ISO-8859-1')
    except Exception as e:
        st.error(f"❌ Error loading {url}: {e}")
        st.stop()

# ---- Your actual dataset URLs ----
main_url = "https://raw.githubusercontent.com/Guitarjakie98/BuyingCenter/main/combined_DataStore%20copy.csv"
demand_url = "https://raw.githubusercontent.com/Guitarjakie98/BuyingCenter/main/Demandbase_techno_F5_analysis.parquet%20copy"
contacts_url = "https://raw.githubusercontent.com/Guitarjakie98/BuyingCenter/main/bqcontactdata%20copy.csv"

# ---- Load datasets ----
df = load_csv_from_github(main_url)
db_df = load_csv_from_github(demand_url)
contacts_df = load_csv_from_github(contacts_url)

st.sidebar.success("✅ Files loaded automatically from GitHub!")

# =====================================================
# FILE PATHS
# =====================================================
default_path = "/Applications/WorkDataSets/combined_cleaned_full.csv"
default_demandbase_path = "/Applications/WorkDataSets/Database/Demandbase_techno_F5_analysis.csv"
default_contacts_path = "/Applications/WorkDataSets/Database/bqcontactdata.csv"

DATA_PATH = st.sidebar.text_input("Enter Main CSV path:", default_path)
DB_PATH = st.sidebar.text_input("Enter Demandbase CSV path:", default_demandbase_path)
CONTACT_PATH = st.sidebar.text_input("Enter Contact CSV path:", default_contacts_path)

if not DATA_PATH or not DB_PATH or not CONTACT_PATH:
    st.stop()

# =====================================================
# LOAD DATA
# =====================================================
df, df_msg = load_data_auto(DATA_PATH)
db_df, db_msg = load_data_auto(DB_PATH)
contacts_df, contacts_msg = load_data_auto(CONTACT_PATH)

# =====================================================
# NORMALIZE COLUMN HEADERS
# =====================================================
df.columns = df.columns.str.strip()
db_df.columns = db_df.columns.str.strip()
contacts_df.columns = contacts_df.columns.str.strip()

# =====================================================
# ACCOUNT DROPDOWN
# =====================================================
st.sidebar.header("Select an Account")

if "Account Name" in df.columns:
    account_options = sorted(df["Account Name"].dropna().unique())
    account_choice = st.sidebar.selectbox(
        "Account (search and select one)",
        options=["-- Select an account --"] + account_options,
        index=0
    )
else:
    st.error("No 'Account Name' column found in dataset.")
    st.stop()

if account_choice == "-- Select an account --":
    st.info("Please select an account to view its data.")
    st.stop()

st.session_state["account_choice"] = account_choice

# =====================================================
# FILTER DATA FOR SELECTED ACCOUNT
# =====================================================
account_data = df[df["Account Name"] == account_choice].copy()
if account_data.empty:
    st.warning("No data available for this account.")
    st.stop()

# Normalize date columns
for col in ["Activity Date", "Activity_DateOnly", "Date"]:
    if col in account_data.columns:
        account_data["__date_col__"] = pd.to_datetime(account_data[col], errors="coerce", utc=True)
        break

# =====================================================
# CHART 1 — ENGAGEMENT TIMELINE
# =====================================================
st.subheader(f"Engagement Timeline for {account_choice}")

named = account_data[(account_data["First Name"].notna()) & (account_data["First Name"].str.strip() != "")]

if not named.empty:
    named["Name + Role"] = named.apply(
        lambda x: f"{x['First Name']} {x['Last Name']} - {x['Buying Role']}"
        if pd.notna(x["Buying Role"]) and str(x["Buying Role"]).strip() != ""
        else f"{x['First Name']} {x['Last Name']}", axis=1
    )

    fig = px.scatter(
        named,
        x="__date_col__",
        y="Name + Role",
        color="First Name",
        symbol="Type" if "Type" in named.columns else None,
        hover_data={
            "Type": True,
            "Details": True if "Details" in named.columns else False,
            "__date_col__": "|%Y-%m-%d"
        },
        title=f"Engagement Timeline for {account_choice}",
        height=600
    )

    fig.update_layout(
        yaxis_title="Name + Buying Role",
        xaxis_title="Engagement Date",
        plot_bgcolor="rgba(0,0,0,0)",
        legend_title="Person / Type",
        hovermode="closest"
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No named engagements found for this account.")

# =====================================================
# FIRMOGRAPHICS
# =====================================================
st.subheader("Firmographics")

if "CustomerId_NAR" in account_data.columns and "CustomerId_NAR" in db_df.columns:
    firmographics = db_df[db_df["CustomerId_NAR"].isin(account_data["CustomerId_NAR"].unique())]
    if not firmographics.empty:
        cols = [
            "Account Name", "Technographics",
            "f5_core_adc_matches", "f5_core_adc_summary",
            "f5_security_matches", "f5_security_summary",
            "f5_cloud_services_matches", "f5_cloud_services_summary",
            "complementary_cloud_matches", "complementary_cloud_summary",
            "complementary_identity_matches", "complementary_identity_summary",
            "complementary_workspace_matches", "complementary_workspace_summary"
        ]
        cols = [c for c in cols if c in firmographics.columns]
        st.dataframe(
            firmographics[cols].style.set_properties(**{
                'white-space': 'pre-wrap',
                'word-wrap': 'break-word'
            }),
            use_container_width=True
        )
    else:
        st.info("No firmographics data found for this account.")
else:
    st.warning("Firmographics join unavailable — missing 'CustomerId_NAR'.")

# =====================================================
# CONTACTS JOIN — SAFE NORMALIZATION
# =====================================================
possible_keys = ["party_number", "Party_Number", "party_id", "Party_ID"]
contact_key = next((k for k in possible_keys if k in contacts_df.columns), None)

if contact_key is None:
    st.error(f"❌ Could not find any of these join keys in contacts dataset: {possible_keys}")
    st.stop()

def normalize_id(x):
    if pd.isna(x):
        return None
    return (
        str(x)
        .strip()
        .upper()
        .replace("H-CIT-", "")
        .replace("H-", "")
        .replace("CIT-", "")
    )

contacts_df["party_number_clean"] = contacts_df[contact_key].apply(normalize_id)
df["CustomerId_NAR_clean"] = df["CustomerId_NAR"].apply(normalize_id)

matching_ids = (
    df.loc[df["Account Name"] == account_choice, "CustomerId_NAR_clean"]
    .dropna()
    .unique()
)

#st.write("🧩 Debug — Normalized matching IDs:", matching_ids[:10])
#st.write("🧩 Debug — Normalized party numbers:", contacts_df["party_number_clean"].dropna().unique()[:10])

account_contacts = contacts_df[
    contacts_df["party_number_clean"].isin(matching_ids)
].copy()

# =====================================================
# DERIVE ENGAGEMENT + COLOR SIGNALS
# =====================================================
engaged_names = set(
    zip(
        named["First Name"].fillna("").str.strip().str.lower(),
        named["Last Name"].fillna("").str.strip().str.lower(),
    )
)

def has_engaged_match(row):
    parts = str(row.get("party_unique_name", "")).strip().split()
    if len(parts) >= 2:
        first, last = parts[0].lower(), parts[-1].lower()
        return (first, last) in engaged_names
    return False

account_contacts["is_engaged"] = account_contacts.apply(has_engaged_match, axis=1)

if "sales_affinity_code" not in account_contacts.columns:
    account_contacts["sales_affinity_code"] = ""

def get_status_color(row):
    if str(row["sales_affinity_code"]).strip():
        return "purple"
    if row["is_engaged"]:
        return "yellow"
    return "red"

account_contacts["status_color"] = account_contacts.apply(get_status_color, axis=1)

# =====================================================
# FILTER CONTACTS AND DISPLAY
# =====================================================
st.sidebar.markdown("---")
st.sidebar.subheader("Contact Filters")

color_filter = st.sidebar.multiselect(
    "Show colors:",
    ["red", "yellow", "purple"],
    default=["red", "yellow", "purple"],
)
search_query = st.sidebar.text_input("🔎 Search name").strip().lower()

filtered_contacts = account_contacts[account_contacts["status_color"].isin(color_filter)].copy()

if search_query and "party_unique_name" in filtered_contacts.columns:
    filtered_contacts = filtered_contacts[
        filtered_contacts["party_unique_name"].astype(str).str.lower().str.contains(search_query, na=False)
    ]

if filtered_contacts.empty:
    st.info(f"No contacts found for {account_choice}.")
    st.stop()

# =====================================================
# FLAG ENGAGED CONTACTS
# =====================================================

# Create a set of engaged (first, last) pairs from your timeline dataset
engaged_pairs = set(
    zip(
        named["First Name"].fillna("").str.strip().str.lower(),
        named["Last Name"].fillna("").str.strip().str.lower()
    )
)

# Function to test if a contact appears in the engagement dataset
def check_engaged(name):
    if not isinstance(name, str):
        return False
    parts = name.strip().split()
    if len(parts) < 2:
        return False
    first, last = parts[0].lower(), parts[-1].lower()
    return (first, last) in engaged_pairs

# Apply the match
filtered_contacts["is_engaged"] = filtered_contacts["party_unique_name"].apply(check_engaged)

# =====================================================
# DISPLAY CONTACT CARDS
# =====================================================

# Inject CSS for layout
st.markdown("""
    <style>
    .contact-container {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 15px;
    }
    .contact-card {
        flex: 0 0 calc(20% - 10px);
        height: 105px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        border-radius: 10px;
        font-size: 13px;
        font-weight: 600;
        color: white;
        box-shadow: 0 2px 5px rgba(0,0,0,0.3);
        padding: 5px;
        text-align: center;
    }
    .red { background-color: #C0392B; }
    .yellow { background-color: #FFD600; color: black; }
    .purple { background-color: #9B59B6; }
    .contact-title {
        font-size: 11px;
        font-weight: 400;
        opacity: 0.85;
    }
    .contact-affinity {
        font-size: 10px;
        opacity: 0.75;
        font-style: italic;
        margin-top: 2px;
    }
    </style>
""", unsafe_allow_html=True)

# =====================================================
# DISPLAY CONTACT CARDS (FIXED HTML RENDER)
# =====================================================

# =====================================================
# DISPLAY CONTACT CARDS (with engagement dots)
# =====================================================

# Inject CSS styles
st.markdown("""
<style>
.contact-container {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-top: 15px;
}
.contact-card {
    position: relative;
    flex: 0 0 calc(20% - 10px);
    height: 105px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    border-radius: 10px;
    font-size: 13px;
    font-weight: 600;
    color: white;
    box-shadow: 0 2px 5px rgba(0,0,0,0.3);
    padding: 5px;
    text-align: center;
}
.red { background-color: #C0392B; }
.yellow { background-color: #FFD600; color: black; }
.purple { background-color: #9B59B6; }
.contact-title {
    font-size: 11px;
    font-weight: 400;
    opacity: 0.85;
}
.contact-affinity {
    font-size: 10px;
    opacity: 0.75;
    font-style: italic;
    margin-top: 2px;
}
.engaged-dot {
    position: absolute;
    top: 5px;
    left: 5px;
    width: 13px;
    height: 13px;
    background-color: #FFD600;
    border-radius: 50%;
    box-shadow: 0 0 8px rgba(255, 214, 0, 0.7);
}
</style>
""", unsafe_allow_html=True)

# Build cards as a single flat string (no indentation!)
cards_html = "<div class='contact-container'>"

for _, row in filtered_contacts.iterrows():
    name = row.get("party_unique_name", "Unknown")
    title = row.get("job_title", "")
    affinity = row.get("sales_affinity_code", "")
    color = row.get("status_color", "red")
    engaged_dot = "<div class='engaged-dot'></div>" if row.get("is_engaged", False) else ""

    # No indentation, otherwise Streamlit escapes the HTML
    cards_html += f"<div class='contact-card {color}'>{engaged_dot}<div>{name}</div><div class='contact-title'>{title}</div><div class='contact-affinity'>{affinity}</div></div>"

cards_html += "</div>"

# Render
st.markdown(cards_html, unsafe_allow_html=True)
st.caption(f"Showing {len(filtered_contacts):,} contacts for {account_choice}.")