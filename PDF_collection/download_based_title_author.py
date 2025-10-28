import os
import json
import re
import requests
import argparse
import time

def doi_to_filename(doi):
    # Replace any character that's not alphanumeric or -_. with _
    return re.sub(r'[^\w\-_\.]', '_', doi)

def find_doi_by_title_author(title, authors, max_results=3):
    """
    Find DOI using Crossref API based on title and author(s).

    Args:
        title (str): Paper title.
        authors (str): Author names as a string.
        max_results (int): Maximum number of results to return.

    Returns:
        list of tuples: [(DOI, Title, Year), ...]
    """
    url = "https://api.crossref.org/works"
    params = {
        "query.title": title,
        "query.author": authors,
        "rows": max_results
    }

    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    results = []
    for item in data["message"]["items"]:
        doi = item.get("DOI")
        paper_title = item.get("title", [""])[0]
        pub_year = None
        if "published-print" in item:
            pub_year = item["published-print"]["date-parts"][0][0]
        elif "published-online" in item:
            pub_year = item["published-online"]["date-parts"][0][0]
        results.append((doi, paper_title, pub_year))

    return results

def is_open_access(doi):
    url = f"https://api.unpaywall.org/v2/{doi}?email=necva.bolucu@csiro.au"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data.get("is_oa") and data.get("best_oa_location") and data["best_oa_location"].get("url_for_pdf"):
            return data["best_oa_location"]["url_for_pdf"]
    return None


def download_pdf_from_url(pdf_url, doi, save_dir):
    import time
    os.makedirs(save_dir, exist_ok=True)
    filename = doi_to_filename(doi) + ".pdf"
    filepath = os.path.join(save_dir, filename)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/114.0.0.0 Safari/537.36"
        ),
        "Accept": "application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://jvi.asm.org/",
        "Connection": "keep-alive",
    }

    session = requests.Session()
    session.headers.update(headers)

    try:
        response = session.get(pdf_url, allow_redirects=True, timeout=20)
        content_type = response.headers.get("Content-Type", "")
        if response.status_code == 200 and "application/pdf" in content_type:
            with open(filepath, "wb") as f:
                f.write(response.content)
            print(f"[SUCCESS] Saved PDF to {filepath}")
            return True
        else:
            print(f"[ERROR] Status: {response.status_code}, Content-Type: {content_type}")
            if response.status_code == 403:
                print(
                    "[HINT] This may be due to bot protection. Try accessing manually or use a browser automation tool.")
            return False
    except Exception as e:
        print(f"[EXCEPTION] Error downloading from {pdf_url}: {e}")
        return False


def download_pdf(doi, save_dir="PDF_trial_", retries=2):

    url = is_open_access(doi)
    if not doi or not url:
        print("[SKIP] Missing DOI or PDF URL")
        return False

    filename = doi_to_filename(doi) + ".pdf"
    os.makedirs(save_dir, exist_ok=True)
    filepath = os.path.join(save_dir, filename)

    # Multiple user agents and referrers to try
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    ]
    referrers = [
        "https://doi.org/" + doi,
        "https://scholar.google.com/",
        "https://www.unpaywall.org/"
    ]

    for attempt in range(retries):
        for agent in user_agents:
            for referer in referrers:
                headers = {
                    "User-Agent": agent,
                    "Referer": referer,
                }
                try:
                    print(f"[TRY] {url} | Agent: {agent} | Referer: {referer}")
                    response = requests.get(url, headers=headers, timeout=20)
                    if response.status_code == 200 and 'application/pdf' in response.headers.get('Content-Type', ''):
                        with open(filepath, 'wb') as f:
                            f.write(response.content)
                        print(f"[OK] Downloaded: {filepath}")
                        return True
                except Exception as e:
                    print(f"[WARN] Attempt failed: {e}")
        time.sleep(1)
    print(f"[FAIL] Failed to download PDF from {url}")
    return False


def main(args):
    # Load json file
    with open(f"{args.output_folder}/used_meta_and_status_updated.json", "r", encoding="utf-8") as f:
        papers = json.load(f)

    # start downloading
    new_papers = []
    for paper in papers:
        if paper['download_status'] == False:
            if paper['doi'] == "None" and paper['title'] is not None:

                try:
                    matches = find_doi_by_title_author(
                        title=paper['title'],
                        authors=paper['author']
                    )

                    print(paper['title'], matches[0][0])
                    paper['doi'] = matches[0][0]
                    success = download_pdf(matches[0][0], args.output_folder)
                    # success = download_pdf_from_url(paper['pdf_url'], paper['extra_doi'], "PDF_trial")
                    if not success:
                        print(f"[INFO] Unpaywall PDF download failed for DOI: {matches[0][0]}")
                    else:
                        paper["download_status"] = True
                        paper["download_file_name"] = f"{doi_to_filename( paper['doi'])+'.pdf'}"
                except:
                    ''

    # Save updated JSON
    with open(f"{args.output_folder}/used_meta_and_status_updated.json", "w", encoding="utf-8") as f:
        json.dump(papers, f, indent=2, ensure_ascii=False)



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Open access PDf download")
    parser.add_argument("--output_folder", type=str, required=True, help="Output folder to save Pdfs.")
    args = parser.parse_args()
    main(args)
