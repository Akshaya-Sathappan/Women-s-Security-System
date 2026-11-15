"""Module 2: Classifying locations as safe or unsafe.

Run:  python ws_module2_models.py            (all models, including the neural network)
      python ws_module2_models.py --no-nn    (skip the neural network / TensorFlow)
Confusion matrices and training curves are written to the outputs/ folder.

Labels: a location is unsafe (1) if its total crime count is above the median, otherwise safe (0).

Features: Lat and Long only. An earlier version also used Total_Crimes as a feature. The label
is computed directly from Total_Crimes, so the model only had to learn "is this number above the
median?", which is why it scored 100%. The individual crime columns leak the label the same way,
because they add up to Total_Crimes. The useful question is whether a location alone predicts how
unsafe it is, because that is the only information the app has about a new place.

Result: once the leak is removed, none of the models do much better than the majority-class
baseline. In this dataset (under 100 valid points) location alone is a weak predictor. The test
split is only about 24 rows, so cross-validated accuracy is the more reliable comparison. To
improve this: fix the geocoding so dropped rows can be used, collect more data, and add real
location features (distance to the nearest police station, lighting, footfall) instead of raw
coordinates.
"""
import argparse

import matplotlib

matplotlib.use("Agg")  # write plots to files; no display needed

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, classification_report, confusion_matrix,
                             f1_score, precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

from crime_data import OUTPUT_DIR, load_clean_data, save_figure

RANDOM_STATE = 42


def plot_confusion_matrix(name, y_true, y_pred):
    fig, ax = plt.subplots(figsize=(6, 4))
    sns.heatmap(confusion_matrix(y_true, y_pred), annot=True, fmt="g", cmap="Blues", ax=ax)
    ax.set_title(f"{name} Confusion Matrix")
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    save_figure(fig, f"module2_confusion_{name.lower().replace(' ', '_')}.png")


CV_SCORING = ["accuracy", "precision", "recall", "f1", "roc_auc"]


def test_metrics(y_true, y_pred, y_score):
    """Metrics on the held-out test split. 'Unsafe' (1) is the positive class."""
    return {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "roc_auc": roc_auc_score(y_true, y_score),
    }


def evaluate(name, model, X, y, X_train, X_test, y_train, y_test, cv):
    """Fit on the train split, report test metrics and 5-fold cross-validated metrics."""
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    y_score = model.predict_proba(X_test)[:, 1]
    metrics = {f"test_{k}": v for k, v in test_metrics(y_test, y_pred, y_score).items()}

    cv_results = cross_validate(model, X, y, cv=cv, scoring=CV_SCORING)
    for metric in CV_SCORING:
        metrics[f"cv_{metric}"] = cv_results[f"test_{metric}"].mean()
        metrics[f"cv_{metric}_std"] = cv_results[f"test_{metric}"].std()

    print(f"\n=== {name} ===")
    print(f"Test accuracy {metrics['test_accuracy']:.2%}, F1 {metrics['test_f1']:.2f}, ROC-AUC {metrics['test_roc_auc']:.2f}")
    print(f"5-fold CV accuracy {metrics['cv_accuracy']:.2%} ± {metrics['cv_accuracy_std']:.2%}, "
          f"F1 {metrics['cv_f1']:.2f}, ROC-AUC {metrics['cv_roc_auc']:.2f}")
    print(classification_report(y_test, y_pred, target_names=["safe", "unsafe"], zero_division=0))
    plot_confusion_matrix(name, y_test, y_pred)
    return metrics


def train_neural_network(X_train, X_test, y_train, y_test):
    import keras
    from keras import layers

    keras.utils.set_random_seed(RANDOM_STATE)

    # Neural networks need scaled inputs; fit the scaler on the training data only
    scaler = StandardScaler().fit(X_train)
    X_train_s, X_test_s = scaler.transform(X_train), scaler.transform(X_test)

    model = keras.Sequential([
        keras.Input(shape=(X_train.shape[1],)),
        layers.Dense(10, activation="relu"),
        layers.Dense(5, activation="relu"),
        layers.Dense(1, activation="sigmoid"),
    ])
    model.compile(loss="binary_crossentropy", optimizer="adam", metrics=["accuracy"])
    history = model.fit(X_train_s, y_train, epochs=100, batch_size=10,
                        validation_data=(X_test_s, y_test), verbose=0)

    y_score = model.predict(X_test_s, verbose=0).ravel()
    y_pred = (y_score > 0.5).astype("int32")
    metrics = {f"test_{k}": v for k, v in test_metrics(y_test, y_pred, y_score).items()}
    print("\n=== Neural Network ===")
    print(f"Test accuracy {metrics['test_accuracy']:.2%}, F1 {metrics['test_f1']:.2f}, ROC-AUC {metrics['test_roc_auc']:.2f}")
    print(classification_report(y_test, y_pred, target_names=["safe", "unsafe"], zero_division=0))
    plot_confusion_matrix("Neural Network", y_test, y_pred)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    ax1.plot(history.history["accuracy"], label="Training Accuracy")
    ax1.plot(history.history["val_accuracy"], label="Validation Accuracy")
    ax1.set_title("Neural Network Training and Validation Accuracy")
    ax1.set_xlabel("Epochs")
    ax1.set_ylabel("Accuracy")
    ax1.legend()
    ax2.plot(history.history["loss"], label="Training Loss")
    ax2.plot(history.history["val_loss"], label="Validation Loss")
    ax2.set_title("Neural Network Training and Validation Loss")
    ax2.set_xlabel("Epochs")
    ax2.set_ylabel("Loss")
    ax2.legend()
    fig.tight_layout()
    save_figure(fig, "module2_nn_training.png")

    # Cross-validating the network would mean retraining it 5 times; skipped for speed.
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-nn", action="store_true", help="skip the neural network (no TensorFlow needed)")
    args = parser.parse_args()

    np.random.seed(RANDOM_STATE)
    sns.set_style("whitegrid")
    data = load_clean_data()

    median_crimes = data["Total_Crimes"].median()
    data["Label"] = (data["Total_Crimes"] > median_crimes).astype(int)
    X = data[["Lat", "Long"]]
    y = data["Label"]
    print(y.value_counts().rename({0: "safe", 1: "unsafe"}).to_string())

    # Stratified split keeps the safe/unsafe ratio the same in train and test.
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, stratify=y, random_state=RANDOM_STATE)
    # The dataset is small, so a single split is noisy; also report 5-fold cross-validation.
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    split = (X, y, X_train, X_test, y_train, y_test, cv)

    models = {
        # Always predicts the most common class. A model is only useful if it beats this.
        "Baseline": DummyClassifier(strategy="most_frequent"),
        "Logistic Regression": make_pipeline(StandardScaler(), LogisticRegression()),
        # Depth is limited to reduce overfitting on such a small dataset.
        "Decision Tree": DecisionTreeClassifier(max_depth=3, random_state=RANDOM_STATE),
    }
    results = {name: evaluate(name, model, *split) for name, model in models.items()}

    if not args.no_nn:
        results["Neural Network"] = train_neural_network(X_train, X_test, y_train, y_test)

    summary = pd.DataFrame(results).T
    summary.index.name = "model"
    OUTPUT_DIR.mkdir(exist_ok=True)
    summary.to_csv(OUTPUT_DIR / "module2_metrics.csv", float_format="%.4f")
    print(f"\nSaved outputs/module2_metrics.csv")

    columns = {
        "test_accuracy": "Test acc", "test_precision": "Test prec", "test_recall": "Test recall",
        "test_f1": "Test F1", "test_roc_auc": "Test AUC",
        "cv_accuracy": "CV acc", "cv_f1": "CV F1", "cv_roc_auc": "CV AUC",
    }
    table = summary.reindex(columns=list(columns)).rename(columns=columns)
    print("\n=== Comparison (unsafe = positive class) ===")
    print(table.map(lambda v: "n/a" if pd.isna(v) else f"{v:.2f}").to_string())


if __name__ == "__main__":
    main()
