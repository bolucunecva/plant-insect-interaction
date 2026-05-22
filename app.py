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
    url = get_csv_url(reviewer)
    df = pd.read_csv(url, dtype=str, low_memory=False).fillna("")
    return df

df = load_data(reviewer)

if df.empty:
    st.stop()

original_df = df.copy().reset_index(drop=True)

# =========================================================
# GRID (USER EDITS HERE)
# =========================================================
gb = GridOptionsBuilder.from_dataframe(df)

gb.configure_default_column(
    editable=True,
    filter=True,
    sortable=True,
    resizable=True,
    floatingFilter=True
)

grid_response = AgGrid(
    df,
    gridOptions=gb.build(),
    update_mode=GridUpdateMode.VALUE_CHANGED,
    allow_unsafe_jscode=True,
    height=700,
    theme="streamlit"
)

# =========================================================
# GET EDITED DATA
# =========================================================
edited_df = pd.DataFrame(grid_response["data"]).fillna("")
edited_df = edited_df.reset_index(drop=True)
original_df = original_df.reset_index(drop=True)

# =========================================================
# BUILD CHANGE MAP (PER CELL)
# =========================================================
change_map = pd.DataFrame(False, index=edited_df.index, columns=edited_df.columns)

for col in edited_df.columns:
    change_map[col] = edited_df[col] != original_df[col]

# attach hidden metadata columns
df_display = edited_df.copy()

for col in edited_df.columns:
    df_display[f"_changed_{col}"] = change_map[col]

# =========================================================
# CELL STYLE (HIGHLIGHT ONLY IF EDITED)
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
        backgroundColor: "white"
    }
}
""")

# =========================================================
# FINAL GRID (ONLY ONE GRID SHOWN)
# =========================================================
gb2 = GridOptionsBuilder.from_dataframe(df_display)

gb2.configure_default_column(
    editable=True,
    filter=True,
    sortable=True,
    resizable=True,
    floatingFilter=True,
    cellStyle=cellstyle_jscode
)

# hide helper columns
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
    theme="streamlit"
)

# =========================================================
# FINAL CLEAN DATA (FOR SAVE)
# =========================================================
final_df = df_display.drop(
    columns=[c for c in df_display.columns if c.startswith("_changed_")],
    errors="ignore"
)

# =========================================================
# SAVE
# =========================================================
st.divider()

if st.button("Save"):
    st.success("Ready to save (connect your GitHub function here)")
