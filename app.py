import base64
import os
from io import StringIO

import pandas as pd
import requests
import streamlit as st
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
        padding-bottom: 6px;
        box-sizing: border-box;
    }

    div[data-testid="stCustomComponentV1"] > iframe {
        width: 100% !important;
        height: 100% !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------
# CONFIG
# ----------------------------
GITHUB_REPO = "bolucunecva/plant-insect-interaction"
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")

# One shared CSV for all reviewers
GITHUB_FILE_PATH = os.getenv("GITHUB_FILE_PATH", "data/insect_plant_interactions_filtered.csv")

REVIEWER_COL = "reviewer"          # column holding e.g. "Reviewer A" (hidden in the grid)
VALID_REVIEWERS = ["A", "B", "C", "D"]
ROW_ID = "__row_id"                # hidden: position of the row in the full CSV
ORIG_PREFIX = "__orig_"            # hidden: saved values, for change highlighting

RAW_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{GITHUB_FILE_PATH}"
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
BLOB_URL = f"https://api.github.com/repos/{GITHUB_REPO}/git/blobs"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")


def normalize_reviewer(value) -> str:
    """'Reviewer A', 'reviewer a', 'A' -> 'A'. Empty/NaN -> ''."""
    s = str(value or "").strip().upper()
    if s.startswith("REVIEWER"):
        s = s[len("REVIEWER"):].strip()
    return s


# ----------------------------
# GITHUB I/O
# ----------------------------
def _read_csv_text(text: str) -> pd.DataFrame:
    if not text.strip():
        return pd.DataFrame()
    return pd.read_csv(StringIO(text), dtype=str, keep_default_na=False, low_memory=False)


def fetch_latest(token=None):
    """
    Return (dataframe, sha) for the current file on the branch.
    With a token, the content is read from the git blob for that exact sha,
    so the content and sha always match (no stale CDN copy).
    """
    if not token:
        r = requests.get(RAW_URL, timeout=60)
        r.raise_for_status()
        r.encoding = "utf-8"
        return _read_csv_text(r.text), None

    headers = {"Authorization": f"token {token}"}
    r = requests.get(API_URL, headers=headers, params={"ref": GITHUB_BRANCH}, timeout=60)
    r.raise_for_status()
    sha = r.json()["sha"]

    b = requests.get(f"{BLOB_URL}/{sha}", headers=headers, timeout=120)
    b.raise_for_status()
    text = base64.b64decode(b.json()["content"]).decode("utf-8")
    return _read_csv_text(text), sha


def save_changes(changes, reviewer, token, expected_rows, max_retries=3):
    """
    Apply ONLY the changed cells to the latest version of the file and commit it.
    changes: list of (row_id, column, new_value).
    Returns (status_code, message, updated_full_df_or_None, new_sha_or_None).
    """
    headers = {"Authorization": f"token {token}"}

    for _ in range(max_retries):
        latest, sha = fetch_latest(token)

        if len(latest) != expected_rows:
            return 409, "The file's row count changed since it was loaded. Click 'Reload from GitHub'.", None, None

        row_ids = sorted({rid for rid, _, _ in changes})
        owners = latest.iloc[row_ids][REVIEWER_COL].map(normalize_reviewer)
        if (owners != reviewer).any():
            return 409, "Some rows were reassigned since loading. Click 'Reload from GitHub'.", None, None

        for rid, col, val in changes:
            latest.iat[rid, latest.columns.get_loc(col)] = val

        buffer = StringIO()
        latest.to_csv(buffer, index=False)
        payload = {
            "message": f"Update dataset (reviewer {reviewer}, {len(changes)} cells)",
            "content": base64.b64encode(buffer.getvalue().encode("utf-8")).decode(),
            "branch": GITHUB_BRANCH,
            "sha": sha,
        }
        r = requests.put(API_URL, json=payload, headers=headers, timeout=120)
        if r.status_code in (200, 201):
            new_sha = r.json().get("content", {}).get("sha")
            return r.status_code, "ok", latest, new_sha
        if r.status_code != 409:          # 409 = someone committed in between -> retry
            return r.status_code, r.text, None, None

    return 409, "File kept changing during save. Please retry.", None, None


# ----------------------------
# SESSION STATE
# ----------------------------
ss = st.session_state
ss.setdefault("grid_version", 0)      # bump to force a clean grid reload
ss.setdefault("flash", None)


def load_into_session():
    df, sha = fetch_latest(GITHUB_TOKEN)
    ss["full_df"] = df
    ss["sha"] = sha
    ss["grid_version"] += 1


if "full_df" not in ss:
    try:
        with st.spinner("Loading dataset..."):
            load_into_session()
    except Exception as e:
        st.error(f"Failed to load CSV: {e}")
        st.stop()

full_df = ss["full_df"]

# ----------------------------
# REVIEWER SELECTION
# ----------------------------
reviewer = st.query_params.get("reviewer", "A")
if isinstance(reviewer, list):
    reviewer = reviewer[0]
reviewer = normalize_reviewer(reviewer)
if reviewer not in VALID_REVIEWERS:
    reviewer = "A"

reviewer = st.sidebar.selectbox(
    "Select Reviewer",
    VALID_REVIEWERS,
    index=VALID_REVIEWERS.index(reviewer),
)
st.sidebar.info(f"Reviewer: {reviewer}")

if st.sidebar.button("Reload from GitHub"):
    try:
        load_into_session()
        st.rerun()
    except Exception as e:
        st.sidebar.error(f"Reload failed: {e}")

# ----------------------------
# FILTER TO THIS REVIEWER
# ----------------------------
if full_df.empty or REVIEWER_COL not in full_df.columns:
    st.error(f"CSV is empty or has no '{REVIEWER_COL}' column.")
    st.stop()

mask = full_df[REVIEWER_COL].map(normalize_reviewer) == reviewer
df = full_df[mask].copy()
df.insert(0, ROW_ID, df.index.astype(int))
df = df.reset_index(drop=True)

# Editable columns = everything except the hidden reviewer column
edit_cols = [c for c in df.columns if c not in (ROW_ID, REVIEWER_COL)]

# ----------------------------
# TITLE
# ----------------------------
st.title("Review Tool")
st.caption(f"Reviewer: {reviewer} — {len(df)} of {len(full_df)} records assigned")

if ss["flash"]:
    st.success(ss["flash"])
    ss["flash"] = None

st.subheader("Edit Dataset")

if df.empty:
    st.info(f"No records assigned to Reviewer {reviewer}.")
    st.stop()

# ----------------------------
# GRID
# ----------------------------
# Baseline = last saved values (from session copy of the file)
grid_df = df[[ROW_ID] + edit_cols].copy()
for col in edit_cols:
    grid_df[f"{ORIG_PREFIX}{col}"] = df[col]

gb = GridOptionsBuilder.from_dataframe(grid_df)

for col in edit_cols:
    cell_style_js = JsCode(f"""
        function(params) {{
            var orig = params.data['{ORIG_PREFIX}{col}'];
            if (orig !== undefined && String(params.value ?? '') !== String(orig)) {{
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

gb.configure_column(ROW_ID, hide=True)
for col in edit_cols:
    gb.configure_column(f"{ORIG_PREFIX}{col}", hide=True)

gb.configure_grid_options(
    suppressMovableColumns=False,
    enableRangeSelection=True,
    domLayout="normal",
    stopEditingWhenCellsLoseFocus=True,   # commit a cell edit as soon as you click elsewhere
)
gb.configure_selection(selection_mode="disabled")

grid_response = AgGrid(
    grid_df,
    gridOptions=gb.build(),
    update_mode=GridUpdateMode.VALUE_CHANGED,
    data_return_mode=DataReturnMode.AS_INPUT,
    allow_unsafe_jscode=True,
    fit_columns_on_grid_load=True,
    use_container_width=True,
    height=500,
    theme="streamlit",
    # new key after each save/reload -> grid remounts with the saved data
    key=f"grid_{reviewer}_{ss['grid_version']}",
)

returned = grid_response["data"]
returned = pd.DataFrame(returned) if returned is not None and len(returned) else grid_df
edited_df = returned[[ROW_ID] + edit_cols].copy()
edited_df[ROW_ID] = pd.to_numeric(edited_df[ROW_ID]).astype(int)
edited_df[edit_cols] = edited_df[edit_cols].fillna("").astype(str)

# ----------------------------
# DETECT CHANGED CELLS (vs last saved values)
# ----------------------------
saved = full_df.iloc[edited_df[ROW_ID].to_numpy()][edit_cols].reset_index(drop=True)
current = edited_df[edit_cols].reset_index(drop=True)
diff = current.ne(saved)

changes = []
for i, col in zip(*diff.to_numpy().nonzero()):
    c = edit_cols[col]
    changes.append((int(edited_df[ROW_ID].iat[i]), c, current.iat[i, col]))

st.divider()

# ----------------------------
# SAVE
# ----------------------------
if not GITHUB_TOKEN:
    st.warning("Missing GITHUB_TOKEN — saving disabled")

if st.button("Save", type="primary", disabled=not GITHUB_TOKEN):
    if not changes:
        st.info("Nothing to save.")
        st.stop()
    with st.spinner("Saving..."):
        try:
            status, msg, new_full, new_sha = save_changes(changes, reviewer, GITHUB_TOKEN, len(full_df))
        except Exception as e:
            status, msg, new_full, new_sha = -1, str(e), None, None

    if status in (200, 201):
        # Use the exact file we just committed as the new baseline (no re-download)
        ss["full_df"] = new_full
        ss["sha"] = new_sha
        ss["grid_version"] += 1
        ss["flash"] = f"Saved {len(changes)} changed cell(s) to GitHub."
        st.rerun()
    elif status == 409:
        st.error(f"Conflict: {msg}")
    else:
        st.error(f"Save failed ({status}): {msg}")

# ----------------------------
# SUMMARY
# ----------------------------
st.subheader("Summary")
c1, c2, c3 = st.columns(3)
c1.metric("Assigned rows", len(df))
c2.metric("Unsaved cell changes", len(changes))
c3.metric("Total rows in file", len(full_df))
