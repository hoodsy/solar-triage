"""Train the student: a gradient-boosted tree committee over the per-day
feature vectors, learning from the rules' labels and the referee's audits.

Scope decisions, deliberate:
- data_gap rows are dropped — "can't see the day" is a deterministic
  coverage gate upstream, not something to learn.
- unclassified rows are excluded from training (teaching the model to
  reproduce ignorance helps nobody) and predicted afterward as analysis:
  each confident prediction there is a testable claim.
- sample weight = provenance x class balance: referee-audited days count
  GOLD_WEIGHT times a rule-labeled day (when teacher and answer key
  disagree, trust the answer key), and rare classes are lifted so 34k
  healthy days can't teach "healthy is always safe".

Evaluation, in rising order of interest: event-split agreement (did it
learn the curriculum), leave-one-site-out per class (does it work on a
plant it never saw — the headline), and the gold subset including the
days where the referee caught the rules being wrong (can the student
beat the teacher).

Run: uv run python -m triage.train [--model hgb|rf|logreg|all]
--model trains a candidate into model/candidates/<name>/ (bundle +
metrics.json); the bare run is the shipped path, model/model.joblib.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from triage.train.features import FEATURE_COLUMNS
from triage.train.splits import event_split, leave_one_site_out, load_training

FEATURES = [*FEATURE_COLUMNS, "pi", "coverage", "rain_mm"]
GOLD_WEIGHT = 5.0
MODEL_DIR = Path("model")


def make_model() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.08, max_leaf_nodes=31,
        l2_regularization=1.0, random_state=7,
    )


def make_rf() -> Pipeline:
    # imputer because RandomForest rejects NaN (HGB eats it natively);
    # keep_empty_features so an all-NaN column in a LOSO fold keeps its slot
    return Pipeline([
        ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
        # min_samples_leaf caps tree depth — and the joblib artifact size
        ("rf", RandomForestClassifier(
            n_estimators=200, min_samples_leaf=5, n_jobs=-1, random_state=7,
        )),
    ])


def make_logreg() -> Pipeline:
    # the linear baseline: if this lands near the trees, the features were
    # doing all the work. lbfgs is deterministic and wants scaled inputs.
    return Pipeline([
        ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
        ("scale", StandardScaler()),
        ("logreg", LogisticRegression(max_iter=1000)),
    ])


# candidate registry: --model NAME picks a factory; "all" loops them
MODELS: dict[str, Callable[[], object]] = {
    "hgb": make_model,
    "rf": make_rf,
    "logreg": make_logreg,
}


def build_matrix(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """(X, y, sample_weight) for the trainable rows."""
    X = df[FEATURES].astype(float)
    y = df["final_label"]
    counts = y.value_counts()
    balance = y.map(len(y) / (len(counts) * counts))
    provenance = df["provenance"].eq("referee").map({True: GOLD_WEIGHT, False: 1.0})
    return X, y, (balance * provenance).rename("weight")


def fit(df: pd.DataFrame, factory: Callable[[], object] = make_model) -> object:
    X, y, w = build_matrix(df)
    model = factory()
    if isinstance(model, Pipeline):
        # Pipeline.fit routes fit params by step name — a bare sample_weight=
        # is rejected. Deliberately not sklearn metadata routing.
        model.fit(X, y, **{f"{model.steps[-1][0]}__sample_weight": w})
    else:
        model.fit(X, y, sample_weight=w)
    return model


def run(name: str | None = None,
        factory: Callable[[], object] = make_model) -> None:
    all_rows = load_training()
    all_rows = all_rows[all_rows["final_label"] != "data_gap"]
    unclassified = all_rows[all_rows["final_label"] == "unclassified"]
    df = all_rows[all_rows["final_label"] != "unclassified"].reset_index(drop=True)
    print(f"trainable rows: {len(df)} | classes: {df['final_label'].nunique()} "
          f"| gold: {int((df['provenance'] == 'referee').sum())}")

    # 1. curriculum check: 20% event-granular holdout
    test = event_split(df, test_frac=0.2, salt="dev").to_numpy()
    model = fit(df[~test], factory)
    pred = model.predict(df.loc[test, FEATURES].astype(float))
    truth = df.loc[test, "final_label"]
    agreement = float((pred == truth).mean())
    holdout_f1 = float(f1_score(truth, pred, average="macro"))
    print(f"\n[1] event-holdout agreement: {agreement:.3f} "
          f"(macro-F1 {holdout_f1:.3f})")

    # 2. the headline: leave-one-site-out
    loso_pred = pd.Series(index=df.index, dtype=object)
    for site, mask in leave_one_site_out(df):
        m = mask.to_numpy()
        if (~m).sum() == 0 or m.sum() == 0:
            continue
        fold = fit(df[~m], factory)
        loso_pred[m] = fold.predict(df.loc[m, FEATURES].astype(float))
    print("\n[2] leave-one-site-out, per class:")
    print(classification_report(df["final_label"], loso_pred, zero_division=0))
    loso_report = classification_report(
        df["final_label"], loso_pred, zero_division=0, output_dict=True,
    )

    # 3. can the student beat the teacher? Gold rows where the referee
    # overruled the rules — using LOSO predictions (never trained on the site)
    gold = df[df["provenance"] == "referee"]
    overruled = gold[gold["rule_label"] != gold["final_label"]]
    with_referee = with_rules = None
    if len(overruled):
        with_referee = float((loso_pred[overruled.index] == overruled["final_label"]).mean())
        with_rules = float((loso_pred[overruled.index] == overruled["rule_label"]).mean())
        print(f"[3] on {len(overruled)} referee-overruled days (unseen-site preds): "
              f"model sides with referee {with_referee:.0%}, with old rule label {with_rules:.0%}")

    # 4. what does it say about the honest-unclassified pile?
    final_model = fit(df, factory)
    if len(unclassified):
        proba = final_model.predict_proba(unclassified[FEATURES].astype(float))
        top = pd.Series(final_model.classes_[proba.argmax(axis=1)])
        conf = proba.max(axis=1)
        confident = pd.Series(top[conf >= 0.8]).value_counts()
        print(f"\n[4] {len(unclassified)} unclassified days: "
              f"{(conf >= 0.8).sum()} predicted with >=80% confidence:")
        print("   ", confident.to_dict())

    # which checklist entries carry the weight? (shuffle one feature at a
    # time on the dev holdout; the accuracy drop is its importance)
    from sklearn.inspection import permutation_importance

    holdout = df[test]
    r = permutation_importance(
        model, holdout[FEATURES].astype(float), holdout["final_label"],
        n_repeats=3, random_state=7,
    )
    imp = pd.Series(r.importances_mean, index=FEATURES).sort_values(ascending=False)
    print("\ntop features (permutation importance):")
    print(imp.head(8).round(4).to_string())

    out_dir = MODEL_DIR if name is None else MODEL_DIR / "candidates" / name
    out_dir.mkdir(parents=True, exist_ok=True)
    # self-describing bundle: serving code reads feature order, classes, and
    # version from here — it must never import this module to learn them
    trained_at = datetime.now(timezone.utc)
    stamp = trained_at.strftime("%Y%m%dT%H%M%SZ")
    bundle = {
        "model": final_model,
        "features": FEATURES,
        "classes": [str(c) for c in final_model.classes_],
        "trained_at": trained_at.isoformat(timespec="seconds"),
        # candidates carry the name so /health and replay output attribute
        # results to the right model
        "version": stamp if name is None else f"{name}-{stamp}",
    }
    joblib.dump(bundle, out_dir / "model.joblib")
    print(f"\nwrote {out_dir / 'model.joblib'} (version {bundle['version']})")

    if name is not None:
        metrics = {
            "model": name,
            "version": bundle["version"],
            "trained_at": bundle["trained_at"],
            "rows": {
                "trainable": len(df),
                "gold": int((df["provenance"] == "referee").sum()),
                "unclassified": len(unclassified),
                "classes": int(df["final_label"].nunique()),
            },
            "event_holdout": {"agreement": agreement, "macro_f1": holdout_f1},
            "loso": {
                "macro_f1": float(loso_report["macro avg"]["f1-score"]),
                "report": loso_report,
            },
            "gold_overruled": {
                "n": len(overruled),
                "sides_with_referee": with_referee,
                "sides_with_rule": with_rules,
            },
        }
        # default=float: output_dict support counts are np.int64, which json
        # rejects (np.float64 sneaks through as a float subclass)
        with (out_dir / "metrics.json").open("w") as fh:
            json.dump(metrics, fh, indent=2, default=float)
        print(f"wrote {out_dir / 'metrics.json'}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m triage.train")
    parser.add_argument(
        "--model", choices=[*MODELS, "all"], default=None,
        help="train a candidate into model/candidates/<name>/ instead of "
             "the shipped path",
    )
    args = parser.parse_args(argv)
    if args.model is None:
        run()
    elif args.model == "all":
        for name, factory in MODELS.items():
            run(name, factory)
    else:
        run(args.model, MODELS[args.model])


if __name__ == "__main__":
    main()
