import streamlit as st
import pandas as pd
import os

from st_aggrid import (
    AgGrid,
    GridOptionsBuilder,
    GridUpdateMode,
    JsCode
)

# =========================================================
# CONFIG
# =========================================================
st.set_page_config(layout="wide")

GITHUB_REPO = "bolucunecva/plant-insect-interaction"
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
VALID_REVIEWERS = ["A", "B", "C", "D"]

# =========================================================
# REVIEWER
# =========================================================
reviewer = st.query_params.get("reviewer", "A")
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
# LOAD DATA
# =========================================================
def get_csv_url(reviewer):
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/data/reviewer_{reviewer}.csv"

@st.cache_data
def load_data(reviewer):
    return pd.read_csv(get_csv_url(reviewer), dtype=str).fillna("")

df = load_data(reviewer)
if df.empty:
    st.stop()

df = df.reset_index(drop=True)

# =========================================================
# STORE ORIGINAL IN SESSION (IMPORTANT)
# =========================================================
if "original_df" not in st.session_state:
    st.session_state.original_df = df.copy()

original_df = st.session_state.original_df

# =========================================================
# JS: CELL CHANGE DETECTION (NO SECOND GRID)
# =========================================================
cell_style = JsCode(f"""
function(params) {{

    const original = {original_df.to_json(orient='records')};

    const rowIndex = params.node.rowIndex;
    const colId = params.colDef.field;

    if (!original[rowIndex]) return null;

    const originalValue = original[rowIndex][colId];
    const currentValue = params.value;

    if (originalValue !== currentValue) {{
        return {{
            backgroundColor: '#fff3cd'
        }};
    }}

    return null;
}}
""")

# =========================================================
# SINGLE GRID ONLY
# =========================================================
gb = GridOptionsBuilder.from_dataframe(df)

gb.configure_default_column(
    editable=True,
    filter=True,
    sortable=True,
    resizable=True,
    floatingFilter=True,
    cellStyle=cell_style
)

grid_response = AgGrid(
    df,
    gridOptions=gb.build(),
    update_mode=GridUpdateMode.VALUE_CHANGED,
    allow_unsafe_jscode=True,
    height=700,
    theme="streamlit",
    key="single_grid"
)

# =========================================================
# GET EDITED DATA
# =========================================================
edited_df = pd.DataFrame(grid_response["data"])

st.divider()
st.metric("Rows", len(edited_df))
