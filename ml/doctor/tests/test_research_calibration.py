from pathlib import Path

import numpy as np


def test_high_scoring_false_matches_disable_class(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    from train_research_head import selective_thresholds

    labels = ["tomato__healthy", "tomato__late_blight"]
    rows = [{"crop": "tomato"}] * 20
    ranked = np.array([[0.999, 0.001]] * len(rows))
    truth = np.array([0] * 3 + [1] * 17)
    cutoffs, _ = selective_thresholds(ranked, truth, labels, rows)
    assert cutoffs == dict.fromkeys(labels)


def test_calibration_counts_leaf_false_alarms_for_the_claimed_produce_crop(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    from train_research_head import selective_thresholds

    labels = ["other__out_of_scope", "potato__visible_damage"]
    rows = [{"crop": "potato"}] * 20
    ranked = np.array([[0.002, 0.998]] * len(rows))
    truth = np.array([1] * 14 + [0] * 6)
    cutoffs, _ = selective_thresholds(ranked, truth, labels, rows)
    assert cutoffs["potato__visible_damage"] is None
    assert cutoffs["other__out_of_scope"] is None
