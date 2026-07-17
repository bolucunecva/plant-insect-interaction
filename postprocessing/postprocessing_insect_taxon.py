import pandas as pd
import requests
import re
import threading
import argparse
from rapidfuzz import process, fuzz
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from cachetools import TTLCache
from cachetools.func import cached

# --------------------------------------------------
# Config
# --------------------------------------------------
BASE_URL_INAT = "https://api.inaturalist.org/v1"
GBIF_URL = "https://api.gbif.org/v1/species/match"

MAX_WORKERS = 20

POSITIONSTACK_API_KEY = "aba96cd2e294af194af1da5bf234a039"
POSITIONSTACK_BASE = "http://api.positionstack.com/v1/forward"

# --------------------------------------------------
# Load iNaturalist taxa for fuzzy matching
# --------------------------------------------------
def load_active_taxa(csv_file):

    df = pd.read_csv(
        csv_file,
        sep="\t",
        on_bad_lines='skip',
        low_memory=True
    )

    return df[df['active']].copy()


active_df = load_active_taxa("inaturalist-open-data-20250927/taxa.csv")

name_lookup = active_df['name'].reset_index(drop=True)
names = name_lookup.tolist()

# --------------------------------------------------
# Thread-safe HTTP sessions
# --------------------------------------------------
thread_local = threading.local()

def get_session():
    if not hasattr(thread_local, "session"):
        thread_local.session = requests.Session()
    return thread_local.session

# --------------------------------------------------
# Fuzzy matching helper
# --------------------------------------------------
def find_closest_taxon(name):
    best_match = process.extractOne(
        name,
        names,
        scorer=fuzz.token_sort_ratio,
        score_cutoff=90
    )

    if best_match:
        matched_name, score, idx = best_match
        return name_lookup.iloc[idx]
    return None

# --------------------------------------------------
# Extract order + family from iNaturalist taxonomy
# --------------------------------------------------
def extract_order_family_by_ids(base_url, taxon_id):

    try:
        session = get_session()
        response = session.get(
            f"{base_url}/taxa/{taxon_id}",
            timeout=10
        )

        response.raise_for_status()
        taxon = response.json()["results"][0]

        order = None
        family = None

        ancestors = taxon.get("ancestors", [])
        for anc in ancestors:
            rank = anc.get("rank")
            name = anc.get("name")
            if rank == "order":
                order = name
            elif rank == "family":
                family = name

        current_rank = taxon.get("rank")

        if current_rank == "order":
            order = taxon.get("name")
        elif current_rank == "family":
            family = taxon.get("name")

        return order, family

    except Exception:
        return None, None

# --------------------------------------------------
# Cache
# --------------------------------------------------
taxon_cache = TTLCache(
    maxsize=5000,
    ttl=86400
)

# --------------------------------------------------
# iNaturalist query
# --------------------------------------------------
@cached(taxon_cache)
def query_inaturalist(name):

    try:
        session = get_session()
        for endpoint in ["taxa", "taxa/autocomplete"]:
            response = session.get(
                f"{BASE_URL_INAT}/{endpoint}",
                params={"q": name},
                timeout=10
            )

            response.raise_for_status()
            results = response.json().get("results")
            if results:
                taxon = max(
                    results,
                    key=lambda x: (
                        x.get("matched_term") == name,
                        x.get("rank_level", 100)
                    )
                )
                taxon_id = taxon.get("id")
                order, family = extract_order_family_by_ids(
                    BASE_URL_INAT,
                    taxon_id
                )

                return {
                    "canonical_name": taxon.get("name"),
                    "order": order,
                    "family": family,
                    "API": "iNaturalist"
                }

    except requests.RequestException:
        return None
    return None

# --------------------------------------------------
# GBIF fallback
# --------------------------------------------------
@lru_cache(maxsize=2048)
def query_gbif(name):

    try:
        session = get_session()
        response = session.get(
            GBIF_URL,
            params={"name": name},
            timeout=10
        )

        response.raise_for_status()
        data = response.json()
        if data.get("matchType") in ["EXACT", "HIGHERRANK"]:
            return {
                "canonical_name": data.get("scientificName"),
                "order": data.get("order"),
                "family": data.get("family"),
                "API": "GBIF"
            }

    except Exception:
        return None
    return None

# --------------------------------------------------
# Optional geocoding
# --------------------------------------------------
def get_coordinates(address):
    if not address or pd.isna(address):
        return None, None
    try:
        session = get_session()
        params = {
            'access_key': POSITIONSTACK_API_KEY,
            'query': str(address),
            'limit': 1
        }

        response = session.get(
            POSITIONSTACK_BASE,
            params=params,
            timeout=10
        )

        response.raise_for_status()
        data = response.json().get("data")
        if data:
            return (
                data[0].get("latitude"),
                data[0].get("longitude")
            )
    except Exception:
        return None, None
    return None, None

# --------------------------------------------------
# Process one taxon
# --------------------------------------------------
def process_name(name):
    if not name or pd.isna(name):
        return {
            "canonical_name": None,
            "order": None,
            "family": None,
            "API": None
        }

    # Try iNaturalist
    result = query_inaturalist(name)

    if result:
        return result
    # Try GBIF
    result = query_gbif(name)
    if result:
        return result

    # Try fuzzy matching
    closest = find_closest_taxon(name)
    if closest:
        result = query_inaturalist(closest)
        if result:
            return result

    return {
        "canonical_name": None,
        "order": None,
        "family": None,
        "API": None
    }

# --------------------------------------------------
# Multithreaded processing
# --------------------------------------------------
def process_name_list(names):
    results = [None] * len(names)
    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:
        future_to_idx = {
            executor.submit(process_name, name): idx
            for idx, name in enumerate(names)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception:
                results[idx] = {
                    "canonical_name": None,
                    "order": None,
                    "family": None,
                    "API": None
                }
    return pd.DataFrame(results)

# --------------------------------------------------
# Split taxa
# --------------------------------------------------
def split_and_clean(name):
    if pd.isna(name):
        return []
    return [
        p.split(":")[-1].strip()
        for p in re.split(r'[&/,;]', str(name))
        if p.strip()
    ]

# --------------------------------------------------
# Expand dataset
# --------------------------------------------------
def expand_dataset(df):
    rows = []
    for _, row in df.iterrows():
        split_values = split_and_clean(
            row['insect_taxon']
        )
        # Keep original row if empty
        if not split_values:
            rows.append(row.copy())
        else:
            for val in split_values:
                new_row = row.copy()
                new_row['insect_taxon'] = val
                rows.append(new_row)
    return pd.DataFrame(rows)

# --------------------------------------------------
# Main
# --------------------------------------------------
def main(args):
    # Input CSV read
    df_input = pd.read_csv(args.input_csv, encoding="utf8")

    print(f"Loaded {len(df_input)} rows")

    # Expand rows with multiple taxa
    expanded_df = expand_dataset(df_input)

    print(f"Expanded to {len(expanded_df)} rows")

    # Resolve taxonomy
    df_taxon = process_name_list(expanded_df['insect_taxon'].tolist())

    # Merge results
    final_df = pd.concat(
        [
            expanded_df.reset_index(drop=True),
            df_taxon.reset_index(drop=True)
        ],
        axis=1
    )


    final_df.to_csv(args.output_file,index=False)

    print(f"Saved to: {args.output_file}")

    print("\nPreview:")
    print(final_df.head())

# --------------------------------------------------
# Run
# --------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Postprocessing after table generation")
    parser.add_argument("--input_csv", default="haba_generated_table_all_inaturalist_try.csv", type=str, help="Input CSV file with generated table")
    parser.add_argument("--output_file", default="anomaly_detection_results.json", type=str, help="Output file for the results")
    args = parser.parse_args()
    main(args)
