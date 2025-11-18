import requests
import pdfplumber
import re
import json


# ===========================================================
# CONFIG
# ===========================================================
BASE_URL = "https://propertprodjango.onrender.com/api/dev/v1"
ORGANIZATION_ID = 2
SESSION = requests.Session()
ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzYzNDc1OTA2LCJpYXQiOjE3NjM0NjE1MDYsImp0aSI6ImM3OTMxYTFjMzgwZjQ0M2ZhYmEwNjJhNGFkZjNiNThiIiwidXNlcl9pZCI6MTJ9.yQtYrEWKvaFW6qIYZzBJDMBeIs9ppvdSUSmJhV5er2k"



# ===========================================================
# COOKIE LOADING (paste browser cookies)
# ===========================================================
def load_cookies_from_browser(cookie_string: str):
    cookie_pairs = cookie_string.split(";")
    for pair in cookie_pairs:
        if "=" in pair:
            name, value = pair.strip().split("=", 1)
            SESSION.cookies.set(name, value)


# ===========================================================
# API HELPERS
# ===========================================================
def api_post(endpoint, data=None):
    url = f"{BASE_URL}/{endpoint.strip('/')}/"

    headers = {
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ACCESS_TOKEN}",
    }

    resp = SESSION.post(url, data=data, headers=headers)

    if resp.status_code >= 400:
        print(f"[ERROR] POST {url} → {resp.status_code}: {resp.text}")

    return resp



# ===========================================================
# PROJECT CREATION
# ===========================================================
def create_project(name):
    payload = {
        "organization": ORGANIZATION_ID,
        "name": name,
        "description": "",
        "location": "Paphos",
        "country": "Cyprus",
        "status": "available",
        "total_units": 0,
        "available_units": 0,
        "currency": "EUR",
        "property_types": [],
        "amenities": [],
        "features": [],
        "metadata": {},
        "is_published": False
    }

    r = api_post("projects", json.dumps(payload))
    if r.status_code == 201:
        pid = r.json()["id"]
        print(f"[PROJECT CREATED] {name} → ID {pid}")
        return pid

    print(f"[PROJECT FAILED] {name}")
    return None


# ===========================================================
# UNIT CREATION
# ===========================================================
def create_unit(project_id, unit):
    payload = {
        "project": project_id,
        "code": unit["code"],
        "unit_type": unit["unit_type"],
        "bedrooms": unit["bedrooms"],
        "bathrooms": unit["bathrooms"],
        "area_internal": unit["area_internal"],
        "area_veranda": unit["area_veranda"],
        "area_total": unit["area_total"],
        "price": unit["price"],
        "currency": "EUR",
        "vat_included": False,
        "status": unit["status"],
        "floor": unit["floor"],
        "plot": unit["plot"],
        "plot_area": unit["plot_area"],
        "veranda": unit["veranda"],
        "veranda_area": unit["veranda_area"],
        "pool": "none",
        "pool_area": None,
        "is_published": False
    }

    r = api_post("units", json.dumps(payload))
    if r.status_code == 201:
        print(f"   → UNIT CREATED: {unit['code']}")
    else:
        print(f"   → ERROR creating {unit['code']}: {r.text}")


# ===========================================================
# SAFE FLOAT
# ===========================================================
def safe_float(v):
    try:
        v = v.replace(",", "")
        return float(v)
    except:
        return None


# ===========================================================
# PARSE A TABLE ROW INTO A UNIT
# ===========================================================
def parse_unit_row(row, project_name, block_prefix):
    # Normalize row: convert None to ""
    row = [(x or "").strip() for x in row]

    # Skip invalid rows
    if len(row) < 2:
        return None

    # Header row like ["Unit", ...]
    if row[0].lower() == "unit":
        return None

    # First column must be the unit number
    unit_number = row[0]
    if not unit_number.isdigit():
        return None

    # Ensure row ALWAYS has 11 columns
    # (Pad missing values)
    while len(row) < 11:
        row.append("")

    # Extract columns safely
    bedrooms = safe_float(row[1])
    plot = safe_float(row[2])
    bathrooms = safe_float(row[3])
    internal = safe_float(row[4])
    veranda = safe_float(row[6])
    total_area = safe_float(row[8])
    price_raw = row[10] if len(row) > 10 else ""

    # Status logic
    status_text = price_raw.lower()
    if "sold" in status_text:
        status = "sold"
        price = None
    elif "reserv" in status_text:
        status = "reserved"
        price = None
    else:
        status = "available"
        price = safe_float(price_raw)

    # Build final unit code
    code = f"{block_prefix}-{unit_number}"

    return {
        "project_name": project_name,
        "code": code,
        "unit_type": "house",
        "bedrooms": int(bedrooms or 0),
        "bathrooms": int(bathrooms or 1),
        "area_internal": internal,
        "area_veranda": veranda,
        "area_total": total_area,
        "price": price,
        "status": status,
        "floor": block_prefix,
        "plot": "private" if plot else "none",
        "plot_area": plot,
        "veranda": "private" if veranda else "none",
        "veranda_area": veranda,
    }



# ===========================================================
# PDF PARSER MASTER FUNCTION
# ===========================================================
def parse_pdf(pdf_path):
    all_units = {}
    current_project = None

    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""

            # PROJECT detection based on first line
            first_line = text.split("\n")[0].strip()
            if len(first_line) > 3 and not re.search(r"[0-9]", first_line):
                current_project = first_line
                print(f"[PROJECT DETECTED] Page {page_number}: {current_project}")
                if current_project not in all_units:
                    all_units[current_project] = []

            # Extract tables
            tables = page.extract_tables()
            if not tables:
                continue

            for table in tables:
                # Expect villa-like table (first row is header of big table)
                if len(table) < 3:
                    continue

                # Every row after header+subheader is a unit
                for row in table[2:]:
                    if not row or not row[0]:
                        continue
                    unit = parse_unit_row(row, current_project, "Villa")
                    if unit:
                        all_units[current_project].append(unit)

    return all_units


# ===========================================================
# MAIN PROCESS
# ===========================================================
def import_pdf(pdf_path, cookie_string):
    load_cookies_from_browser(cookie_string)

    all_projects = parse_pdf(pdf_path)

    print("\n==============================")
    print("  STARTING IMPORT")
    print("==============================")

    for project_name, units in all_projects.items():
        print(f"\n--- PROJECT: {project_name} ---")
        print(f"Units detected: {len(units)}")

        pid = create_project(project_name)
        if not pid:
            print("Skipping this project.")
            continue

        for unit in units:
            create_unit(pid, unit)

    print("\n==============================")
    print("   IMPORT COMPLETE")
    print("==============================\n")


# ===========================================================
# RUN
# ===========================================================
if __name__ == "__main__":
    pdf_file = "FullPricelist_B-1.pdf"
    cookie_string = ""   # <<< paste from your browser

    import_pdf(pdf_file, cookie_string)
