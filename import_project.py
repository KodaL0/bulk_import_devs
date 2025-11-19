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
ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzYzNTY0NDUyLCJpYXQiOjE3NjM1NTAwNTIsImp0aSI6IjA3NDAxZjIzOTc5NjQ5MTQ4YTk1NmE2YThkMGQyMWI1IiwidXNlcl9pZCI6MTJ9.NzaPrkoYuiL6r_c77RU4G7wy_DlvG4bVZnC0OLYDVIA"


# ===========================================================
# UTILITIES
# ===========================================================
def safe_float(v):
    """Convert messy PDF strings into float."""
    if v is None:
        return None
    v = str(v).replace(",", "").strip()
    v = re.sub(r"[^0-9.]", "", v)
    if v == "":
        return None
    try:
        return float(v)
    except:
        return None


def detect_status(row_text):
    row_text = row_text.lower()
    if "sold" in row_text:
        return "sold"
    if "reserv" in row_text:
        return "reserved"
    return "available"


def extract_price(cell):
    if cell is None:
        return None
    txt = str(cell)
    # Grab numbers only
    numbers = re.sub(r"[^0-9]", "", txt)
    return float(numbers) if numbers else None


def is_block_unit(value):
    return bool(re.match(r"^[A-Z]+[0-9]+$", value))


def is_villa_unit(value):
    return value.isdigit()


# ===========================================================
# API HELPERS
# ===========================================================
def api_post(endpoint, data=None):
    url = f"{BASE_URL}/{endpoint.strip('/')}/"

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }

    resp = SESSION.post(url, data=data, headers=headers)
    if resp.status_code >= 400:
        print(f"[ERROR] POST {url} → {resp.status_code}: {resp.text}")

    return resp


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


def create_unit(project_id, unit):
    r = api_post("units", json.dumps(unit))
    if r.status_code == 201:
        print(f"   → UNIT CREATED: {unit['code']}")


# ===========================================================
# PARSING LOGIC
# ===========================================================
def parse_pdf(pdf_path):
    all_data = {}
    current_project = None
    current_block = None

    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            first_line = text.split("\n")[0].strip()

            # Detect project title
            if len(first_line) > 3 and not any(char.isdigit() for char in first_line):
                current_project = first_line
                print(f"[PROJECT DETECTED] Page {page_number}: {current_project}")
                all_data[current_project] = []
                current_block = None

            tables = page.extract_tables()
            if not tables:
                continue

            for table in tables:
                if len(table) < 2:
                    continue

                header = [h.lower().strip() if h else "" for h in table[0]]

                # Detect column indexes dynamically
                col = {
                    "unit": None,
                    "beds": None,
                    "baths": None,
                    "internal": None,
                    "veranda": None,
                    "total": None,
                    "pool": None,
                    "price": None
                }

                for i, h in enumerate(header):
                    if "unit" in h and "blok" in h:
                        col["unit"] = i
                    if "bed" in h:
                        col["beds"] = i
                    if "bath" in h:
                        col["baths"] = i
                    if "internal" in h:
                        col["internal"] = i
                    if "veranda" in h:
                        col["veranda"] = i
                    if "total" in h:
                        col["total"] = i
                    if "pool" in h:
                        col["pool"] = i
                    if "price" in h:
                        col["price"] = i

                # Parse table rows
                for row in table[1:]:
                    if not row:
                        continue

                    unit_raw = str(row[col["unit"]] if col["unit"] is not None else "").strip()

                    # Detect block headers line "Block L"
                    if unit_raw.lower().startswith("block"):
                        current_block = unit_raw.replace("Block", "").strip()
                        continue

                    # Skip empty or invalid lines
                    if not unit_raw:
                        continue

                    # Determine unit type: Block or Villa
                    if is_block_unit(unit_raw):
                        block_letter = re.match(r"([A-Z]+)", unit_raw).group(1)
                        number = re.match(r"[A-Z]+([0-9]+)", unit_raw).group(1)
                        code = f"{block_letter}-{number}".upper()

                    elif is_villa_unit(unit_raw):
                        code = f"Villa-{unit_raw}"
                        block_letter = "Villa"

                    else:
                        continue

                    # Extract values
                    beds = safe_float(row[col["beds"]]) if col["beds"] is not None else None
                    baths = safe_float(row[col["baths"]]) if col["baths"] is not None else None
                    internal = safe_float(row[col["internal"]]) if col["internal"] is not None else None
                    veranda = safe_float(row[col["veranda"]]) if col["veranda"] is not None else None
                    total_area = safe_float(row[col["total"]]) if col["total"] is not None else None
                    pool_raw = row[col["pool"]] if col["pool"] is not None else ""
                    price_raw = row[col["price"]] if col["price"] is not None else ""

                    row_text = " ".join([str(x) for x in row])

                    status = detect_status(row_text)
                    price = extract_price(price_raw)

                    pool_raw_lower = str(pool_raw).strip().lower()

                    if "communal" in pool_raw_lower:
                        pool = "communal"
                    elif "private" in pool_raw_lower:
                        pool = "private"
                    elif "both" in pool_raw_lower:
                        pool = "both"
                    else:
                        pool = "none"


                    unit_data = {
                        "project": None,  # filled later
                        "code": code,
                        "unit_type": "apartment" if block_letter != "Villa" else "house",
                        "bedrooms": int(beds or 0),
                        "bathrooms": int(baths or 1),
                        "area_internal": internal,
                        "area_veranda": veranda,
                        "area_total": total_area,
                        "price": price,
                        "currency": "EUR",
                        "vat_included": False,
                        "status": status,
                        "floor": block_letter,
                        "plot": "none",
                        "plot_area": None,
                        "veranda": "private" if veranda else "none",
                        "veranda_area": veranda,
                        "pool": pool,
                        "pool_area": None,
                        "is_published": False
                    }

                    all_data[current_project].append(unit_data)

    return all_data


# ===========================================================
# MAIN IMPORT
# ===========================================================
def import_pdf(pdf_path):
    projects = parse_pdf(pdf_path)

    print("\n==============================")
    print("  STARTING IMPORT")
    print("==============================")

    for project_name, units in projects.items():
        print(f"\n--- PROJECT: {project_name} --- ({len(units)} units found)")
        pid = create_project(project_name)
        if not pid:
            continue

        for unit in units:
            unit["project"] = pid
            create_unit(pid, unit)

    print("\n==============================")
    print("   IMPORT COMPLETE")
    print("==============================\n")


# RUN SCRIPT
if __name__ == "__main__":
    import_pdf("FullPricelist_B-1.pdf")
