import streamlit as st
import pandas as pd
import requests
import os

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

    div[data-testid="stDataEditor"] {
        width: 100% !important;
    }

    /* Highlight edited cells */
    .edited-cell {
        background-color: #fff3cd !important;
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
# FAST RAW URL
# ----------------------------
def get_csv_url(reviewer):
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/data/reviewer_{reviewer}.csv"

# ----------------------------
# LOAD DATA
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
# SAVE TO GITHUB
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

# Keep original copy for comparison
original_df = df.copy()

# ----------------------------
# FILTERS
# ----------------------------
st.sidebar.header("Filters")

filtered_df = df.copy()

# Global search
search_text = st.sidebar.text_input("Search")

if search_text:
    filtered_df = filtered_df[
        filtered_df.astype(str)
        .apply(
            lambda row: row.str.contains(
                search_text,
                case=False,
                na=False
            ).any(),
            axis=1
        )
    ]

# Column filters
filter_columns = st.sidebar.multiselect(
    "Filter Columns",
    options=filtered_df.columns.tolist()
)

for col in filter_columns:

    unique_values = sorted(
        filtered_df[col]
        .astype(str)
        .dropna()
        .unique()
        .tolist()
    )

    selected_values = st.sidebar.multiselect(
        f"{col}",
        options=unique_values,
        default=unique_values
    )

    filtered_df = filtered_df[
        filtered_df[col].astype(str).isin(selected_values)
    ]

# ----------------------------
# COLUMN VISIBILITY
# ----------------------------
visible_columns = st.sidebar.multiselect(
    "Visible Columns",
    options=filtered_df.columns.tolist(),
    default=filtered_df.columns.tolist()
)

filtered_df = filtered_df[visible_columns]

# ----------------------------
# EDITOR
# ----------------------------
st.subheader("Edit Dataset")

edited_df = st.data_editor(
    filtered_df,
    use_container_width=True,
    hide_index=True,
    num_rows="dynamic",
    key="editor"
)

# ----------------------------
# HIGHLIGHT CHANGED CELLS
# ----------------------------
def highlight_changes(val, row_idx, col_name):
    try:
        original_val = str(original_df.iloc[row_idx][col_name])

        if str(val) != original_val:
            return "background-color: #fff3cd"

    except:
        pass

    return ""

styled_df = edited_df.style.apply(
    lambda col: [
        highlight_changes(v, i, col.name)
        for i, v in enumerate(col)
    ]
)

st.subheader("Highlighted Changes")

st.dataframe(
    styled_df,
    use_container_width=True,
    hide_index=True
)

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
                st.error("Conflict: file updated elsewhere. Reload and retry.")

            else:
                st.error(f"Save failed ({status}): {resp}")

# ----------------------------
# SUMMARY
# ----------------------------
st.subheader("Summary")

st.metric("Total Rows", len(edited_df))
