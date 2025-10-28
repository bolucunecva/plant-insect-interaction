import re
import time
import json
import requests
import argparse
import json_repair
import pandas as pd
from typing import Optional, Union, List
from sklearn.model_selection import train_test_split
import random
import numpy as np

def get_prompt_baseline(text_body: str, columns_list: list) -> str:
    # Step 1: Construct dictionary key mapping instructions
    key_mapping_instruction_list = ["[Dictionary Key Mapping in your response]\n{"]

    for col_name in columns_list:
        instruction_context = f"'{col_name}',"
        key_mapping_instruction_list.append(instruction_context)

    if key_mapping_instruction_list[-1].endswith(","):
        key_mapping_instruction_list[-1] = key_mapping_instruction_list[-1][:-1]  # Remove trailing comma
    key_mapping_instruction_list.append("}")

    key_mapping_instruction = "\n".join(key_mapping_instruction_list)
    production_table_columns = ", ".join(columns_list)

    return (
        f"Please, extract {production_table_columns} from the given article.\n"
        f"For the extracted information, you MUST respond in a list of JSON dictionaries "
        f"structure with the given Dictionary Key Mapping.\n\n{key_mapping_instruction}\n\n"
        f"[Given Article Start]\n\n{text_body}\n\n[Given Article End]"
    )


def extract_json_list_from_text_(text: str) -> list:
    """Extract list of JSON dictionaries from text."""
    text = text.replace("\n", " ")
    pattern = r'\[\s*\{.*\}\s*\]'
    match = re.search(pattern, text)
    if match:
        try:
            loaded = json_repair.loads(match.group(0))
            return [item for item in loaded if isinstance(item, dict)] if isinstance(loaded, list) else []
        except Exception:
            return []
    return []


def extract_json_list_from_text(text: str):
    """Extract list of JSON dictionaries from model output."""
    # Remove markdown fences like ```json ... ```
    clean_text = re.sub(r"```(?:json)?", "", text).strip()

    # Regex: extract the first [...] block containing JSON objects
    pattern = r'\[\s*\{.*?\}\s*\]'
    searched = re.search(pattern, clean_text, flags=re.DOTALL)

    if searched:
        try:
            loaded_extraction = json_repair.loads(searched.group(0))
            if isinstance(loaded_extraction, list):
                return [item for item in loaded_extraction if isinstance(item, dict)]
        except Exception as e:
            print(f"JSON repair failed: {e}")
            return []
    return []


def save_file(data_dict, csv_filename):
    """
    Save a nested dictionary to CSV.

    Args:
        data_dict (dict): Dictionary where each key maps to a list of dictionaries.
        csv_filename (str): Name/path of the CSV file to save.
    """
    rows = []
    for pdf_file, entries in data_dict.items():
        for entry in entries:
            row = entry.copy()
            row["pdf_file"] = pdf_file  # add filename as a column
            rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(csv_filename, index=False)
    print(f"CSV saved successfully as '{csv_filename}'!")


def save_file_raw(data_dict, csv_filename):
    import json
    with open(csv_filename, 'w') as fp:
        json.dump(data_dict, fp)


def main(args):
    url = "http://lt02-ep:11434/api/chat"

    max_retries = 10
    wait_time = 2  # seconds


    column_list = "insect family:::insect taxon:::plant family:::plant taxon:::plant organ:::geographiclocation:::latitude:::longtitude:::primary source".split(":::")

    # Set seed for reproducibility
    seed = args.seed if hasattr(args, "seed") else 42
    random.seed(seed)
    np.random.seed(seed)

    # Load dataset
    dataset = pd.read_csv(f"plant_insect_dataset.csv")
    dataset = dataset.head(50)
 
    prediction = {}
    prediction_raw = {}

    # Start measuring time
    start_time = time.time()

    # Iterate through each row (article) in the dataset
    for index, row in dataset.iterrows():
        prompt = get_prompt_baseline(row['doc_full_text'], column_list)
        messages = [
            {"role": "user", "content": prompt}
        ]

        payload = {
            "model": args.model_id,
            "messages": messages,
            "temperature": 0.0,
            "stream": False,
            "options": {"num_ctx": 30000, "think": "low"}
        }

        # Retry loop for robustness
        success = False
        for attempt in range(max_retries):
            try:
                response = requests.post(url, data=json.dumps(payload))
                response_json = response.json()
                respond_raw = response_json.get("message", {}).get('content', '')

                extracted = extract_json_list_from_text(respond_raw)
                if extracted:
                    prediction[row['paper_id']] = extracted
                    prediction_raw[row['paper_id']] = respond_raw
                    success = True
                    break
                else:
                    print(f"Empty result for {row['paper_id']} (attempt {attempt + 1})")
            except Exception as e:
                print(f"Error on {row['paper_id']} attempt {attempt + 1}: {e}")
            time.sleep(wait_time)

        if not success:
            prediction[row['paper_id']] = []
            prediction_raw[row['paper_id']] = ""

    # End measuring time
    end_time = time.time()
    total_time_sec = end_time - start_time
    print(f"Total prediction time: {total_time_sec:.2f} seconds")
    print(f"Average time per article: {total_time_sec / len(dataset):.2f} seconds")

    # Save results
    save_file(prediction, f"{args.model_id}_zero_prediction.csv")
    save_file_raw(prediction_raw, f"{args.model_id}_zero_prediction_raw.json")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plant insect data from articles using LLM.")
    parser.add_argument("--model_id", type=str, required=True, help="API Model ID.")
    parser.add_argument("--seed", type=int, default=42, help="seed value")
    args = parser.parse_args()

    main(args)
