"""
Streamlit CSV Review App with GitHub Integration
------------------------------------------------
Features:
- Load CSV from GitHub (raw URL)
- Row-by-row review interface
- Approve / Flag / Edit workflow
- Save updates back to GitHub via API
- Simple reviewer session handling

SETUP REQUIREMENTS:
1. pip install streamlit pandas requests
2. Create a GitHub Personal Access Token (PAT)
   - Needs repo write access
3. Set environment variables:
   - GITHUB_TOKEN
   - GITHUB_REPO (e.g. "username/repo")
   - GITHUB_FILE_PATH (e.g. "data/shard_001.csv")
   - GITHUB_BRANCH (optional, default "main")

RUN:
streamlit run app.py
"""

import streamlit as st
import pandas as pd
import requests
import os
import base64
from io import StringIO

# ----------------------------
# CONFIG
# ----------------------------
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")  # "owner/repo"
GITHUB_FILE_PATH = os.getenv("GITHUB_FILE_PATH")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")

# Reviewer from URL
query_params = st.query_params
reviewer = query_params.get("reviewer", "A")

RAW_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{GITHUB_FILE_PATH}"
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
} if GITHUB_TOKEN else {}

# ----------------------------
# LOAD DATA
# ----------------------------
@st.cache_data
def load_data():
    df = pd.read_csv(RAW_URL)
    if "status" not in df.columns:
        df["status"] = "unreviewed"
    if "review_comment" not in df.columns:
        df["review_comment"] = ""
    if "corrected_value" not in df.columns:
        df["corrected_value"] = ""
    return df


def save_to_github(df, sha):
    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index=False)
    encoded_content = base64.b64encode(csv_buffer.getvalue().encode()).decode()

    payload = {
        "message": "Update reviewed dataset",
        "content": encoded_content,
        "branch": GITHUB_BRANCH,
        "sha": sha
    }

    response = requests.put(API_URL, json=payload, headers=HEADERS)
    return response.status_code, response.text


def get_file_sha():
    r = requests.get(API_URL, headers=HEADERS)
    if r.status_code == 200:
        return r.json()["sha"]
    return None

# ----------------------------
# UI
# ----------------------------

st.title("CSV Review Tool (GitHub-backed)")

if not GITHUB_TOKEN:
    st.warning("No GITHUB_TOKEN set — saving will be disabled")

# Load dataset
try:
    df = load_data()
except Exception as e:
    st.error(f"Failed to load CSV: {e}")
    st.stop()

# Session state
if "index" not in st.session_state:
    st.session_state.index = 0

idx = st.session_state.index

# Bounds
if idx >= len(df):
    st.success("All records reviewed!")
    st.stop()

row = df.iloc[idx]

st.subheader(f"Record {idx+1} / {len(df)}")

# Display record
st.write(row.to_dict())

# Editable fields
new_value = st.text_input("Corrected Value", value=row.get("corrected_value", ""))
comment = st.text_area("Review Comment", value=row.get("review_comment", ""))

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("Approve"):
        df.at[idx, "status"] = "approved"
        df.at[idx, "review_comment"] = comment
        df.at[idx, "corrected_value"] = new_value
        st.session_state.index += 1
        st.rerun()

with col2:
    if st.button("Flag"):
        df.at[idx, "status"] = "flagged"
        df.at[idx, "review_comment"] = comment
        df.at[idx, "corrected_value"] = new_value
        st.session_state.index += 1
        st.rerun()

with col3:
    if st.button("Skip"):
        st.session_state.index += 1
        st.rerun()

# Save button
st.divider()

if st.button("Save to GitHub"):
    sha = get_file_sha()
    if sha:
        status, resp = save_to_github(df, sha)
        if status == 200:
            st.success("Saved to GitHub successfully!")
        else:
            st.error(f"GitHub save failed: {resp}")
    else:
        st.error("Could not fetch file SHA from GitHub")

# Progress
st.progress(st.session_state.index / len(df))
