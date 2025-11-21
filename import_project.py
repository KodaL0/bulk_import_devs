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

ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzYzNzI4NzgzLCJpYXQiOjE3NjM3MTQzODMsImp0aSI6ImUyNjA1MjE2YjZmNTQ5MTFhYjBhMzYyN2Q4ZjY1MDNkIiwidXNlcl9pZCI6MTJ9.DfO4NGulNL9dG8iG0WscVuOa8blafCS0ci6rALx8dRU"

ALLOWED_PROJECTS = {
    "Marelia Valley",
    "Michelle Park",
    "TM BOUTIQUE",
    "The Pearl",
    "Business Centre (MBC)",
    "Golden Hills",
    "Infinity",
    "Elite Residences",
    "Adonidos Gardens",
    "Panorama Apartments",
}

# ===========================================================
# API HELPERS
# ===========================================================
def api_get(endpoint):
    url = f"{BASE_URL}/{endpoint.strip('/')}/"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    return SESSION.get(url, headers=headers)


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


def project_exists(name):
    """Check server for existing projects; avoid duplicates."""
    r = api_get("projects")
    if r.status_code != 200:
        print("[WARNING] Could not fetch existing projects.")
        return False

    for p in r.json():
        if p["name"].strip().lower() == name.strip().lower():
            print(f"[FOUND EXISTING PROJECT] {name} → ID {p['id']}")
            return p["id"]

    return False


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
        "is_published": False,
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
    r = api_post("units", json.dumps(unit))

    if r.status_code == 201:
        print(f"   → UNIT CREATED: {unit['code']}")
    else:
        print(f"[UNIT FAILED] {unit['code']} → {r.status_code}: {r.text}")


# ===========================================================
# HELPERS
# ===========================================================
HEADER_SKIP_WORDS = {
    "block",
    "first floor",
    "second floor",
    "third floor",
    "entire building",
    "building",
    "unit",
    "units",
    "floor",
    "villa",  # villa alone is a header, not a unit
}

def should_skip_row(text):
    text = str(text).strip().lower()
    for w in HEADER_SKIP_WORDS:
        if text.startswith(w):
            return True
    return False


def clean_number(val):
    if val is None:
        return None
    txt = str(val).replace(",", "").replace("\n", " ").strip()
    digits = re.sub(r"[^0-9.]", "", txt)
    return float(digits) if digits else None


def detect_status(text):
    text = str(text).lower()
    if "sold" in text:
        return "sold"
    if "reserv" in text:
        return "reserved"
    return "available"


def extract_unit_code(raw):
    raw = str(raw).strip()

    # Skip header "Villa"
    if raw.lower() == "villa":
        return None

    # Villa with number
    if raw.lower().startswith("villa "):
        parts = raw.split()
        if len(parts) >= 2 and parts[1].isdigit():
            return f"Villa-{parts[1]}"
        return None

    # Penthouse
    if raw.lower().startswith("penthouse"):
        match = re.findall(r"[A-Z]?\d+", raw)
        return f"PH-{match[0]}" if match else None

    # Duplex
    if raw.lower().startswith("duplex"):
        match = re.findall(r"[A-Z]?\d+", raw)
        return match[0] if match else None

    # A101, B203
    if re.match(r"^[A-Z]\d{2,3}$", raw):
        return raw

    # 101 (single building)
    if raw.isdigit():
        return raw

    return raw if raw else None


# ===========================================================
# UNIVERSAL PDF PARSER
# ===========================================================
def parse_pdf(pdf_path):
    parsed = {}
    current_project = None
    seen_codes = {}

    with pdfplumber.open(pdf_path) as pdf:

        for page in pdf.pages:
            text = page.extract_text() or ""
            if not text.strip():
                continue

            lines = [l.strip() for l in text.split("\n") if l.strip()]
            if not lines:
                continue

            project_name = lines[0]

            if project_name in ALLOWED_PROJECTS:
                current_project = project_name
                if project_name not in parsed:
                    parsed[project_name] = []
                    seen_codes[project_name] = set()
                print(f"[PROJECT DETECTED] {project_name}")
            else:
                continue

            tables = page.extract_tables()
            if not tables:
                continue

            for table in tables:
                header = [
                    h.lower().strip() if h else "" for h in table[0]
                ]

                cols = {}
                for i, h in enumerate(header):
                    if "unit" in h:
                        cols["unit"] = i
                    if "bed" in h:
                        cols["beds"] = i
                    if "bath" in h:
                        cols["baths"] = i
                    if "internal" in h:
                        cols["internal"] = i
                    if "veranda" in h:
                        cols["veranda"] = i
                    if "total" in h:
                        cols["total"] = i
                    if "plot" in h:
                        cols["plot"] = i
                    if "pool" in h:
                        cols["pool"] = i
                    if "price" in h:
                        cols["price"] = i

                for row in table[1:]:
                    if not any(row):
                        continue

                    # Extract unit text
                    unit_cell = row[cols["unit"]] if "unit" in cols else None
                    if not unit_cell:
                        continue

                    if should_skip_row(unit_cell):
                        continue

                    code = extract_unit_code(unit_cell)
                    if not code:
                        continue

                    # Skip duplicates
                    if code in seen_codes[current_project]:
                        continue

                    seen_codes[current_project].add(code)

                    beds = clean_number(row[cols["beds"]]) if "beds" in cols else None
                    baths = clean_number(row[cols["baths"]]) if "baths" in cols else None
                    internal = clean_number(row[cols["internal"]]) if "internal" in cols else None
                    veranda = clean_number(row[cols["veranda"]]) if "veranda" in cols else None
                    total = clean_number(row[cols["total"]]) if "total" in cols else None
                    plot_area = clean_number(row[cols["plot"]]) if "plot" in cols else None
                    pool_raw = row[cols["pool"]] if "pool" in cols else ""
                    price = clean_number(row[cols["price"]]) if "price" in cols else None

                    # Pool fix (Option B)
                    pool_value = "none"
                    if isinstance(pool_raw, str):
                        pr = pool_raw.lower()
                        if "commun" in pr:
                            pool_value = "communal"
                        elif re.match(r"^[0-9.]+x[0-9.]+$", pr):
                            pool_value = "private"
                    else:
                        pool_value = "none"

                    status = detect_status(" ".join(str(c) for c in row))

                    unit_data = {
                        "project": None,
                        "code": code,
                        "unit_type": "house" if code.startswith("Villa") else "apartment",
                        "bedrooms": int(beds or 0),
                        "bathrooms": int(baths or 1),
                        "area_internal": internal,
                        "area_veranda": veranda,
                        "area_total": total,
                        "price": price,
                        "currency": "EUR",
                        "vat_included": False,
                        "status": status,
                        "floor": "",
                        "plot": "",
                        "plot_area": plot_area,
                        "veranda": "private" if veranda else "none",
                        "veranda_area": veranda,
                        "pool": pool_value,
                        "pool_area": None,
                        "is_published": False,
                    }

                    parsed[current_project].append(unit_data)

    return parsed


# ===========================================================
# MAIN IMPORT
# ===========================================================
def import_pdf(pdf_path):
    projects = parse_pdf(pdf_path)

    for project_name, units in projects.items():

        print(f"\n=====================================================")
        print(f" PROJECT: {project_name}   ({len(units)} units found)")
        print(f"=====================================================")

        existing = project_exists(project_name)
        if existing:
            print(f"[SKIP] Project already exists — will not create duplicate.")
            continue

        new_id = create_project(project_name)
        if not new_id:
            continue

        for unit in units:
            unit["project"] = new_id
            create_unit(new_id, unit)

    print("\n================ IMPORT COMPLETE ================")


# ===========================================================
# RUN SCRIPT
# ===========================================================
if __name__ == "__main__":
    import_pdf("FullPricelist_B-1.pdf")
