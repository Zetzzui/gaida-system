"""
ml_classifier.py
----------------
ML-based intent classifier for GAIDA system.
Trains and compares Logistic Regression, Random Forest, and Neural Network
on the anxiety_training.jsonl dataset.

Usage:
    from app.services.ml_classifier import classify_intent

    result = classify_intent("I cant breathe")
    # returns: {"intent": "anxiety", "confidence": 0.87, "method": "ml"}
"""

import json
import pickle
import os
import warnings
warnings.filterwarnings('ignore')

from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix, classification_report
from sklearn.pipeline import Pipeline

from app.services.text_prep import STOPWORDS, preprocess

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent
TRAINING_DATA = BASE_DIR / "training" / "anxiety_training.jsonl"
MODEL_DIR = BASE_DIR / "training" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

BEST_MODEL_PATH = MODEL_DIR / "best_model.pkl"
LR_MODEL_PATH = MODEL_DIR / "lr_model.pkl"
RF_MODEL_PATH = MODEL_DIR / "rf_model.pkl"
NN_MODEL_PATH = MODEL_DIR / "nn_model.pkl"

# Cache loaded model in memory
_model = None


# ---------------------------------------------------------------------------
# Load dataset
# ---------------------------------------------------------------------------
def load_dataset():
    data = []
    with open(TRAINING_DATA, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    texts = [d["text"] for d in data]
    labels = [d["label"] for d in data]
    return texts, labels


# ---------------------------------------------------------------------------
# Build model pipelines
# ---------------------------------------------------------------------------
def build_pipelines():
    tfidf_params = {
        "ngram_range": (1, 2),
        "max_features": 5000,
        "sublinear_tf": True,
        "preprocessor": preprocess,
        "stop_words": sorted(STOPWORDS),
    }
    return {
        "Logistic Regression": Pipeline([
            ("tfidf", TfidfVectorizer(**tfidf_params)),
            ("clf", LogisticRegression(
                max_iter=1000, C=1.0, random_state=42,
                class_weight="balanced",
            )),
        ]),
        "Random Forest": Pipeline([
            ("tfidf", TfidfVectorizer(**tfidf_params)),
            ("clf", RandomForestClassifier(
                n_estimators=200, random_state=42,
                class_weight="balanced_subsample",
            )),
        ]),
        "Neural Network": Pipeline([
            ("tfidf", TfidfVectorizer(**tfidf_params)),
            ("clf", MLPClassifier(
                hidden_layer_sizes=(256, 128, 64), max_iter=500,
                random_state=42,
            )),
        ]),
    }


# ---------------------------------------------------------------------------
# Train and compare all models
# ---------------------------------------------------------------------------
def train_and_compare():
    """
    Trains all 3 models, compares accuracy, saves the best one.
    Returns a comparison report dict.
    """
    print("Loading dataset...")
    texts, labels = load_dataset()
    print(f"Total examples: {len(texts)}")

    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels
    )

    pipelines = build_pipelines()
    results = {}

    for name, pipeline in pipelines.items():
        print(f"Training {name}...")
        pipeline.fit(X_train, y_train)
        y_pred = pipeline.predict(X_test)
        test_acc = accuracy_score(y_test, y_pred)
        macro_f1 = f1_score(y_test, y_pred, average="macro", zero_division=0)
        cv_acc = cross_val_score(pipeline, texts, labels, cv=5).mean()
        report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)

        results[name] = {
            "test_accuracy": round(test_acc * 100, 2),
            "macro_f1": round(macro_f1 * 100, 2),
            "cv_accuracy": round(cv_acc * 100, 2),
            "classification_report": report,
            "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
            "pipeline": pipeline,
        }

        suicidal_recall = round(report.get("suicidal", {}).get("recall", 0) * 100, 2)
        print(f"  {name}: Test Acc={test_acc*100:.2f}% | Macro-F1={macro_f1*100:.2f}% "
              f"| Suicidal Recall={suicidal_recall}% | CV={cv_acc*100:.2f}%")

    # Save all models
    model_paths = {
        "Logistic Regression": LR_MODEL_PATH,
        "Random Forest": RF_MODEL_PATH,
        "Neural Network": NN_MODEL_PATH,
    }
    for name, path in model_paths.items():
        with open(path, "wb") as f:
            pickle.dump(results[name]["pipeline"], f)

    # Pick best by macro-F1 (balanced across all classes, not just accuracy)
    best_name = max(results, key=lambda n: results[n]["macro_f1"])
    best_pipeline = results[best_name]["pipeline"]

    with open(BEST_MODEL_PATH, "wb") as f:
        pickle.dump(best_pipeline, f)

    print(f"\n[OK] Best model: {best_name} (Macro-F1={results[best_name]['macro_f1']}%)")
    print(f"   Saved to: {BEST_MODEL_PATH}")

    return {
        "best_model": best_name,
        "results": {
            name: {
                "test_accuracy": r["test_accuracy"],
                "macro_f1": r["macro_f1"],
                "cv_accuracy": r["cv_accuracy"],
                "suicidal_recall": round(
                    r["classification_report"].get("suicidal", {}).get("recall", 0) * 100, 2
                ),
            }
            for name, r in results.items()
        }
    }


# ---------------------------------------------------------------------------
# Load all 3 models
# ---------------------------------------------------------------------------
_models = {}

def _load_all_models():
    global _models
    if not _models:
        model_paths = {
            "Logistic Regression": LR_MODEL_PATH,
            "Random Forest": RF_MODEL_PATH,
            "Neural Network": NN_MODEL_PATH,
        }
        missing = [name for name, path in model_paths.items() if not path.exists()]
        if missing:
            print(f"Missing models: {missing}. Training now...")
            train_and_compare()

        # Load all 3 models — NN included so the first reply doesn't pay a loading penalty
        for name in ["Logistic Regression", "Random Forest", "Neural Network"]:
            path = model_paths[name]
            if path.exists():
                with open(path, "rb") as f:
                    _models[name] = pickle.load(f)
                print(f"[GAIDA] Loaded {name}")

    return _models


def _load_nn_if_needed():
    """Load Neural Network only when needed — keeps startup fast."""
    global _models
    if "Neural Network" not in _models:
        if NN_MODEL_PATH.exists():
            print("[GAIDA] Loading Neural Network (first use)...")
            with open(NN_MODEL_PATH, "rb") as f:
                _models["Neural Network"] = pickle.load(f)
            print("[GAIDA] Neural Network loaded.")
        else:
            print("[GAIDA] Neural Network model not found — retraining...")
            train_and_compare()
            with open(NN_MODEL_PATH, "rb") as f:
                _models["Neural Network"] = pickle.load(f)
    return _models


# ---------------------------------------------------------------------------
# classify_intent — runs ALL 3 models, uses majority vote
# This is what virtual_agent.py calls
# ---------------------------------------------------------------------------
def classify_intent(text: str) -> dict:
    """
    Classifies a message using ALL 3 trained ML models.
    Uses majority vote to determine final intent.
    If tie, uses Logistic Regression as tiebreaker (highest accuracy).

    Returns:
        {
            "intent": str,          ← majority vote result
            "confidence": float,    ← average confidence of agreeing models
            "method": "ml",
            "all_predictions": {    ← all 3 model predictions for transparency
                "Logistic Regression": {"intent": str, "confidence": float},
                "Random Forest": {"intent": str, "confidence": float},
                "Neural Network": {"intent": str, "confidence": float},
            },
            "votes": {intent: count}  ← how many models agreed
        }
    """
    try:
        _load_all_models()       # loads LR + RF at startup
        _load_nn_if_needed()     # loads NN on first use
        models = _models
        predictions = {}


        for name, model in models.items():
            intent = model.predict([text])[0]
            proba = model.predict_proba([text])[0]
            confidence = round(float(max(proba)), 3)
            predictions[name] = {
                "intent": intent,
                "confidence": confidence,
            }

        # Count votes per intent
        from collections import Counter
        vote_counts = Counter(p["intent"] for p in predictions.values())
        
        # Majority vote — most common intent wins
        majority_intent = vote_counts.most_common(1)[0][0]

        # If tie (all 3 different) — use Logistic Regression as tiebreaker
        if vote_counts.most_common(1)[0][1] == 1:
            majority_intent = predictions["Logistic Regression"]["intent"]

        # Average confidence of models that agreed with majority
        agreeing_confidences = [
            p["confidence"] for p in predictions.values()
            if p["intent"] == majority_intent
        ]
        avg_confidence = round(sum(agreeing_confidences) / len(agreeing_confidences), 3)

        CONFIDENCE_THRESHOLD = 0.55

        if avg_confidence < CONFIDENCE_THRESHOLD:
            return {
                "intent": "uncertain",
                "confidence": avg_confidence,
                "method": "ml_low_confidence",
                "all_predictions": predictions,
                "votes": dict(vote_counts),
            }

        return {
            "intent": majority_intent,
            "confidence": avg_confidence,
            "method": "ml",
            "all_predictions": predictions,
            "votes": dict(vote_counts),
        }

    except Exception as e:
        print(f"ML classifier error: {e}")
        return {
            "intent": "neutral",
            "confidence": 0.3,
            "method": "ml_fallback",
            "all_predictions": {},
            "votes": {},
        }


# ---------------------------------------------------------------------------
# classify_intent_all — returns all 3 predictions separately
# Useful for showing panel the comparison per message
# ---------------------------------------------------------------------------
def classify_intent_all(text: str) -> dict:
    """
    Returns predictions from all 3 models separately.
    Use this for panel demonstration / comparison report.
    """
    try:
        _load_all_models()
        _load_nn_if_needed()
        models = _models
        results = {}
        
        for name, model in models.items():
            intent = model.predict([text])[0]
            proba = model.predict_proba([text])[0]
            confidence = round(float(max(proba)), 3)
            results[name] = {
                "intent": intent,
                "confidence": confidence,
            }
        return results
    except Exception as e:
        print(f"Error: {e}")
        return {}


# ---------------------------------------------------------------------------
# Run this file directly to train and compare models
# python ml_classifier.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    report = train_and_compare()
    print("\n=== FINAL COMPARISON ===")
    print(f"{'Model':<25} {'Test Acc':>9} {'Macro-F1':>10} {'CV Acc':>9} {'Suicidal Recall':>16}")
    print("-" * 75)
    for name, r in report["results"].items():
        print(f"{name:<25} {r['test_accuracy']:>8}% {r['macro_f1']:>8}% {r['cv_accuracy']:>8}% "
              f"{r['suicidal_recall']:>14}%")
    print(f"\nBest: {report['best_model']} (by macro-F1)")

    # Demo classify_intent with all 3
    print("\n=== DEMO: ALL 3 MODELS ON SAMPLE MESSAGES ===\n")
    test_msgs = [
        "I cant breathe",
        "im so stressed",
        "I want to kill myself",
        "hello",
        "I feel so alone",
        "I failed my exam",
        "i think im going crazy"
    ]
    for msg in test_msgs:
        result = classify_intent(msg)
        print(f"Message: '{msg}'")
        print(f"  Final (majority vote): {result['intent']} ({result['confidence']})")
        for model_name, pred in result["all_predictions"].items():
            print(f"  {model_name:<25}: {pred['intent']} ({pred['confidence']})")
        print()