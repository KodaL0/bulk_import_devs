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

ACCESS_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzYzNDk5MTEwLCJpYXQiOjE3NjM0ODQ3MTAsImp0aSI6IjY0ZWMzMjYyOGIyYTQ0MzY5OWJjZWUyMDBiZWVmYzY5IiwidXNlcl9pZCI6MTJ9.SIhIr-o4uQO-FIxLVoscwehaKav0uQWQyqVgm9QtZw4"
)

# ===========================================================
# API HELPERS
# ===========================================================
def api_post(endpoint, data=None):
    url = f"{BASE_URL}/{endpoint.strip('/')}/"

    headers = {
        "Accept": "application/json",
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
        "floor": "",  # ALWAYS EMPTY
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
# HELPERS
# ===========================================================
def safe_float(v):
    try:
        v = v.replace(",", "")
        return float(v)
    except:
        return None


# ===========================================================
# PARSE UNIT ROW
# ===========================================================
def parse_unit_row(row, project_name):
    row = [(x or "").strip() for x in row]

    if len(row) < 2:
        return None

    unit_raw = row[0]

    # --- Skip header rows ---
    if unit_raw.lower() == "unit":
        return None

    # =======================================================
    # IDENTITY RULE: VILLA OR BLOCK UNIT?
    # =======================================================

    if unit_raw.isdigit():
        # Villa
        code = f"Villa-{unit_raw}"
        unit_type = "house"
    else:
        # Block-type unit (A101, M102, L003, A201 etc.)
        code = re.sub(r"[^A-Za-z0-9]", "", unit_raw)  # Clean
        unit_type = "apartment"

    # Ensure proper row padding
    while len(row) < 11:
        row.append("")

    bedrooms = safe_float(row[1])
    plot = safe_float(row[2])
    bathrooms = safe_float(row[3])
    internal = safe_float(row[4])
    veranda = safe_float(row[6])
    total_area = safe_float(row[8])
    price_raw = row[10]

    # Determine status
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

    return {
        "project_name": project_name,
        "code": code,
        "unit_type": unit_type,
        "bedrooms": int(bedrooms or 0),
        "bathrooms": int(bathrooms or 1),
        "area_internal": internal,
        "area_veranda": veranda,
        "area_total": total_area,
        "price": price,
        "status": status,
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

            # PROJECT DETECTION
            first_line = text.split("\n")[0].strip()
            if len(first_line) > 3 and not re.search(r"[0-9]", first_line):
                current_project = first_line
                print(f"[PROJECT DETECTED] Page {page_number}: {current_project}")
                all_units.setdefault(current_project, [])

            # EXTRACT TABLES
            for table in page.extract_tables() or []:
                if len(table) < 3:
                    continue

                # Parse real unit rows (skip header rows)
                for row in table[2:]:
                    if not row or not row[0]:
                        continue

                    # Remove "Penthouse" lines
                    if "penthouse" in row[0].lower():
                        continue

                    unit = parse_unit_row(row, current_project)
                    if unit:
                        all_units[current_project].append(unit)

    return all_units


# ===========================================================
# MAIN PROCESS
# ===========================================================
def import_pdf(pdf_path):
    all_projects = parse_pdf(pdf_path)

    print("\n==============================")
    print("  STARTING IMPORT")
    print("==============================")

    for project_name, units in all_projects.items():
        print(f"\n--- PROJECT: {project_name} ---")
        print(f"Units detected: {len(units)}")

        pid = create_project(project_name)
        if not pid:
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
    import_pdf(pdf_file)
