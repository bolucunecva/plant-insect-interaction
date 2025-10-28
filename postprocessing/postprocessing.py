import pandas as pd
import requests
import re
from rapidfuzz import process, fuzz
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import argparse
# -------------------------------
# Config
# -------------------------------
BASE_URL_INAT = "https://api.inaturalist.org/v1"
GBIF_URL = "https://api.gbif.org/v1/species/match"
POSITIONSTACK_API_KEY = "aba96cd2e294af194af1da5bf234a039"
POSITIONSTACK_BASE = "http://api.positionstack.com/v1/forward"


columns_to_split = ["insect taxon"]
MAX_WORKERS = 20  # parallel threads for APIs

# -------------------------------
# Load taxa CSV
# -------------------------------
def load_active_taxa(csv_file):
    df = pd.read_csv("inaturalist-open-data-20250927/taxa.csv", sep="\t", on_bad_lines='skip', low_memory=True)
    active_df = df[df['active']].copy()
    return active_df

active_df = load_active_taxa("inaturalist-open-data-20250927/taxa.csv")
names = active_df['name'].tolist()

# -------------------------------
# HTTP sessions
# -------------------------------
session_inat = requests.Session()
session_geo = requests.Session()

# -------------------------------
# Fuzzy match
# -------------------------------
def find_closest_taxon(query_name):
    best_match = process.extractOne(
        query_name, names,
        scorer=fuzz.token_sort_ratio,
        score_cutoff=70
    )
    if best_match:
        closest_name, score, idx = best_match
        match_row = active_df.iloc[idx]
        return {
            'query_name': query_name,
            'closest_name': match_row['name'],
            'taxon_id': match_row['taxon_id'],
            'ancestry': match_row['ancestry'],
            'rank': match_row['rank'],
            'similarity_score': score
        }
    return None

# -------------------------------
# iNaturalist API
# -------------------------------
def query_inaturalist(name):
    try:
        for endpoint in ["taxa", "taxa/autocomplete"]:
            resp = session_inat.get(f"{BASE_URL_INAT}/{endpoint}", params={"q": name}, timeout=10)
            resp.raise_for_status()
            data = resp.json().get("results")
            if data:
                taxon = data[0]
                hierarchy = taxon.get("ancestors", [])
                return {
                    "query": name,
                    "taxon_id": taxon.get("id"),
                    "canonical_name": taxon.get("name"),
                    "synonyms": taxon.get("matched_term"),
                    "rank": taxon.get("rank"),
                    "hierarchy": " > ".join([a.get("name") for a in hierarchy if "name" in a]),
                    "is_active": taxon.get("is_active", True),
                    "API": "iNaturalist"
                }
    except requests.RequestException:
        return None
    return None

# -------------------------------
# GBIF fallback
# -------------------------------
def query_gbif(name):
    try:
        resp = session_inat.get(GBIF_URL, params={"name": name}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("matchType") in ["EXACT", "HIGHERRANK"]:
            hierarchy = [data.get(rank) for rank in ["kingdom","phylum","class","order","family","genus"] if data.get(rank)]
            return {
                "query": name,
                "taxon_id": data.get("usageKey"),
                "canonical_name": data.get("scientificName"),
                "synonyms": None,
                "rank": data.get("rank"),
                "hierarchy": " > ".join(hierarchy),
                "is_active": True,
                "API": "GBIF"
            }
    except requests.RequestException:
        return None
    return None

# -------------------------------
# Positionstack geocoding
# -------------------------------
def get_coordinates(address):
    if not address or pd.isna(address) or str(address).strip() == "":
        return None, None
    try:
        params = {'access_key': POSITIONSTACK_API_KEY, 'query': str(address), 'limit': 1}
        resp = session_geo.get(POSITIONSTACK_BASE, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data")
        if data:
            lat = data[0].get("latitude")
            lon = data[0].get("longitude")
            return lat, lon
    except requests.RequestException:
        return None, None
    return None, None

# -------------------------------
# Process a single taxon
# -------------------------------
def process_name(name):
    if not name or pd.isna(name):
        return {
            "query": None,
            "taxon_id": None,
            "canonical_name": None,
            "synonyms": None,
            "rank": None,
            "hierarchy": None,
            "is_active": None,
            "API": None
        }
    clean_name = str(name).strip()
    result = query_inaturalist(clean_name)
    if result:
        return result
 
    result = query_gbif(clean_name)
    if result:
        return result
    
    closest = find_closest_taxon(clean_name)
    if closest:
        result = query_inaturalist(closest['closest_name'])
        if result:
            return result


    
    return {
        "query": clean_name,
        "taxon_id": None,
        "canonical_name": None,
        "synonyms": None,
        "rank": None,
        "hierarchy": None,
        "is_active": None,
        "API": None
    }

# -------------------------------
# Process list of names in parallel
# -------------------------------
def process_name_list(names):
    """
    Process list of taxon names sequentially, preserving order.
    """
    results = []
    for name in names:
        result = process_name(name)
        results.append(result)
        time.sleep(0.1)  # optional: small delay to avoid hammering APIs
    return pd.DataFrame(results)

# -------------------------------
# Split and clean multiple taxon names
# -------------------------------
def split_and_clean(name):
    if pd.isna(name):
        return []
    parts = re.split(r'[&/,;]', str(name))
    cleaned = []
    for p in parts:
        if ':' in p:
            p = p.split(':')[-1]
        p = p.strip()
        if p:
            cleaned.append(p)
    return cleaned

def expand_dataset(df):
    expanded_rows = []
    for idx, row in df.iterrows():
        split_values = {}
        max_len = 1
        for col in columns_to_split:
            values = split_and_clean(row[col])
            split_values[col] = values
            if len(values) > max_len:
                max_len = len(values)

        for i in range(max_len):
            new_row = row.to_dict()
            for col in columns_to_split:
                if i < len(split_values[col]):
                    new_row[col] = split_values[col][i]
                else:
                    new_row[col] = split_values[col][0] if split_values[col] else None
            expanded_rows.append(new_row)

    expanded_df = pd.DataFrame(expanded_rows)
    expanded_df.reset_index(drop=True, inplace=True)
    return expanded_df


API_KEY = "55648fea201148dda5416aef1bf1946c"
def get_coordinates_opencage(address):
    if not address:
        return None, None
    url = "https://api.opencagedata.com/geocode/v1/json"
    params = {"q": address, "key": API_KEY, "limit": 1}
    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if data["results"]:
            loc = data["results"][0]["geometry"]
            return loc["lat"], loc["lng"]
    except:
        return None, None
    return None, None


# -------------------------------
# Main
# -------------------------------
def main(args):   
    # Load input dataset
    df_input = pd.read_csv(args.input_file, encoding="utf8")

    # Expand insect taxon column
    expanded_df = expand_dataset(df_input)
    
    # Process insect taxa in parallel
    insect_taxon = list(expanded_df['insect taxon'])
    df_taxon = process_name_list(insect_taxon)
    
    # Add latitude and longitude for location column
    latitudes, longitudes = [], []
    for loc in expanded_df['geographiclocation']:
        lat, lon = get_coordinates_opencage(loc)
        latitudes.append(lat)
        longitudes.append(lon)
    
    expanded_df['latitude_API'] = latitudes
    expanded_df['longitude_API'] = longitudes
    
    # Merge taxon info back into dataset
    final_df = pd.concat([expanded_df.reset_index(drop=True), df_taxon.reset_index(drop=True)], axis=1)
    
    # Save
    final_df.to_csv(args.output_file, index=False)
    print(final_df.head())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Postprocessing")
    parser.add_argument("--input_file", type=str, required=True, help="Input csv file")
    parser.add_argument("--output_file", type=str, required=True, help="Output csv file")
    args = parser.parse_args()

    main(args)
