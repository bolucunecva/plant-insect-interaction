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
# CONFIG
# =========================================================
st.set_page_config(layout="wide")

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
# LOAD DATA
# =========================================================
def get_csv_url(reviewer):
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/data/reviewer_{reviewer}.csv"

@st.cache_data
def load_data(reviewer):
    return pd.read_csv(get_csv_url(reviewer), dtype=str).fillna("")

df_original = load_data(reviewer)

if df_original.empty:
    st.stop()

# =========================================================
# SHOW SINGLE EDITABLE GRID (ONLY ONCE)
# =========================================================
gb = GridOptionsBuilder.from_dataframe(df_original)

gb.configure_default_column(
    editable=True,
    filter=True,
    sortable=True,
    resizable=True,
    floatingFilter=True
)

grid_response = AgGrid(
    df_original,
    gridOptions=gb.build(),
    update_mode=GridUpdateMode.VALUE_CHANGED,
    allow_unsafe_jscode=True,
    height=700,
    theme="streamlit",
    key="main_grid"
)

# =========================================================
# GET EDITED DATA
# =========================================================
df_edited = pd.DataFrame(grid_response["data"]).fillna("")

# =========================================================
# COMPUTE CHANGES (NO SECOND GRID)
# =========================================================
df_display = df_edited.copy()

for col in df_original.columns:
    df_display[f"_changed_{col}"] = df_edited[col] != df_original[col]

# =========================================================
# CELL COLORING
# =========================================================
cell_style = JsCode("""
function(params) {
    const field = params.colDef.field;
    const changedField = "_changed_" + field;

    if (params.data && params.data[changedField] === true) {
        return {
            backgroundColor: "#fff3cd"
        };
    }
    return null;
}
""")

# =========================================================
# RE-RENDER SAME GRID DATA WITH HIGHLIGHT (SAME GRID LOGIC)
# =========================================================
gb2 = GridOptionsBuilder.from_dataframe(df_display)

gb2.configure_default_column(
    editable=True,
    filter=True,
    sortable=True,
    resizable=True,
    floatingFilter=True,
    cellStyle=cell_style
)

for col in df_display.columns:
    if col.startswith("_changed_"):
        gb2.configure_column(col, hide=True)

st.subheader("Dataset")


AgGrid(
    df_display,
    gridOptions=gb2.build(),
    update_mode=GridUpdateMode.VALUE_CHANGED,
    allow_unsafe_jscode=True,
    height=700,
    theme="streamlit",
    key="highlight_grid"
)
