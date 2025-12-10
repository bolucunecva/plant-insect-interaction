import requests
import argparse


# API endpoint
url = "http://130.155.192.43:8083/download_PDFs_from_BibFile"
  
    
def main(args):
    bib_file_path = args.bib_file
    output_zip_path = args.zip_file
    

    with open(bib_file_path, "rb") as f:
        file_data = {'upload_file': f}
        response = requests.post(url, files=file_data)

    # Check if the request was successful
    if response.status_code == 200:
        with open(output_zip_path, "wb") as out_file:
            out_file.write(response.content)
        print(f"PDFs downloaded successfully to {output_zip_path}")
    else:
        print(f"Failed to download PDFs. Status code: {response.status_code}")
        print(response.text)
    
if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument("--bib_file", type=str, required=True, help="Path to the bib file.")
    parser.add_argument("--zip_file", type=str, required=True, help="Path to the zip file for downloaded PDFs.")

    args = parser.parse_args()
    main(args)
