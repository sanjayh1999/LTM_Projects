import certifi
import os
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

import requests
import pandas as pd
import time

# Make/model pairs — we'll pull multiple years for each
VEHICLE_MODELS = [
    ("honda", "civic"), ("honda", "accord"), ("honda", "cr-v"),
    ("toyota", "camry"), ("toyota", "corolla"), ("toyota", "rav4"),
    ("hyundai", "elantra"), ("hyundai", "sonata"), ("hyundai", "tucson"),
    ("ford", "f-150"), ("ford", "escape"), ("ford", "explorer"),
    ("chevrolet", "malibu"), ("chevrolet", "equinox"),
    ("nissan", "altima"), ("nissan", "rogue"),
    ("kia", "optima"), ("kia", "sportage"),
    ("volkswagen", "jetta"), ("subaru", "outback"),
]

YEARS = [2017, 2018, 2019, 2020, 2021, 2022, 2023]

BASE_URL = "https://api.nhtsa.gov/complaints/complaintsByVehicle"
OUTPUT_DIR = "data/raw/nhtsa"

def fetch_complaints(make, model, year):
    params = {"make": make, "model": model, "modelYear": year}
    resp = requests.get(BASE_URL, params=params, timeout=15, verify=False)
    resp.raise_for_status()
    return resp.json().get("results", [])

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    all_rows = []

    for make, model in VEHICLE_MODELS:
        for year in YEARS:
            print(f"Fetching {make} {model} {year}...")
            try:
                results = fetch_complaints(make, model, year)
                print(f"  -> {len(results)} complaints")
                all_rows.extend(results)
            except Exception as e:
                print(f"  !! failed: {e}")
            time.sleep(0.5)  # be polite to the API

    df = pd.DataFrame(all_rows)
    out_path = os.path.join(OUTPUT_DIR, "nhtsa_complaints.csv")
    df.to_csv(out_path, index=False)
    print(f"\nSaved {len(df)} total complaints to {out_path}")

if __name__ == "__main__":
    main()