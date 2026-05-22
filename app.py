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
# FILTER UI
# ----------------------------
with st.expander("Filter Rows", expanded=False):
    fcol1, fcol2, fcol3 = st.columns([2, 3, 2])
    with fcol1:
        col_opts = ["(all columns)"] + df.columns.tolist() if not df.empty else ["(all columns)"]
        filter_column = st.selectbox("Column", col_opts, key="filter_col")
    with fcol2:
        filter_text = st.text_input("Contains", key="filter_text", placeholder="Type to filter…")
    with fcol3:
        show_changed_only = st.checkbox("Changed rows only", key="show_changed")

# Apply filters
display_df = df.copy()

if filter_text and not display_df.empty:
    if filter_column == "(all columns)":
        mask = display_df.apply(
            lambda row: row.astype(str).str.contains(filter_text, case=False, na=False).any(),
            axis=1,
        )
    else:
        mask = display_df[filter_column].astype(str).str.contains(filter_text, case=False, na=False)
    display_df = display_df[mask]

if show_changed_only and not original_df.empty and not display_df.empty:
    common_cols = display_df.columns.intersection(original_df.columns)
    common_idx  = display_df.index.intersection(original_df.index)
    if len(common_idx):
        changed_mask = (
            display_df.loc[common_idx, common_cols] != original_df.loc[common_idx, common_cols]
        ).any(axis=1)
        display_df = display_df.loc[common_idx[changed_mask]]

st.caption(f"Showing {len(display_df)} / {len(df)} rows")

# ----------------------------
# EDITOR (NO SCHEMA LIMITS)
# ----------------------------
st.subheader("Edit Dataset")

edited_df = st.data_editor(
    df,
    use_container_width=True,
    hide_index=True,
    num_rows="dynamic"
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
            status, resp = save_to_github(edited_df, reviewer, GITHUB_TOKEN)

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
