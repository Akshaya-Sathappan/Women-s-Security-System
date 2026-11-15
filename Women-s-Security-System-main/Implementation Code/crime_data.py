"""Shared loading and cleaning for the Chennai crime dataset (used by Module 1 and Module 2)."""
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "chennai_data.xlsx"
OUTPUT_DIR = BASE_DIR / "outputs"

CRIME_COLUMNS = ["Theft", "Robbery", "Assault", "Harassment"]

# Rough bounding box around Chennai. Many addresses in the raw file were geocoded
# far outside the city (some to other continents), so those coordinates are wrong.
CHENNAI_LAT = (12.7, 13.4)
CHENNAI_LONG = (79.9, 80.4)


def load_clean_data(path: Path = DATA_PATH, verbose: bool = True) -> pd.DataFrame:
    """Load the dataset, fill missing numeric values, drop bad geocodes and add Total_Crimes."""
    data = pd.read_excel(path)

    # 'Unnamed: 0' is a leftover index column from an earlier export
    data = data.drop(columns=["Unnamed: 0"], errors="ignore")

    # Fill missing numeric values with the column median. Only numeric columns are used,
    # because data.median() fails on the text Address column in pandas 2.
    numeric_columns = data.select_dtypes(include="number").columns
    data[numeric_columns] = data[numeric_columns].fillna(data[numeric_columns].median())

    in_chennai = data["Lat"].between(*CHENNAI_LAT) & data["Long"].between(*CHENNAI_LONG)
    if verbose:
        print(f"Dropping {(~in_chennai).sum()} of {len(data)} rows geocoded outside Chennai")
    data = data[in_chennai].reset_index(drop=True)

    data["Total_Crimes"] = data[CRIME_COLUMNS].sum(axis=1)
    return data


def save_figure(fig, name: str) -> Path:
    """Save a matplotlib figure into the outputs/ folder and close it."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / name
    fig.savefig(path, dpi=120, bbox_inches="tight")
    fig.clf()
    print(f"Saved {path.relative_to(BASE_DIR)}")
    return path
