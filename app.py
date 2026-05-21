# ----------------------------
# LOAD DATA
# ----------------------------
df = load_data(reviewer)

if df.empty:
    st.info("No data found — showing empty table.")
    df = pd.DataFrame()

# ----------------------------
# COLUMN FILTERS
# ----------------------------
st.sidebar.header("Filters")

filtered_df = df.copy()

# Select columns to filter
filter_columns = st.sidebar.multiselect(
    "Filter columns",
    options=df.columns.tolist()
)

# Dynamic filters
for col in filter_columns:

    unique_values = sorted(
        [str(v) for v in filtered_df[col].dropna().unique()]
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
# EDITOR
# ----------------------------
st.subheader("Edit Dataset")

edited_df = st.data_editor(
    filtered_df,
    use_container_width=True,
    hide_index=True,
    num_rows="dynamic"
)

st.divider()
