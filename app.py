import streamlit as st
import pandas as pd
import requests
import os
import base64
from io import StringIO

from st_aggrid import (
    AgGrid,
    GridOptionsBuilder,
    GridUpdateMode,
    JsCode
)

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(layout="wide")

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1rem;
        padding-left: 1rem;
        padding-right: 1rem;
        max-width: 100%;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# =========================================================
# CONFIG
# =========================================================
GITHUB_REPO = "bolucunecva/plant-insect-interaction"
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
VALID_REVIEWERS = ["A", "B", "C", "D"]

# =========================================================
# REVIEWER
# =========================================================
query_params = st.query_params

reviewer = query_params.get("reviewer", "A")

if isinstance(reviewer, list):
    reviewer = reviewer[0]

reviewer = str(reviewer).strip().upper()

if reviewer not in VALID_REVIEWERS:
    reviewer = "A"

reviewer = st.sidebar.selectbox(
    "Select Reviewer",
    VALID_REVIEWERS,
    index=VALID_REVIEWERS.index(reviewer)
)

st.sidebar.info(f"Reviewer: {reviewer}")

# =========================================================
# DATA URL
# =========================================================
def get_csv_url(reviewer):
    return (
        f"https://raw.githubusercontent.com/"
        f"{GITHUB_REPO}/"
        f"{GITHUB_BRANCH}/"
        f"data/reviewer_{reviewer}.csv"
    )

# =========================================================
# LOAD DATA
# =========================================================
@st.cache_data
def load_data(reviewer):
    url = get_csv_url(reviewer)

    try:
        df = pd.read_csv(url, dtype=str, low_memory=False).fillna("")
        return df

    except pd.errors.EmptyDataError:
        st.warning("CSV is empty.")
        return pd.DataFrame()

    except Exception as e:
        st.error(f"Load failed: {e}")
        st.stop()

# =========================================================
# SAVE TO GITHUB
# =========================================================
def save_to_github(df, reviewer, token):

    github_file_path = f"data/reviewer_{reviewer}.csv"
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{github_file_path}"

    headers = {"Authorization": f"token {token}"}

    r = requests.get(api_url, headers=headers)
    if r.status_code != 200:
        return r.status_code, r.text

    sha = r.json()["sha"]

    buffer = StringIO()
    df.to_csv(buffer, index=False)

    encoded = base64.b64encode(buffer.getvalue().encode()).decode()

    payload = {
        "message": f"Update dataset (reviewer {reviewer})",
        "content": encoded,
        "branch": GITHUB_BRANCH,
        "sha": sha
    }

    r = requests.put(api_url, json=payload, headers=headers)
    return r.status_code, r.text

# =========================================================
# TITLE
# =========================================================
st.title("Review Tool")
st.caption(f"Reviewer: {reviewer}")

# =========================================================
# LOAD DATA
# =========================================================
df = load_data(reviewer)

if df.empty:
    st.info("No data found.")
    st.stop()

# =========================================================
# ORIGINAL COPY (IMPORTANT FOR COLOR DIFF)
# =========================================================
original_df = df.copy().reset_index(drop=True)
df = df.reset_index(drop=True)

df["_row_id"] = df.index
original_df["_row_id"] = original_df.index

# =========================================================
# CREATE CHANGE FLAGS (CRITICAL FIX)
# =========================================================
for col in df.columns:
    if col in ["_row_id"]:
        continue

    df[f"_changed_{col}"] = df[col] != original_df[col]

# =========================================================
# CELL COLORING
# =========================================================
cellstyle_jscode = JsCode("""
function(params) {

    const field = params.colDef.field;

    const changeField = "_changed_" + field;

    if (params.data && params.data[changeField] === true) {
        return {
            backgroundColor: "#fff3cd",
            color: "black"
        }
    }

    return {
        backgroundColor: "white",
        color: "black"
    }
}
""")

# =========================================================
# GRID SETUP
# =========================================================
gb = GridOptionsBuilder.from_dataframe(df)

gb.configure_default_column(
    editable=True,
    filter=True,
    sortable=True,
    resizable=True,
    floatingFilter=True,
    cellStyle=cellstyle_jscode
)

# Hide helper columns
gb.configure_column("_row_id", hide=True)

for col in df.columns:
    if col.startswith("_changed_"):
        gb.configure_column(col, hide=True)

gb.configure_selection(
    selection_mode="multiple",
    use_checkbox=True
)

grid_options = gb.build()

# =========================================================
# TABLE
# =========================================================
st.subheader("Dataset (Excel-like view)")

grid_response = AgGrid(
    df,
    gridOptions=grid_options,
    update_mode=GridUpdateMode.VALUE_CHANGED,
    allow_unsafe_jscode=True,
    height=700,
    theme="streamlit"
)

# =========================================================
# EDITED DATA
# =========================================================
edited_df = pd.DataFrame(grid_response["data"])

# Remove helper columns before saving
drop_cols = [c for c in edited_df.columns if c.startswith("_changed_")]
edited_df = edited_df.drop(columns=drop_cols, errors="ignore")

if "_row_id" in edited_df.columns:
    edited_df = edited_df.drop(columns=["_row_id"])

st.divider()

# =========================================================
# SAVE
# =========================================================
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

if not GITHUB_TOKEN:
    st.warning("Missing GITHUB_TOKEN — saving disabled")

if st.button("Save to GitHub"):

    if not GITHUB_TOKEN:
        st.error("No GitHub token")

    else:
        with st.spinner("Saving..."):

            status, resp = save_to_github(
                edited_df,
                reviewer,
                GITHUB_TOKEN
            )

            if status in [200, 201]:
                st.success("Saved successfully!")
                st.cache_data.clear()

            elif status == 409:
                st.error("Conflict detected. Reload required.")

            else:
                st.error(f"Save failed ({status})")
                st.code(resp)

# =========================================================
# SUMMARY
# =========================================================
st.subheader("Summary")

st.metric("Rows", len(edited_df))
