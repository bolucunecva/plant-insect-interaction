import os
import json
import argparse
from PyPDF2 import PdfReader




def main(args):
    # Folder containing PDFs
    folder_path = args.folder

    # Loop through all files in the folder
    count = 0
    for filename in os.listdir(args.folder):
        if filename.endswith(".pdf"):
            file_path = os.path.join(folder_path, filename)
            try:
                reader = PdfReader(file_path)
                num_pages = len(reader.pages)
                if num_pages == 1:
                    count +=1
            except Exception as e:
                # print(f"Error reading {filename}: {e}")
                count += 1
    print(f"Total non readable and 1 page papers are {str(count)}")



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="One page checker")
    parser.add_argument("--folder", type=str, required=True, help="Folder with PDFs.")
    args = parser.parse_args()
    main(args)
