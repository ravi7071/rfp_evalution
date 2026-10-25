from __future__ import annotations

import argparse

from ingestion import extract_text_from_pdf_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract raw text from a PDF file.")
    parser.add_argument("pdf_path", help="Path to the test PDF file")
    args = parser.parse_args()

    extracted_text = extract_text_from_pdf_path(args.pdf_path)
    print("--- Extracted text start ---")
    print(extracted_text)
    print("--- Extracted text end ---")


if __name__ == "__main__":
    main()

