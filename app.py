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

query_params = st.query_params

reviewer = query_params.get("reviewer", "A")
if isinstance(reviewer, list):
    reviewer = reviewer[0]

reviewer = str(reviewer).strip().upper()  # FIX: avoid case mismatch

GITHUB_FILE_PATH = f"data/reviewer_{reviewer}.csv"

API_URL = (
    f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
    f"?ref={GITHUB_BRANCH}"   # 🔥 FIX: branch must be included
)

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}"
} if GITHUB_TOKEN else {}

# ----------------------------
# LOAD DATA
# ----------------------------
@st.cache_data
def load_data():
    r = requests.get(API_URL, headers=HEADERS)

    if r.status_code == 404:
        st.error(f"File not found in GitHub: {GITHUB_FILE_PATH}")
        st.stop()

    if r.status_code != 200:
        st.error(f"GitHub API error {r.status_code}: {r.text}")
        st.stop()

    data = r.json()

    if "content" not in data:
        st.error("Invalid GitHub response: no file content found")
        st.stop()

    decoded = base64.b64decode(data["content"]).decode("utf-8")

    df = pd.read_csv(StringIO(decoded), dtype=str).fillna("")

    return df

# ----------------------------
# GET SHA
# ----------------------------
def get_file_sha():
    r = requests.get(API_URL, headers=HEADERS)
    if r.status_code == 200:
        return r.json().get("sha")
    return None

# ----------------------------
# SAVE TO GITHUB
# ----------------------------
def save_to_github(df, sha):
    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index=False)

    encoded = base64.b64encode(csv_buffer.getvalue().encode()).decode()

    payload = {
        "message": f"Update reviewed dataset (reviewer {reviewer})",
        "content": encoded,
        "branch": GITHUB_BRANCH,
        "sha": sha
    }

    r = requests.put(API_URL, json=payload, headers=HEADERS)
    return r.status_code, r.text

# ----------------------------
# UI
# ----------------------------
st.title("CSV Review Tool (Table Mode)")
st.caption(f"Reviewer: {reviewer}")

if not GITHUB_TOKEN:
    st.warning("Missing GITHUB_TOKEN — saving disabled")

# LOAD DATA
df = load_data()

if df.empty:
    st.error("Dataset is empty")
    st.stop()

# ----------------------------
# DATA CLEANING
# ----------------------------
for col in ["status", "review_comment", "corrected_value"]:
    if col not in df.columns:
        df[col] = ""

df["status"] = df["status"].fillna("unreviewed")
df["review_comment"] = df["review_comment"].fillna("")
df["corrected_value"] = df["corrected_value"].fillna("")

# ----------------------------
# EDITOR
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
    sha = get_file_sha()

    if not sha:
        st.error("Could not fetch file SHA (file may not exist)")
    else:
        status, resp = save_to_github(edited_df, sha)

        if status in [200, 201]:
            st.success("Saved to GitHub successfully!")
            st.cache_data.clear()
        else:
            st.error(f"GitHub save failed: {resp}")

# ----------------------------
# SUMMARY
# ----------------------------
st.subheader("Summary")

col1, col2, col3 = st.columns(3)

col1.metric("Total Rows", len(edited_df))
col2.metric("Approved", (edited_df["status"] == "approved").sum())
col3.metric("Flagged", (edited_df["status"] == "flagged").sum())
