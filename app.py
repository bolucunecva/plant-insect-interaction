import streamlit as st
import pandas as pd
import requests
import os

# ----------------------------
# PAGE CONFIG
# ----------------------------
st.set_page_config(
    page_title="Review Tool",
    layout="wide"
)

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

    section[data-testid="stSidebar"] {
        width: 320px !important;
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
# RAW CSV URL
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

    api_url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_REPO}/contents/{github_file_path}"
    )

    headers = {
        "Authorization": f"token {token}"
    }

    # Get current SHA
    r = requests.get(api_url, headers=headers)

    if r.status_code != 200:
        return r.status_code, r.text

    sha = r.json().get("sha")

    # Convert dataframe to CSV
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
    st.info("No data found — showing empty table.")
    df = pd.DataFrame()

# ----------------------------
# SESSION STATE
# ----------------------------
if "original_df" not in st.session_state:
    st.session_state.original_df = df.copy()

# ----------------------------
# FILTERS
# ----------------------------
st.sidebar.subheader("Filters")

filtered_df = df.copy()

for col in df.columns:

    unique_values = sorted(
        [
            str(v)
            for v in df[col].dropna().unique()
            if str(v).strip() != ""
        ]
    )

    # Avoid huge filters
    if 0 < len(unique_values) <= 50:

        selected_values = st.sidebar.multiselect(
            f"{col}",
            unique_values,
            default=unique_values
        )

        filtered_df = filtered_df[
            filtered_df[col].astype(str).isin(selected_values)
        ]

# ----------------------------
# HIGHLIGHT CHANGES
# ----------------------------
def highlight_changes(row_idx, col_name, value):

    try:
        original_df = st.session_state.original_df

        if row_idx >= len(original_df):
            return ""

        old_value = str(original_df.iloc[row_idx][col_name])
        new_value = str(value)

        if old_value != new_value:
            return "background-color: #fff3cd"

    except:
        pass

    return ""

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
# VISUAL CHANGE PREVIEW
# ----------------------------
st.subheader("Changed Cells Preview")

styled_df = edited_df.copy()

def style_dataframe(df_to_style):

    styles = pd.DataFrame(
        "",
        index=df_to_style.index,
        columns=df_to_style.columns
    )

    original_df = st.session_state.original_df

    common_rows = min(
        len(df_to_style),
        len(original_df)
    )

    for row in range(common_rows):

        for col in df_to_style.columns:

            try:
                old = str(original_df.iloc[row][col])
                new = str(df_to_style.iloc[row][col])

                if old != new:
                    styles.iloc[row, df_to_style.columns.get_loc(col)] = (
                        "background-color: #fff3cd"
                    )

            except:
                pass

    return styles

st.dataframe(
    styled_df.style.apply(
        style_dataframe,
        axis=None
    ),
    use_container_width=True
)

st.divider()

# ----------------------------
# SAVE
# ----------------------------
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

if not GITHUB_TOKEN:
    st.warning("Missing GITHUB_TOKEN — saving disabled")

col1, col2 = st.columns([1, 5])

with col1:

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

                    st.session_state.original_df = edited_df.copy()

                elif status == 409:

                    st.error(
                        "Conflict: file updated elsewhere. "
                        "Reload and retry."
                    )

                else:

                    st.error(
                        f"Save failed ({status}): {resp}"
                    )

with col2:
    st.info(
        "Changed cells are highlighted in yellow "
        "in the preview table below."
    )

# ----------------------------
# SUMMARY
# ----------------------------
st.subheader("Summary")

c1, c2 = st.columns(2)

with c1:
    st.metric("Total Rows", len(edited_df))

with c2:

    changed_cells = 0

    original_df = st.session_state.original_df

    common_rows = min(
        len(edited_df),
        len(original_df)
    )

    for row in range(common_rows):

        for col in edited_df.columns:

            try:
                if (
                    str(original_df.iloc[row][col])
                    !=
                    str(edited_df.iloc[row][col])
                ):
                    changed_cells += 1

            except:
                pass

    st.metric("Changed Cells", changed_cells)
