import streamlit as st
import pandas as pd
import requests
import os
from st_aggrid import (
    AgGrid,
    GridOptionsBuilder,
    GridUpdateMode,
    JsCode
)

# ----------------------------
# PAGE CONFIG
# ----------------------------
st.set_page_config(layout="wide")

st.markdown(
    """
    <style>
    .block-container {
        padding-left: 1rem;
        padding-right: 1rem;
        max-width: 100%;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# ----------------------------
# CONFIG
# ----------------------------
GITHUB_REPO = "bolucunecva/plant-insect-interaction"
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")

VALID_REVIEWERS = ["A", "B", "C", "D"]

# ----------------------------
# REVIEWER SELECTION
# ----------------------------
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

# ----------------------------
# CSV URL
# ----------------------------
def get_csv_url(reviewer):
    return (
        f"https://raw.githubusercontent.com/"
        f"{GITHUB_REPO}/{GITHUB_BRANCH}/data/reviewer_{reviewer}.csv"
    )

# ----------------------------
# LOAD DATA
# ----------------------------
@st.cache_data
def load_data(reviewer):

    url = get_csv_url(reviewer)

    try:
        df = pd.read_csv(
            url,
            dtype=str,
            low_memory=False
        ).fillna("")

        return df

    except pd.errors.EmptyDataError:
        st.warning("CSV is empty.")
        return pd.DataFrame()

    except Exception as e:
        st.error(f"Failed to load CSV: {e}")
        st.stop()

# ----------------------------
# SAVE TO GITHUB
# ----------------------------
def save_to_github(df, reviewer, token):

    import base64
    from io import StringIO

    github_file_path = f"data/reviewer_{reviewer}.csv"

    api_url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_REPO}/contents/{github_file_path}"
    )

    headers = {
        "Authorization": f"token {token}"
    }

    # Get current file SHA
    r = requests.get(api_url, headers=headers)

    if r.status_code != 200:
        return r.status_code, r.text

    sha = r.json().get("sha")

    # Convert DF -> CSV
    buffer = StringIO()

    df.to_csv(buffer, index=False)

    encoded = base64.b64encode(
        buffer.getvalue().encode()
    ).decode()

    payload = {
        "message": f"Update dataset (reviewer {reviewer})",
        "content": encoded,
        "branch": GITHUB_BRANCH,
        "sha": sha
    }

    r = requests.put(
        api_url,
        json=payload,
        headers=headers
    )

    return r.status_code, r.text

# ----------------------------
# TITLE
# ----------------------------
st.title("Review Tool")

st.caption(f"Reviewer: {reviewer}")

# ----------------------------
# LOAD DATA
# ----------------------------
df = load_data(reviewer)

if df.empty:
    st.info("No data found.")
    st.stop()

# ----------------------------
# ADD ROW ID
# ----------------------------
df = df.reset_index(drop=True)

df["_row_id"] = df.index

# ----------------------------
# CELL COLOR FOR EDITED VALUES
# ----------------------------
cellstyle_jscode = JsCode(
    """
    function(params) {

        if (params.oldValue !== params.value) {
            return {
                'backgroundColor': '#fff3cd',
                'color': 'black'
            }
        }

        return null
    }
    """
)

# ----------------------------
# AGGRID CONFIG
# ----------------------------
gb = GridOptionsBuilder.from_dataframe(df)

gb.configure_default_column(
    editable=True,
    filter=True,
    sortable=True,
    resizable=True,
    floatingFilter=True,
    cellStyle=cellstyle_jscode
)

# Hide internal row id
gb.configure_column("_row_id", hide=True)

# Selection
gb.configure_selection(
    selection_mode="multiple",
    use_checkbox=True
)

# Grid options
gb.configure_grid_options(
    enableRangeSelection=True,
    rowSelection="multiple",
    animateRows=True
)

grid_options = gb.build()

# ----------------------------
# TABLE
# ----------------------------
st.subheader("Dataset")

st.info(
    "Excel-style filters are available in every column header."
)

grid_response = AgGrid(
    df,
    gridOptions=grid_options,
    update_mode=GridUpdateMode.VALUE_CHANGED,
    allow_unsafe_jscode=True,
    fit_columns_on_grid_load=False,
    height=700,
    theme="streamlit",
    reload_data=False
)

# ----------------------------
# UPDATED DATAFRAME
# ----------------------------
edited_df = pd.DataFrame(grid_response["data"])

# Remove helper column
if "_row_id" in edited_df.columns:
    edited_df = edited_df.drop(columns=["_row_id"])

st.divider()

# ----------------------------
# SAVE
# ----------------------------
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

                st.error(
                    "Conflict detected. "
                    "File changed elsewhere. Reload and retry."
                )

            else:

                st.error(
                    f"Save failed ({status}): {resp}"
                )

# ----------------------------
# SUMMARY
# ----------------------------
st.subheader("Summary")

st.metric("Total Rows", len(edited_df))

st.metric("Total Columns", len(edited_df.columns))
