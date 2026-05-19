import streamlit as st
import pandas as pd
import requests
import os
import base64
from io import StringIO

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
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = "bolucunecva/plant-insect-interaction"
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}"
} if GITHUB_TOKEN else {}

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

# Sidebar selector (interactive)
reviewer = st.sidebar.selectbox(
    "Select Reviewer",
    VALID_REVIEWERS,
    index=VALID_REVIEWERS.index(reviewer)
)

st.sidebar.info(f"Current reviewer: {reviewer}")

# ----------------------------
# LOAD DATA (CACHE KEYED BY REVIEWER)
# ----------------------------
@st.cache_data
def load_data(reviewer):
    github_file_path = f"data/reviewer_{reviewer}.csv"

    api_url = (
        f"https://api.github.com/repos/{GITHUB_REPO}/contents/{github_file_path}"
        f"?ref={GITHUB_BRANCH}"
    )

    r = requests.get(api_url, headers=HEADERS)

    if r.status_code == 404:
        st.error(f"File not found: {github_file_path}")
        st.stop()

    if r.status_code != 200:
        st.error(f"GitHub API error {r.status_code}: {r.text}")
        st.stop()

    data = r.json()

    if "content" not in data:
        st.error("Invalid GitHub response (no content)")
        st.stop()

    decoded = base64.b64decode(data["content"]).decode("utf-8")
    
    # DEBUG (optional)
    # st.text(decoded[:500])
    
    if not decoded.strip():
        st.error(f"{github_file_path} is empty")
        st.stop()
    
    try:
        df = pd.read_csv(StringIO(decoded), dtype=str).fillna("")
    
    except pd.errors.EmptyDataError:
        st.error(f"{github_file_path} contains no CSV data")
        st.stop()
    
    except pd.errors.ParserError as e:
        st.error(f"CSV parsing error in {github_file_path}: {e}")
        st.stop()
    
    except Exception as e:
        st.error(f"Unexpected CSV error: {e}")
        st.stop()

    return df

# ----------------------------
# GET SHA
# ----------------------------
def get_file_sha(reviewer):
    github_file_path = f"data/reviewer_{reviewer}.csv"

    api_url = (
        f"https://api.github.com/repos/{GITHUB_REPO}/contents/{github_file_path}"
        f"?ref={GITHUB_BRANCH}"
    )

    r = requests.get(api_url, headers=HEADERS)

    if r.status_code == 200:
        return r.json().get("sha")

    return None

# ----------------------------
# SAVE TO GITHUB
# ----------------------------
def save_to_github(df, reviewer, sha):
    github_file_path = f"data/reviewer_{reviewer}.csv"

    api_url = (
        f"https://api.github.com/repos/{GITHUB_REPO}/contents/{github_file_path}"
    )

    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index=False)

    encoded = base64.b64encode(csv_buffer.getvalue().encode()).decode()

    payload = {
        "message": f"Update dataset (reviewer {reviewer})",
        "content": encoded,
        "branch": GITHUB_BRANCH,
        "sha": sha
    }

    r = requests.put(api_url, json=payload, headers=HEADERS)
    return r.status_code, r.text

# ----------------------------
# TITLE
# ----------------------------
st.title("CSV Review Tool (Multi-Reviewer)")
st.caption(f"Reviewer: {reviewer}")

if not GITHUB_TOKEN:
    st.warning("Missing GITHUB_TOKEN — saving disabled")

# ----------------------------
# LOAD DATA (IMPORTANT FIX)
# ----------------------------
df = load_data(reviewer)

if df.empty:
    st.error("Dataset is empty")
    st.stop()


# ----------------------------
# TABLE EDITOR
# ----------------------------
st.subheader("Edit Dataset")

edited_df = st.data_editor(
    df,
    use_container_width=True,
    hide_index=True,
    num_rows="dynamic",
    column_config={
        "status": st.column_config.SelectboxColumn(
            "Status",
            options=["unreviewed", "approved", "flagged"],
            width="small"
        ),
        "review_comment": st.column_config.TextColumn("Review Comment"),
        "corrected_value": st.column_config.TextColumn("Corrected Value")
    }
)

st.divider()

# ----------------------------
# SAVE
# ----------------------------
if st.button("Save to GitHub"):
    with st.spinner("Saving..."):

        sha = get_file_sha(reviewer)

        if not sha:
            st.error("Could not fetch file SHA")
        else:
            status, resp = save_to_github(edited_df, reviewer, sha)

            if status in [200, 201]:
                st.success("Saved successfully!")
                st.cache_data.clear()

            elif status == 409:
                st.error("Conflict: file updated elsewhere. Reload and retry.")

            elif status == 401:
                st.error("Unauthorized: check GitHub token.")

            elif status == 422:
                st.error("Invalid request (likely SHA mismatch).")

            else:
                st.error(f"Save failed ({status}): {resp}")

# ----------------------------
# SUMMARY
# ----------------------------
st.subheader("Summary")

col1, col2, col3 = st.columns(3)

col1.metric("Total Rows", len(edited_df))
col2.metric("Approved", (edited_df["status"] == "approved").sum())
col3.metric("Flagged", (edited_df["status"] == "flagged").sum())
