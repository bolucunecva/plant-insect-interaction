import base64
import json
import os
import re
from datetime import datetime, timezone
from io import StringIO

import pandas as pd
import requests
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, DataReturnMode, JsCode

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
GITHUB_FILE_PATH = os.getenv("GITHUB_FILE_PATH", "data/insect_plant_interactions_filtered.csv")
NOTES_FILE_PATH = os.getenv("NOTES_FILE_PATH", "data/review_notes.csv")
VOCAB_FILE_PATH = os.getenv("VOCAB_FILE_PATH", "data/controlled_vocabulary.json")

REVIEWER_COL = "reviewer"          # shown in the grid; filter it to see one reviewer's rows
REVIEWER_EDITABLE = False          # set True if reviewers may reassign rows
ROW_ID = "__row_id"                # hidden: position of the row in the full CSV

# Controlled vocabulary: columns that may only take values from a fixed list.
# Fill the lists in here, OR put a JSON file at VOCAB_FILE_PATH in the repo, e.g.
#   {"plant_part": ["leaf", "stem", "root"], "direct_interactions": [...], ...}
# The JSON file wins over the lists below. An empty list means "use the distinct
# values already in the column" (a quick start; replace with the real list).
CONTROLLED_VOCAB = {
    "plant_part": [],
    "direct_interactions": [],
    "plant_insect_interactions": [],
}

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
API_BASE = f"https://api.github.com/repos/{GITHUB_REPO}"
RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}"


# ----------------------------
# GITHUB I/O (generic, any file in the repo)
# ----------------------------
def _headers(token):
    return {"Authorization": f"token {token}"}


def gh_read_text(path, token=None):
    """Return (text, sha) for a repo file, or (None, None) if it does not exist."""
    if not token:
        r = requests.get(f"{RAW_BASE}/{path}", timeout=60)
        if r.status_code == 404:
            return None, None
        r.raise_for_status()
        r.encoding = "utf-8"
        return r.text, None

    r = requests.get(f"{API_BASE}/contents/{path}", headers=_headers(token),
                     params={"ref": GITHUB_BRANCH}, timeout=60)
    if r.status_code == 404:
        return None, None
    r.raise_for_status()
    sha = r.json()["sha"]
    # Read the blob for that exact sha so content and sha always match (no stale CDN copy)
    b = requests.get(f"{API_BASE}/git/blobs/{sha}", headers=_headers(token), timeout=120)
    b.raise_for_status()
    return base64.b64decode(b.json()["content"]).decode("utf-8"), sha


def gh_write_text(path, text, sha, message, token):
    """Create/update a repo file. Returns the requests response."""
    payload = {
        "message": message,
        "content": base64.b64encode(text.encode("utf-8")).decode(),
        "branch": GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha
    return requests.put(f"{API_BASE}/contents/{path}", json=payload,
                        headers=_headers(token), timeout=120)


def _line_end(text) -> str:
    return "\r\n" if text and "\r\n" in text[:10000] else "\n"


def _read_csv_text(text) -> pd.DataFrame:
    if not text or not text.strip():
        return pd.DataFrame()
    return pd.read_csv(StringIO(text), dtype=str, keep_default_na=False, low_memory=False)


def fetch_latest(token=None):
    text, sha = gh_read_text(GITHUB_FILE_PATH, token)
    if text is None:
        raise FileNotFoundError(GITHUB_FILE_PATH)
    df = _read_csv_text(text)
    df.attrs["line_end"] = _line_end(text)
    return df, sha


def save_changes(changes, token, expected_rows, max_retries=3):
    """
    Apply ONLY the changed cells to the latest version of the file and commit it.
    changes: list of (row_id, column, new_value).
    Returns (status_code, message, updated_full_df_or_None).
    """
    for _ in range(max_retries):
        latest, sha = fetch_latest(token)

        if len(latest) != expected_rows:
            return 409, "The file's row count changed since it was loaded. Click 'Reload from GitHub'.", None

        missing = {c for _, c, _ in changes} - set(latest.columns)
        if missing:
            return 409, f"Columns no longer in the file: {sorted(missing)}. Click 'Reload from GitHub'.", None

        for rid, col, val in changes:
            latest.iat[rid, latest.columns.get_loc(col)] = val

        buffer = StringIO()
        latest.to_csv(buffer, index=False, lineterminator=latest.attrs.get("line_end", "\n"))
        r = gh_write_text(GITHUB_FILE_PATH, buffer.getvalue(), sha,
                          f"Update dataset ({len(changes)} cells)", token)
        if r.status_code in (200, 201):
            return r.status_code, "ok", latest
        if r.status_code != 409:          # 409 = someone committed in between -> retry
            return r.status_code, r.text, None

    return 409, "File kept changing during save. Please retry.", None


NOTE_COLS = ["timestamp_utc", "author", "note"]


def load_notes(token=None):
    text, _ = gh_read_text(NOTES_FILE_PATH, token)
    df = _read_csv_text(text)
    return df if not df.empty else pd.DataFrame(columns=NOTE_COLS)


def add_note(author, note, token, max_retries=3):
    """Append one note to the shared notes CSV (created on first use)."""
    row = {"timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
           "author": author.strip(), "note": note.strip()}
    for _ in range(max_retries):
        text, sha = gh_read_text(NOTES_FILE_PATH, token)
        df = _read_csv_text(text)
        if df.empty:
            df = pd.DataFrame(columns=NOTE_COLS)
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        buf = StringIO()
        df.to_csv(buf, index=False, lineterminator=_line_end(text))
        r = gh_write_text(NOTES_FILE_PATH, buf.getvalue(), sha,
                          f"Add review note ({row['author'] or 'anonymous'})", token)
        if r.status_code in (200, 201):
            return True, df
        if r.status_code != 409:
            return False, r.text
    return False, "Notes file kept changing. Please retry."


# ----------------------------
# CONTROLLED VOCABULARY
# ----------------------------
def _norm_name(name: str) -> str:
    return re.sub(r"[\s_\-]+", "_", str(name).strip().lower())


def build_vocab(df: pd.DataFrame, token=None) -> dict:
    """Map actual CSV column name -> sorted list of allowed values ('' always allowed)."""
    configured = dict(CONTROLLED_VOCAB)
    try:
        text, _ = gh_read_text(VOCAB_FILE_PATH, token)
        if text:
            configured.update(json.loads(text))
    except Exception as e:
        st.warning(f"Could not read {VOCAB_FILE_PATH}: {e}")

    by_norm = {_norm_name(c): c for c in df.columns}
    vocab = {}
    for name, values in configured.items():
        col = by_norm.get(_norm_name(name))
        if col is None:
            continue
        values = [str(v).strip() for v in (values or []) if str(v).strip()]
        if not values:  # fall back to what is already in the data
            values = sorted({v.strip() for v in df[col] if str(v).strip()})
        vocab[col] = [""] + sorted(dict.fromkeys(values), key=str.lower)
    return vocab


# ----------------------------
# SESSION STATE
# ----------------------------
ss = st.session_state
ss.setdefault("grid_version", 0)      # bump to force a clean grid reload
ss.setdefault("flash", None)


def load_into_session():
    df, sha = fetch_latest(GITHUB_TOKEN)
    ss["full_df"] = df.reset_index(drop=True)
    ss["sha"] = sha
    ss["vocab"] = build_vocab(ss["full_df"], GITHUB_TOKEN)
    ss["notes"] = load_notes(GITHUB_TOKEN)
    ss["grid_version"] += 1


if "full_df" not in ss:
    try:
        with st.spinner("Loading dataset..."):
            load_into_session()
    except Exception as e:
        st.error(f"Failed to load CSV: {e}")
        st.stop()

full_df = ss["full_df"]
vocab = ss["vocab"]

if full_df.empty:
    st.error("CSV is empty.")
    st.stop()

# ----------------------------
# TITLE
# ----------------------------
st.title("Review Tool")

top_l, top_r = st.columns([4, 1])
with top_l:
    st.caption(
        f"{len(full_df)} records. Filter the '{REVIEWER_COL}' column (box under its header) "
        "to see one reviewer's rows. Double-click a cell to edit; press Enter to finish."
    )
with top_r:
    if st.button("Reload from GitHub", use_container_width=True):
        try:
            load_into_session()
            st.rerun()
        except Exception as e:
            st.error(f"Reload failed: {e}")

if ss["flash"]:
    st.success(ss["flash"])
    ss["flash"] = None

# ----------------------------
# GLOBAL REVIEW NOTES
# ----------------------------
notes_df = ss["notes"]
with st.expander(f"Review notes ({len(notes_df)})", expanded=False):
    if len(notes_df):
        st.dataframe(notes_df.iloc[::-1], hide_index=True, use_container_width=True)
    else:
        st.caption("No notes yet.")
    with st.form("add_note", clear_on_submit=True):
        n1, n2 = st.columns([1, 4])
        author = n1.text_input("Your name / reviewer ID")
        note = n2.text_area("Note", height=80,
                            placeholder="General comments about the dataset or the review…")
        submitted = st.form_submit_button("Add note", disabled=not GITHUB_TOKEN)
    if submitted:
        if not note.strip():
            st.warning("Write a note first.")
        else:
            with st.spinner("Saving note..."):
                try:
                    ok, result = add_note(author, note, GITHUB_TOKEN)
                except Exception as e:
                    ok, result = False, str(e)
            if ok:
                ss["notes"] = result
                ss["flash"] = "Note saved."
                st.rerun()
            else:
                st.error(f"Could not save note: {result}")

st.subheader("Edit Dataset")

# ----------------------------
# GRID
# ----------------------------
df = full_df.copy()
df.insert(0, ROW_ID, range(len(df)))

# Put the reviewer column first so it is easy to filter
data_cols = [c for c in df.columns if c != ROW_ID]
if REVIEWER_COL in data_cols:
    data_cols = [REVIEWER_COL] + [c for c in data_cols if c != REVIEWER_COL]

edit_cols = [c for c in data_cols if REVIEWER_EDITABLE or c != REVIEWER_COL]

grid_df = df[[ROW_ID] + data_cols].copy()

# Edited cells are remembered in the browser (EDITS) and only those are sent back
# to Python. Sending the whole 30k-row table back after every edit was too slow,
# which is why changes were never counted and Save had nothing to save.
EDITS = f"window.__reviewEdits_{ss['grid_version']}"

gb = GridOptionsBuilder.from_dataframe(grid_df)

# Dropdown in the filter row of the reviewer column: All / each reviewer / unassigned.
# The choice is remembered in the browser, so it survives saves and reloads.
reviewer_options = (
    sorted({v.strip() for v in full_df[REVIEWER_COL] if str(v).strip()})
    if REVIEWER_COL in full_df.columns else []
)
reviewer_dropdown_filter = JsCode(f"""
class ReviewerDropdownFilter {{
    init(params) {{
        this.params = params;
        var options = {json.dumps(reviewer_options)};
        this.eGui = document.createElement('div');
        this.eGui.style.cssText = 'display:flex;align-items:center;width:100%;height:100%;';
        this.select = document.createElement('select');
        this.select.style.cssText = 'width:100%;height:26px;font-size:12px;';
        var items = [['', 'All reviewers']]
            .concat(options.map(function(o) {{ return [o, o]; }}))
            .concat([['__blank__', '(unassigned)']]);
        var self = this;
        items.forEach(function(it) {{
            var opt = document.createElement('option');
            opt.value = it[0]; opt.textContent = it[1];
            self.select.appendChild(opt);
        }});
        this.eGui.appendChild(this.select);
        this.select.addEventListener('change', function() {{ self.apply(self.select.value, true); }});

        var saved = '';
        try {{ saved = window.localStorage.getItem('reviewTool.reviewer') || ''; }} catch (e) {{}}
        if (saved && items.some(function(it) {{ return it[0] === saved; }})) {{
            this.select.value = saved;
            setTimeout(function() {{ self.apply(saved, false); }}, 0);
        }}
    }}
    apply(value, remember) {{
        if (remember) {{
            try {{ window.localStorage.setItem('reviewTool.reviewer', value); }} catch (e) {{}}
        }}
        var model = null;
        if (value === '__blank__') {{ model = {{filterType: 'text', type: 'blank'}}; }}
        else if (value) {{ model = {{filterType: 'text', type: 'equals', filter: value}}; }}
        var api = this.params.api;
        this.params.parentFilterInstance(function(inst) {{
            var r = inst.setModel(model);
            if (r && typeof r.then === 'function') {{ r.then(function() {{ api.onFilterChanged(); }}); }}
            else {{ api.onFilterChanged(); }}
        }});
    }}
    onParentModelChanged(model) {{
        if (!model) {{ this.select.value = ''; }}
        else if (model.type === 'blank') {{ this.select.value = '__blank__'; }}
        else if (model.filter != null) {{ this.select.value = model.filter; }}
    }}
    getGui() {{ return this.eGui; }}
}}
""")

for col in data_cols:
    editable = col in edit_cols
    opts = dict(
        editable=editable,
        filter="agTextColumnFilter",
        floatingFilter=True,
        resizable=True,
        sortable=True,
    )
    if editable:
        allowed = json.dumps(vocab.get(col)) if col in vocab else "null"
        # Yellow = changed but not saved; red = value outside the controlled vocabulary
        opts["cellStyle"] = JsCode(f"""
            function(params) {{
                var allowed = {allowed};
                var v = String(params.value ?? '');
                if (allowed && allowed.indexOf(v) === -1) {{
                    return {{backgroundColor: '#f8d7da', color: '#842029'}};
                }}
                var store = {EDITS} || {{}};
                var e = store[params.data['{ROW_ID}'] + '|{col}'];
                if (e && v !== e.orig) {{
                    return {{backgroundColor: '#fff3cd', color: '#856404', fontWeight: 'bold'}};
                }}
                return null;
            }}
        """)
    if col in vocab:
        opts.update(
            cellEditor="agSelectCellEditor",
            cellEditorParams={"values": vocab[col]},
            singleClickEdit=True,
            headerTooltip="Controlled vocabulary: pick a value from the list",
        )
    if col == REVIEWER_COL:
        opts.update(
            pinned="left",
            width=150,
            floatingFilterComponent=reviewer_dropdown_filter,
            suppressFloatingFilterButton=True,
        )
    gb.configure_column(col, **opts)

gb.configure_column(ROW_ID, hide=True)

# Record every edit in the browser; keep the original value of the first edit
record_edit = JsCode(f"""
    function(params) {{
        {EDITS} = {EDITS} || {{}};
        var col = params.colDef.field;
        var key = params.data['{ROW_ID}'] + '|' + col;
        var prev = {EDITS}[key];
        {EDITS}[key] = {{
            row_id: params.data['{ROW_ID}'],
            col: col,
            value: params.newValue == null ? '' : String(params.newValue),
            orig: prev ? prev.orig : (params.oldValue == null ? '' : String(params.oldValue))
        }};
    }}
""")

# What the grid sends back to Python: only the edited cells
return_edits = JsCode(f"""
    function(p) {{
        var e = p.eventData;
        if (e && e.colDef && e.data) {{        // make sure the latest edit is included
            {EDITS} = {EDITS} || {{}};
            var key = e.data['{ROW_ID}'] + '|' + e.colDef.field;
            var prev = {EDITS}[key];
            {EDITS}[key] = {{
                row_id: e.data['{ROW_ID}'],
                col: e.colDef.field,
                value: e.newValue == null ? '' : String(e.newValue),
                orig: prev ? prev.orig : (e.oldValue == null ? '' : String(e.oldValue))
            }};
        }}
        var out = [];
        var store = {EDITS} || {{}};
        for (var k in store) {{ out.push({{row_id: store[k].row_id, col: store[k].col, value: store[k].value}}); }}
        return {{edits: out}};
    }}
""")

# Finish any open cell edit as soon as the mouse leaves the grid. Without this,
# typing in a cell and then clicking "Save" sends the edit and the click at the
# same moment, and Streamlit drops the click (looks like "nothing happened").
finish_edit_on_leave = JsCode("""
    function(params) {
        if (window.__stopEditHooked) { return; }
        window.__stopEditHooked = true;
        var stop = function() { params.api.stopEditing(); };
        document.documentElement.addEventListener('mouseleave', stop);
        window.addEventListener('blur', stop);
    }
""")

gb.configure_grid_options(
    suppressMovableColumns=False,
    domLayout="normal",
    stopEditingWhenCellsLoseFocus=True,   # commit a cell edit as soon as you click elsewhere
    onCellEditingStarted=finish_edit_on_leave,
    onCellValueChanged=record_edit,
)
gb.configure_selection(selection_mode="disabled")

grid_response = AgGrid(
    grid_df,
    gridOptions=gb.build(),
    update_on=["cellValueChanged"],             # only re-run on edits (not on every filter keystroke)
    data_return_mode=DataReturnMode.CUSTOM,     # return only the edited cells
    custom_jscode_for_grid_return=return_edits,
    allow_unsafe_jscode=True,
    fit_columns_on_grid_load=True,
    use_container_width=True,
    height=500,
    theme="streamlit",
    # new key after each save/reload -> grid remounts with the saved data
    key=f"grid_{ss['grid_version']}",
)

# ----------------------------
# DETECT CHANGED CELLS (vs last saved values)
# ----------------------------
raw = getattr(grid_response, "raw_data", None)
if raw is None and isinstance(grid_response, dict):
    raw = grid_response
edits = (raw or {}).get("edits", []) if isinstance(raw, dict) else []
# Remember the latest edits so they survive reruns caused by other widgets
if raw is not None:
    ss["edits"] = {"version": ss["grid_version"], "items": edits}
elif ss.get("edits", {}).get("version") == ss["grid_version"]:
    edits = ss["edits"]["items"]

changes = []
for e in edits:
    try:
        rid, col = int(e["row_id"]), str(e["col"])
    except (KeyError, TypeError, ValueError):
        continue
    if col not in edit_cols or not 0 <= rid < len(full_df):
        continue
    val = "" if e.get("value") is None else str(e["value"])
    if val != full_df.iat[rid, full_df.columns.get_loc(col)]:   # reverted edits drop out
        changes.append((rid, col, val))

# New values must come from the controlled vocabulary
bad = [(rid, c, v) for rid, c, v in changes if c in vocab and v not in vocab[c]]

st.divider()

# ----------------------------
# SAVE
# ----------------------------
if not GITHUB_TOKEN:
    st.warning("Missing GITHUB_TOKEN — saving disabled")

s1, s2 = st.columns([1, 5])
save_clicked = s1.button(
    "Save",                      # keep the label fixed: a changing label resets the button
    key="save_btn",
    type="primary",
    disabled=not GITHUB_TOKEN,
    use_container_width=True,
)
if changes:
    s2.info(f"{len(changes)} unsaved cell change(s) — highlighted in yellow.")

if save_clicked:
    if not changes:
        st.info("Nothing to save. (If you were still typing in a cell, press Enter first.)")
    elif bad:
        st.error("Some values are not in the controlled vocabulary: "
                 + ", ".join(f"row {rid + 1} / {c}: '{v}'" for rid, c, v in bad[:10]))
    else:
        with st.spinner("Saving..."):
            try:
                status, msg, new_full = save_changes(changes, GITHUB_TOKEN, len(full_df))
            except Exception as e:
                status, msg, new_full = -1, str(e), None

        if status in (200, 201):
            # Use the exact file we just committed as the new baseline (no re-download)
            ss["full_df"] = new_full.reset_index(drop=True)
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
c1.metric("Total rows in file", len(full_df))
c2.metric("Unsaved cell changes", len(changes))
out_of_vocab = sum(int((~full_df[c].isin(v)).sum()) for c, v in vocab.items())
c3.metric("Saved values outside vocabulary", out_of_vocab)
