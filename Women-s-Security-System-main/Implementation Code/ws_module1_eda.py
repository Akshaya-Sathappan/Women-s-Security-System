"""Module 1: Exploratory analysis of a city's crime data.

Run:  python ws_module1_eda.py                         (bundled Chennai case study)
      python ws_module1_eda.py --data my_city.csv      (any city with the same columns)
Plots are written to the outputs/ folder.
"""
import argparse

import matplotlib

matplotlib.use("Agg")  # write plots to files; no display needed

import matplotlib.pyplot as plt
import seaborn as sns

from crime_data import CRIME_COLUMNS, add_data_args, load_from_args, save_figure


def plot_crime_distributions(data):
    fig, axes = plt.subplots(nrows=2, ncols=2, figsize=(14, 10))
    colors = ["blue", "red", "green", "orange"]
    for ax, column, color in zip(axes.flat, CRIME_COLUMNS, colors):
        sns.histplot(data=data, x=column, kde=True, ax=ax, color=color).set_title(f"Distribution of {column}")
    fig.tight_layout()
    save_figure(fig, "module1_crime_distributions.png")


def plot_spatial_distribution(data):
    # Longitude on x, latitude on y, like a map
    fig, ax = plt.subplots(figsize=(12, 8))
    sns.scatterplot(data=data, x="Long", y="Lat", hue="Total_Crimes", palette="viridis",
                    size="Total_Crimes", sizes=(20, 200), alpha=0.7, ax=ax)
    ax.set_title("Spatial Distribution of Crimes")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    save_figure(fig, "module1_spatial_distribution.png")


def plot_total_crimes(data):
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.histplot(data=data, x="Total_Crimes", kde=True, color="orange", ax=ax).set_title("Distribution of Total Crimes")
    fig.tight_layout()
    save_figure(fig, "module1_total_crimes.png")


def main():
    parser = argparse.ArgumentParser(description="Exploratory analysis of a city's crime data")
    add_data_args(parser)
    args = parser.parse_args()

    sns.set_style("whitegrid")
    data = load_from_args(args)

    print("\nFirst rows:")
    print(data.head())
    print("\nSummary statistics:")
    print(data.describe())
    print()

    plot_crime_distributions(data)
    plot_spatial_distribution(data)
    plot_total_crimes(data)


if __name__ == "__main__":
    main()
