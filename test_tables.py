import pdfplumber

pdf = pdfplumber.open("FullPricelist_B-1.pdf")

for page_number, page in enumerate(pdf.pages, 1):
    print(f"\n===== PAGE {page_number} =====")
    tables = page.extract_tables()

    if not tables:
        print("NO TABLES FOUND")
        continue

    for t_index, table in enumerate(tables):
        print(f"\n--- TABLE {t_index+1} ---")
        for row in table:
            print(row)
