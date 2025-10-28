import requests
import os
import json
import re
import argparse


def doi_to_filename(doi):
    # Replace any character that's not alphanumeric or -_. with _
    return re.sub(r'[^\w\-_\.]', '_', doi)


headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}


def is_open_access(doi):
    url = f"https://api.unpaywall.org/v2/{doi}?email=necva.bolucu@csiro.au"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data.get("is_oa") and data.get("best_oa_location") and data["best_oa_location"].get("url_for_pdf"):
            return data["best_oa_location"]["url_for_pdf"]
    return None

def download_pdf_from_url(pdf_url, doi, save_dir):
    os.makedirs(save_dir, exist_ok=True)
    filename = doi_to_filename(doi) + ".pdf"
    filepath = os.path.join(save_dir, filename)
    try:
        response = requests.get(pdf_url, timeout=15)
        if response.status_code == 200 and "application/pdf" in response.headers.get("Content-Type", ""):
            with open(filepath, "wb") as f:
                f.write(response.content)
            print(f"[SUCCESS] Saved PDF to {filepath}")
            return True
        else:
            print(f"[ERROR] Failed to download PDF from {pdf_url} (status {response.status_code})")
            return False
    except Exception as e:
        print(f"[EXCEPTION] Error downloading from {pdf_url}: {e}")
        return False

def download_pdf(paper, save_dir="PDF_trial_"):
    paper['pdf_url'] = ''
    doi = paper.get("doi")
    if not doi:
        print("[SKIP] No DOI found in paper.")
        return paper

    print(f"\n[INFO] Processing DOI: {doi}")

    # First: Try Unpaywall PDF
    try:
        pdf_url = is_open_access(doi)
        if pdf_url:
            print(f"[INFO] Found OA PDF from Unpaywall: {pdf_url}")
            success = download_pdf_from_url(pdf_url, doi, save_dir)

            if success:
                paper['pdf_url'] = pdf_url
                return
            else:
                print(f"[INFO] Unpaywall PDF download failed.")
        else:
            print(f"[INFO] No fallback PDF URL available for DOI: {doi}")
    except:
        ''
    return paper



def main(args):
    # Load json file
    with open(f"{args.output_folder}/used_meta_and_status.json", "r", encoding="utf-8") as f:
        papers = json.load(f)

    # start downloading
    new_papers = []
    for paper in papers:
        if not paper['download_file_name'] and paper['doi']:
            updated_paper = download_pdf(paper, args.output_folder)

            # If PDF was downloaded (pdf_url is set), update download_file_name
            try:
                updated_paper.get('pdf_url')
                # Assume download_pdf saved the file in output_folder with DOI-based name
                doi = updated_paper['doi']
                updated_paper['download_file_name'] = doi_to_filename(doi) + ".pdf"
            except:
                ''

            new_papers.append(updated_paper)
        else:
            new_papers.append(paper)

    # Save updated JSON
    with open(args.input_file[:5] + "_open_access.json", "w", encoding="utf-8") as f:
        json.dump(new_papers, f, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Open access PDf download")
    parser.add_argument("--output_folder", type=str, required=True, help="Output folder to save Pdfs.")
    args = parser.parse_args()

    main(args)
