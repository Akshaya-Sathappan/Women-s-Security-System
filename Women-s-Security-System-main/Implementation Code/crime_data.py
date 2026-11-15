"""Shared loading and cleaning for city crime datasets (used by Module 1 and Module 2).

Any city works, as long as the file (.xlsx or .csv) has these columns:
    Lat, Long, Theft, Robbery, Assault, Harassment
The bundled crime_data.xlsx is a case study of 150 locations in Chennai, India.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_PATH = BASE_DIR / "crime_data.xlsx"
OUTPUT_DIR = BASE_DIR / "outputs"

CRIME_COLUMNS = ["Theft", "Robbery", "Assault", "Harassment"]
REQUIRED_COLUMNS = ["Lat", "Long"] + CRIME_COLUMNS

# Without --bbox, rows farther than this from the dataset's median point are treated as
# bad geocodes. 50 km covers a large metro area; mis-geocoded rows are usually much farther.
DEFAULT_RADIUS_KM = 50.0


def add_data_args(parser: argparse.ArgumentParser) -> None:
    """Add the shared --data / --bbox / --radius-km options to a script's parser."""
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH,
                        help="crime dataset (.xlsx or .csv); default: the bundled Chennai case study")
    parser.add_argument("--bbox", type=parse_bbox, metavar="MIN_LAT,MAX_LAT,MIN_LONG,MAX_LONG",
                        help="keep only rows inside this box (overrides --radius-km)")
    parser.add_argument("--radius-km", type=float, default=DEFAULT_RADIUS_KM,
                        help=f"keep rows within this distance of the median location (default {DEFAULT_RADIUS_KM:g})")


def parse_bbox(text: str):
    try:
        min_lat, max_lat, min_long, max_long = (float(v) for v in text.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError("--bbox needs four numbers: MIN_LAT,MAX_LAT,MIN_LONG,MAX_LONG")
    if min_lat >= max_lat or min_long >= max_long:
        raise argparse.ArgumentTypeError("--bbox minimums must be smaller than maximums")
    return min_lat, max_lat, min_long, max_long


def _distance_km(lat, long, lat0, long0):
    """Great-circle (haversine) distance in km."""
    lat, long, lat0, long0 = map(np.radians, (lat, long, lat0, long0))
    a = np.sin((lat - lat0) / 2) ** 2 + np.cos(lat0) * np.cos(lat) * np.sin((long - long0) / 2) ** 2
    return 2 * 6371 * np.arcsin(np.sqrt(a))


def load_clean_data(path: Path = DEFAULT_DATA_PATH, bbox=None, radius_km: float = DEFAULT_RADIUS_KM,
                    verbose: bool = True) -> pd.DataFrame:
    """Load a crime dataset, fill missing values, drop bad geocodes and add Total_Crimes."""
    path = Path(path)
    if not path.exists():
        raise SystemExit(f"Data file not found: {path}")
    data = pd.read_csv(path) if path.suffix.lower() == ".csv" else pd.read_excel(path)

    missing = [c for c in REQUIRED_COLUMNS if c not in data.columns]
    if missing:
        raise SystemExit(f"{path.name} is missing required columns: {', '.join(missing)}")

    # 'Unnamed: 0' is a leftover index column from an earlier export
    data = data.drop(columns=["Unnamed: 0"], errors="ignore")

    # Fill missing numeric values with the column median. Only numeric columns are used,
    # because data.median() fails on text columns (such as Address) in pandas 2.
    numeric_columns = data.select_dtypes(include="number").columns
    data[numeric_columns] = data[numeric_columns].fillna(data[numeric_columns].median())

    # Drop rows whose coordinates are outside the city (bad geocodes)
    if bbox:
        min_lat, max_lat, min_long, max_long = bbox
        keep = data["Lat"].between(min_lat, max_lat) & data["Long"].between(min_long, max_long)
        area = f"the box {bbox}"
    else:
        lat0, long0 = data["Lat"].median(), data["Long"].median()
        keep = _distance_km(data["Lat"], data["Long"], lat0, long0) <= radius_km
        area = f"{radius_km:g} km of the median location ({lat0:.4f}, {long0:.4f})"
    if verbose:
        print(f"Loaded {len(data)} rows from {path.name}")
        print(f"Dropping {(~keep).sum()} rows outside {area}")
    data = data[keep].reset_index(drop=True)
    if len(data) < 10:
        raise SystemExit(f"Only {len(data)} rows left after filtering; check --bbox / --radius-km")

    data["Total_Crimes"] = data[CRIME_COLUMNS].sum(axis=1)
    return data


def load_from_args(args: argparse.Namespace) -> pd.DataFrame:
    return load_clean_data(args.data, bbox=args.bbox, radius_km=args.radius_km)


def save_figure(fig, name: str) -> Path:
    """Save a matplotlib figure into the outputs/ folder and close it."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / name
    fig.savefig(path, dpi=120, bbox_inches="tight")
    fig.clf()
    print(f"Saved {path.relative_to(BASE_DIR)}")
    return path
