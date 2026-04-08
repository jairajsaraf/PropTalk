"""Generate synthetic sample data for the Property Data Explorer demo.

This script creates realistic-looking but entirely synthetic property data.
No proprietary data is used or included. Run this once after cloning:

    python generate_sample_data.py

CSVs are written to sample_data/ (gitignored).
"""

import os
import numpy as np
import pandas as pd

np.random.seed(42)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "sample_data")
N_DEED = 5000
N_HAR = 5000

# ---------------------------------------------------------------------------
# City / geography configuration
# ---------------------------------------------------------------------------

TEXAS_CITIES = {
    # city: (weight, county, zip_range, lat_range, lon_range)
    "HOUSTON":      (0.40, "HARRIS",    (77001, 77099), (29.70, 29.85), (-95.50, -95.25)),
    "DALLAS":       (0.15, "DALLAS",    (75201, 75299), (32.70, 32.85), (-96.85, -96.70)),
    "SAN ANTONIO":  (0.12, "BEXAR",     (78201, 78299), (29.38, 29.52), (-98.55, -98.40)),
    "AUSTIN":       (0.12, "TRAVIS",    (78701, 78799), (30.22, 30.35), (-97.80, -97.68)),
    "FORT WORTH":   (0.08, "TARRANT",   (76101, 76199), (32.70, 32.80), (-97.40, -97.25)),
    "PLANO":        (0.03, "COLLIN",    (75023, 75093), (33.00, 33.08), (-96.75, -96.68)),
    "FRISCO":       (0.02, "COLLIN",    (75033, 75035), (33.13, 33.18), (-96.84, -96.79)),
    "MCKINNEY":     (0.02, "COLLIN",    (75069, 75072), (33.18, 33.22), (-96.65, -96.60)),
    "ROUND ROCK":   (0.02, "WILLIAMSON",(78664, 78681), (30.50, 30.55), (-97.70, -97.65)),
    "EL PASO":      (0.02, "EL PASO",   (79901, 79999), (31.75, 31.82), (-106.48, -106.38)),
    "LUBBOCK":      (0.02, "LUBBOCK",   (79401, 79499), (33.52, 33.58), (-101.88, -101.80)),
}

HOUSTON_AREA_CITIES = {
    # city: (weight, zip_range, lat_range, lon_range)
    "Houston":      (0.50, (77001, 77099), (29.70, 29.85), (-95.50, -95.25)),
    "Katy":         (0.10, (77449, 77494), (29.75, 29.82), (-95.82, -95.72)),
    "Sugar Land":   (0.08, (77478, 77498), (29.58, 29.65), (-95.65, -95.58)),
    "The Woodlands": (0.08, (77380, 77389), (30.15, 30.22), (-95.52, -95.45)),
    "Pearland":     (0.07, (77581, 77588), (29.53, 29.58), (-95.30, -95.23)),
    "Spring":       (0.05, (77373, 77389), (30.05, 30.12), (-95.45, -95.38)),
    "Cypress":      (0.04, (77429, 77433), (29.95, 30.00), (-95.72, -95.65)),
    "League City":  (0.03, (77573, 77574), (29.48, 29.53), (-95.12, -95.05)),
    "Missouri City": (0.03, (77459, 77489), (29.55, 29.60), (-95.55, -95.48)),
    "Richmond":     (0.02, (77406, 77469), (29.58, 29.62), (-95.75, -95.70)),
}

STREET_NAMES = [
    "Main St", "Oak Dr", "Elm Ave", "Cedar Ln", "Maple Blvd", "Pine Rd",
    "Walnut St", "Birch Ct", "Willow Way", "Ash Dr", "Pecan Ln", "Hickory Ave",
    "Magnolia Blvd", "Cypress Dr", "Mesquite Rd", "Live Oak Ln", "Post Oak Blvd",
    "Westheimer Rd", "Memorial Dr", "Kirby Dr", "Shepherd Dr", "Heights Blvd",
    "Richmond Ave", "Bissonnet St", "Bellaire Blvd", "Fondren Rd", "Gessner Rd",
    "Beltway 8", "FM 1960", "Spring Cypress Rd",
]

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Christopher", "Karen", "Daniel", "Lisa", "Matthew", "Nancy",
    "Carlos", "Maria", "Jose", "Ana", "Luis", "Rosa", "Wei", "Min", "Raj", "Priya",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Chen",
    "Nguyen", "Patel", "Kim", "Singh",
]

LLC_NAMES = [
    "Lone Star Properties LLC", "Texas Realty Holdings LLC", "Gulf Coast Investments LLC",
    "Bluebonnet Capital LLC", "Sunrise Homes LLC", "Heritage Real Estate LLC",
    "Pinnacle Property Group LLC", "Keystone Acquisitions LLC", "Atlas Holdings LLC",
    "Vertex Capital Partners LLC", "Horizon Realty LLC", "Summit Investment Group LLC",
    "Ironwood Properties LLC", "Meridian Homes LLC", "Catalyst Real Estate LLC",
]

INVESTOR_CLASSES = ["not_an_investor", "small_investor", "medium_investor", "large_investor", "mega_investor"]
INVESTOR_WEIGHTS = [0.65, 0.15, 0.10, 0.07, 0.03]


def _random_name(rng: np.random.RandomState) -> str:
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def generate_deed_transactions() -> pd.DataFrame:
    """Generate ~5000 synthetic deed transaction records."""
    rng = np.random.RandomState(42)

    cities = list(TEXAS_CITIES.keys())
    weights = [TEXAS_CITIES[c][0] for c in cities]
    chosen_cities = rng.choice(cities, size=N_DEED, p=weights)

    records = []
    for i in range(N_DEED):
        city = chosen_cities[i]
        _, county, zip_range, lat_range, lon_range = TEXAS_CITIES[city]

        # Investor classification
        inv_class = rng.choice(INVESTOR_CLASSES, p=INVESTOR_WEIGHTS)
        is_investor = inv_class != "not_an_investor"

        # Cash purchase — higher probability for investors
        cash_prob = 0.45 if is_investor else 0.18
        cash = "Y" if rng.random() < cash_prob else "N"

        # Corporate buyer — correlated with investor status
        corp_prob = 0.70 if inv_class in ("large_investor", "mega_investor") else (0.25 if is_investor else 0.08)
        corporate = "Y" if rng.random() < corp_prob else "N"

        # Buyer name
        if corporate == "Y":
            buyer = rng.choice(LLC_NAMES)
        else:
            buyer = _random_name(rng)

        # Sale amount — log-normal, median ~$280K
        sale_amount = round(float(rng.lognormal(mean=12.54, sigma=0.55)), 0)
        sale_amount = max(50000.0, min(sale_amount, 5000000.0))

        # Property type
        prop_code = 10 if rng.random() < 0.80 else rng.choice([11, 20, 21, 22, 24])

        # Occupancy
        occ = "T" if is_investor and rng.random() < 0.85 else ("T" if rng.random() < 0.15 else "S")

        # Date — uniform 2020-01-01 to 2025-12-31
        days_offset = rng.randint(0, 2192)  # ~6 years
        sale_date = pd.Timestamp("2020-01-01") + pd.Timedelta(days=int(days_offset))

        records.append({
            "CLIP": rng.randint(100000000000, 999999999999),
            "SITUS_STREET_ADDRESS": f"{rng.randint(100, 19999)} {rng.choice(STREET_NAMES)}",
            "SITUS_CITY": city,
            "SITUS_COUNTY": county,
            "SITUS_ZIP_CODE": str(rng.randint(zip_range[0], zip_range[1])),
            "PROPERTY_INDICATOR_CODE": prop_code,
            "SALE_AMOUNT": sale_amount,
            "SALE_DERIVED_DATE": sale_date,
            "INVESTOR_CLASSIFICATION_ENRICHED": inv_class,
            "INVESTOR_PURCHASE_INDICATOR_ENRICHED": "Y" if is_investor else "N",
            "CASH_PURCHASE_IND": cash,
            "BUYER_1_FULL_NAME": buyer,
            "BUYER_1_CORPORATE_IND": corporate,
            "BUYER_OCCUPANCY_CODE": occ,
            "SELLER_1_FULL_NAME": _random_name(rng),
            "parcel_level_latitude": round(rng.uniform(lat_range[0], lat_range[1]), 6),
            "parcel_level_longitude": round(rng.uniform(lon_range[0], lon_range[1]), 6),
        })

    return pd.DataFrame(records)


def generate_har_listings() -> pd.DataFrame:
    """Generate ~5000 synthetic HAR listing records."""
    rng = np.random.RandomState(43)

    cities = list(HOUSTON_AREA_CITIES.keys())
    weights = [HOUSTON_AREA_CITIES[c][0] for c in cities]
    chosen_cities = rng.choice(cities, size=N_HAR, p=weights)

    records = []
    for i in range(N_HAR):
        city = chosen_cities[i]
        _, zip_range, lat_range, lon_range = HOUSTON_AREA_CITIES[city]

        # Status
        status = rng.choice(["Closed", "Active", "Pending"], p=[0.60, 0.25, 0.15])

        # Property type
        prop_type = rng.choice(["Residential", "Townhouse", "Condominium"], p=[0.80, 0.12, 0.08])

        # Bedrooms and bathrooms
        bedrooms = int(rng.choice([1, 2, 3, 4, 5, 6], p=[0.03, 0.12, 0.35, 0.33, 0.12, 0.05]))
        bathrooms = min(bedrooms, max(1, bedrooms - int(rng.choice([0, 1], p=[0.6, 0.4]))))

        # Living area — correlated with bedrooms
        base_sqft = 600 + bedrooms * 450
        living_area = int(max(800, min(5000, rng.normal(base_sqft, 300))))

        # Year built — skewed toward 2000+
        year_built = int(max(1960, min(2025, rng.normal(2005, 12))))

        # List price — log-normal, median ~$320K
        list_price = round(float(rng.lognormal(mean=12.68, sigma=0.50)), 0)
        list_price = max(80000.0, min(list_price, 3000000.0))

        # Close price — slight discount/premium from list
        close_price = round(list_price * rng.uniform(0.94, 1.02), 0) if status == "Closed" else None

        # Days on market
        dom = int(max(1, min(180, rng.exponential(30))))

        # Dates
        listing_days_ago = rng.randint(0, 730)  # within ~2 years
        listing_date = pd.Timestamp("2023-01-01") + pd.Timedelta(days=int(listing_days_ago))
        close_date = listing_date + pd.Timedelta(days=int(dom)) if status == "Closed" else None

        records.append({
            "ListingId": f"HAR-{100000 + i}",
            "City": city,
            "ZipCode": str(rng.randint(zip_range[0], zip_range[1])),
            "ListPrice": list_price,
            "ClosePrice": close_price,
            "StandardStatus": status,
            "PropertyType": prop_type,
            "BedroomsTotal": bedrooms,
            "BathroomsTotalInteger": bathrooms,
            "LivingArea": living_area,
            "YearBuilt": year_built,
            "DaysOnMarket": dom,
            "ListingContractDate": listing_date,
            "CloseDate": close_date,
            "Latitude": round(rng.uniform(lat_range[0], lat_range[1]), 6),
            "Longitude": round(rng.uniform(lon_range[0], lon_range[1]), 6),
        })

    return pd.DataFrame(records)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Generating deed transactions...")
    deed_df = generate_deed_transactions()
    deed_path = os.path.join(OUTPUT_DIR, "deed_transactions_sample.csv")
    deed_df.to_csv(deed_path, index=False)
    print(f"  -> {deed_path} ({len(deed_df)} rows)")

    print("Generating HAR listings...")
    har_df = generate_har_listings()
    har_path = os.path.join(OUTPUT_DIR, "har_listings_sample.csv")
    har_df.to_csv(har_path, index=False)
    print(f"  -> {har_path} ({len(har_df)} rows)")

    print("Done!")


if __name__ == "__main__":
    main()
