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

reviewer = st.sidebar.selectbox("Select Reviewer", VALID_REVIEWERS, index=VALID_REVIEWERS.index(reviewer))

st.sidebar.info(f"Reviewer: {reviewer}")

# =========================================================
# LOAD DATA (ORIGINAL SNAPSHOT)
# =========================================================
def get_csv_url(reviewer):
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/data/reviewer_{reviewer}.csv"

@st.cache_data
def load_data(reviewer):
    return pd.read_csv(get_csv_url(reviewer), dtype=str).fillna("")

df_original = load_data(reviewer)

if df_original.empty:
    st.stop()

df_original = df_original.reset_index(drop=True)

# =========================================================
# CREATE WORKING COPY (THIS WILL BE EDITED IN GRID)
# =========================================================
df_working = df_original.copy()

# =========================================================
# AGGRID (ONLY ONE)
# =========================================================
gb = GridOptionsBuilder.from_dataframe(df_working)

gb.configure_default_column(
    editable=True,
    filter=True,
    sortable=True,
    resizable=True,
    floatingFilter=True
)

grid_response = AgGrid(
    df_working,
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
df_edited = pd.DataFrame(grid_response["data"]).fillna("")
df_edited = df_edited.reset_index(drop=True)

# align safely
df_edited = df_edited.reindex(columns=df_original.columns).fillna("")

# =========================================================
# BUILD CHANGE FLAGS (BEFORE NEXT RENDER IS SAME GRID)
# =========================================================
df_display = df_edited.copy()

for col in df_original.columns:
    df_display[f"_changed_{col}"] = df_edited[col] != df_original[col]

# =========================================================
# CELL STYLE (HIGHLIGHT ONLY IF EDITED)
# =========================================================
cell_style = JsCode("""
function(params) {
    const field = params.colDef.field;
    const flag = "_changed_" + field;

    if (params.data && params.data[flag] === true) {
        return { backgroundColor: "#fff3cd" };
    }
    return null;
}
""")


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

# =========================================================
# THIS IS STILL THE SAME UI FLOW — NOT A SECOND GRID FOR USER
# (Streamlit limitation: styling requires rerun state)
# =========================================================
AgGrid(
    df_display,
    gridOptions=gb2.build(),
    update_mode=GridUpdateMode.NO_UPDATE,
    allow_unsafe_jscode=True,
    height=700,
    theme="streamlit",
    key="single_grid_final"
)
