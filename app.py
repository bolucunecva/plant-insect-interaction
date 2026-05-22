import streamlit as st
import pandas as pd
import requests
import os
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode, JsCode

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

    /* Force AG Grid to fill the full container width */
    .ag-theme-streamlit,
    .ag-theme-alpine,
    .ag-theme-balham {
        width: 100% !important;
        min-width: 100% !important;
    }

    /* Make the AG Grid iframe wrapper mouse-resizable in both directions */
    div[data-testid="stCustomComponentV1"] {
        resize: both !important;
        overflow: hidden !important;
        min-height: 200px !important;
        min-width: 300px !important;
        max-width: 100% !important;
        width: 100% !important;
        /* Show a grab cursor hint at bottom-right corner */
        padding-bottom: 6px;
        box-sizing: border-box;
    }

    div[data-testid="stCustomComponentV1"] > iframe {
        width: 100% !important;
        height: 100% !important;
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
# FAST RAW URL (IMPORTANT FIX)
# ----------------------------
def get_csv_url(reviewer):
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/data/reviewer_{reviewer}.csv"

# ----------------------------
# LOAD DATA (FAST + STREAMING FRIENDLY)
# ----------------------------
@st.cache_data
def load_data(reviewer):
    url = get_csv_url(reviewer)

    try:
        df = pd.read_csv(url, dtype=str, low_memory=False).fillna("")
        return df

    except pd.errors.EmptyDataError:
        st.warning("CSV is empty. Starting with empty table.")
        return pd.DataFrame()

    except Exception as e:
        st.error(f"Failed to load CSV: {e}")
        st.stop()

# ----------------------------
# SAVE BACK TO GITHUB (API ONLY FOR WRITE)
# ----------------------------
def save_to_github(df, reviewer, token):
    import base64
    from io import StringIO

    github_file_path = f"data/reviewer_{reviewer}.csv"
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{github_file_path}"

    headers = {
        "Authorization": f"token {token}"
    }

    # Get SHA
    r = requests.get(api_url, headers=headers)
    if r.status_code != 200:
        return r.status_code, r.text

    sha = r.json().get("sha")

    # Convert dataframe to CSV
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
    st.info("No data found — showing empty table.")
    df = pd.DataFrame()

# ----------------------------
# TRACK ORIGINAL DATA (for change detection)
# ----------------------------
orig_key = f"original_df_{reviewer}"
if orig_key not in st.session_state:
    st.session_state[orig_key] = df.copy()

original_df = st.session_state[orig_key]

# ----------------------------
# EDITOR WITH COLUMN-HEADER FILTERS + CHANGE HIGHLIGHTING
# ----------------------------
st.subheader("Edit Dataset")

# Embed original values as hidden columns so the JS cellStyle can compare
grid_df = df.copy()
if not original_df.empty:
    for col in df.columns.intersection(original_df.columns):
        grid_df[f"__orig_{col}"] = original_df[col].reindex(df.index).fillna("")

gb = GridOptionsBuilder.from_dataframe(grid_df)

# Visible, editable columns with floating (in-header) filter + change highlight
for col in df.columns:
    orig_field = f"__orig_{col}"
    cell_style_js = JsCode(f"""
        function(params) {{
            var orig = params.data['{orig_field}'];
            if (orig !== undefined && String(params.value) !== String(orig)) {{
                return {{backgroundColor: '#fff3cd', color: '#856404', fontWeight: 'bold'}};
            }}
            return null;
        }}
    """)
    gb.configure_column(
        col,
        editable=True,
        filter="agTextColumnFilter",
        floatingFilter=True,
        cellStyle=cell_style_js,
        resizable=True,
        sortable=True,
    )

# Hide the shadow __orig_ columns
for col in df.columns:
    gb.configure_column(f"__orig_{col}", hide=True)

gb.configure_grid_options(
    suppressMovableColumns=False,
    enableRangeSelection=True,
    domLayout="normal",
)
gb.configure_selection(selection_mode="disabled")

grid_options = gb.build()

grid_response = AgGrid(
    grid_df,
    gridOptions=grid_options,
    update_mode=GridUpdateMode.VALUE_CHANGED,
    data_return_mode=DataReturnMode.AS_INPUT,   # return ALL rows (filtered ones just hidden)
    allow_unsafe_jscode=True,
    fit_columns_on_grid_load=True,
    use_container_width=True,
    height=500,
    theme="streamlit",
)

# Extract edited data (drop hidden __orig_ columns before saving)
returned = pd.DataFrame(grid_response["data"]) if grid_response["data"] is not None else df.copy()
visible_cols = [c for c in returned.columns if not c.startswith("__orig_")]
edited_df = returned[visible_cols] if not returned.empty else df.copy()

st.divider()

# ----------------------------
# SAVE
# ----------------------------
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

if not GITHUB_TOKEN:
    st.warning("Missing GITHUB_TOKEN — saving disabled")

if st.button("Save"):
    if not GITHUB_TOKEN:
        st.error("No GitHub token")
    else:
        with st.spinner("Saving..."):
            status, resp = save_to_github(edited_df, reviewer, GITHUB_TOKEN)

            if status in [200, 201]:
                st.success("Saved successfully!")
                st.cache_data.clear()
                # Update baseline so highlights reset after a successful save
                st.session_state[orig_key] = edited_df.copy()

            elif status == 409:
                st.error("Conflict: file updated elsewhere. Reload and retry.")

            else:
                st.error(f"Save failed ({status}): {resp}")

# ----------------------------
# SUMMARY
# ----------------------------
st.subheader("Summary")
st.metric("Total Rows", len(edited_df))
