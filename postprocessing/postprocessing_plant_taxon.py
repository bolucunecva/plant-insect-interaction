import os
import argparse
import pandas as pd
import rpy2.robjects as robjects

from rpy2.robjects.packages import importr
from rpy2.robjects import pandas2ri
from rpy2.robjects.conversion import localconverter

# ── Set R path ────────────────────────────────────────────────────────────────
os.environ['R_HOME'] = r"C:\Users\bol107\AppData\Local\Programs\R\R-4.5.2"


# ── Install/load TNRS package ────────────────────────────────────────────────
utils = importr('utils')

try:
    tnrs = importr('TNRS')
except Exception:
    utils.install_packages('TNRS')
    tnrs = importr('TNRS')


def main(args):
    # ── Load dataset ──────────────────────────────────────────────────────────────
    dataset = pd.read_csv(args.input_csv)

    # ── Extract taxon names ───────────────────────────────────────────────────────
    taxon_list = (
        dataset['plant_taxon']
        .fillna("none")
        .astype(str)
        .str.strip()
        .tolist()
    )

    # Remove duplicates for faster TNRS lookup
    unique_taxa = list(pd.Series(taxon_list).unique())

    print(f"Resolving {len(unique_taxa)} unique taxa...")

    # ── Resolve names in batches ─────────────────────────────────────────────────
    BATCH_SIZE = 100
    all_results = []

    for i in range(0, len(unique_taxa), BATCH_SIZE):

        batch = unique_taxa[i:i + BATCH_SIZE]

        print(
            f"Processing batch {i // BATCH_SIZE + 1} "
            f"({len(batch)} names)"
        )

        try:
            names_to_resolve = robjects.StrVector(batch)

            resolved = tnrs.TNRS(
                names_to_resolve,
                sources="wfo",
                mode="resolve"
            )

            # Correct modern conversion method
            with localconverter(
                robjects.default_converter + pandas2ri.converter
            ):
                df_resolved = robjects.conversion.rpy2py(resolved)

            all_results.append(df_resolved)

        except Exception as e:
            print(f"Batch failed: {e}")

    # ── Combine all TNRS results ─────────────────────────────────────────────────
    if len(all_results) == 0:
        raise ValueError("No TNRS results returned.")

    final_df = pd.concat(all_results, ignore_index=True)

    print("\nTNRS columns:")
    print(final_df.columns.tolist())

    # ── Merge back to original dataset ───────────────────────────────────────────
    possible_name_cols = [
        "Name_submitted",
        "submitted_name",
        "user_supplied_name"
    ]

    merge_col = None

    for col in possible_name_cols:
        if col in final_df.columns:
            merge_col = col
            break

    if merge_col is not None:
        merged = dataset.merge(
            final_df,
            left_on='plant_taxon',
            right_on=merge_col,
            how='left'
        )

    else:
        print("WARNING: No matching submitted-name column found.")
        merged = dataset.copy()

    # ── Save output ───────────────────────────────────────────────────────────────
    merged.to_csv(args.output_file, index=False)

    print(f"\nDone. Results saved to:\n{args.output_file}")

    print("\nPreview:")
    print(merged.head())

# --------------------------------------------------
# Run
# --------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Postprocessing after table generation")
    parser.add_argument("--input_csv", default="gpt-oss_20b_zero_prediction_haba_elsevier_all_inaturalist.csv", type=str, help="Input CSV file with generated table")
    parser.add_argument("--output_file", default="anomaly_detection_results.json", type=str, help="Output file for the results")
    args = parser.parse_args()
    main(args)
