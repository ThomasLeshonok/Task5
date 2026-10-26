import numpy as np
import pandas as pd
import pytest

from mining.anomalies import (
    Settings, detect, detect_series, grubbs_critical, grubbs_test, incidents, iqr_test, ma_test, moving_average,
    zscore_test,
)
from mining.simulator import generate, planned_events


def frame(values, start="2099-11-01", **extra):
    data = pd.DataFrame({"Date": pd.date_range(start, periods=len(values)), "A": values})
    for name, series in extra.items():
        data[name] = series
    return data


def noisy(n=90, seed=1, level=100.0, sd=4.0):
    return np.random.default_rng(seed).normal(level, sd, n)


def test_iqr_fences():
    flags, lower, upper = iqr_test(pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 100.0]), 1.5)
    assert (lower, upper) == (-3.0, 13.0)
    assert flags.tolist() == [False] * 8 + [True]


def test_zscore_flags_beyond_threshold():
    y = pd.Series(np.r_[np.zeros(50), 10.0])
    flags, z = zscore_test(y, 3)
    assert flags.iloc[-1] and not flags.iloc[:-1].any()


def test_moving_average_excludes_the_day_itself():
    y = pd.Series([10.0, 10, 10, 100, 10, 10, 10])
    assert moving_average(y, 3, centered=True)[3] == 10
    assert moving_average(y, 3, centered=False)[4] == pytest.approx(40)
    flags, expected, deviation = ma_test(y, 3, 50, True)
    assert flags.tolist() == [False, False, True, True, True, False, False]
    assert deviation[3] == pytest.approx(900)


def test_grubbs_critical_value_matches_table():
    assert grubbs_critical(10, 0.05) == pytest.approx(2.290, abs=0.002)
    assert grubbs_critical(30, 0.05) == pytest.approx(2.908, abs=0.002)


def test_grubbs_finds_two_outliers_iteratively():
    y = pd.Series(np.r_[noisy(60), 160.0, 30.0])
    flags, steps = grubbs_test(y, 0.05)
    assert flags.iloc[-2:].all()
    assert flags.sum() <= 3 and len(steps) == flags.sum()


def test_injected_spike_found_by_every_test():
    values = noisy()
    values[45] = 170
    det = detect_series(frame(values), "A", Settings(weekday_adjust=False))
    row = det.frame.iloc[45]
    assert row[["iqr", "zscore", "ma", "grubbs"]].all()
    assert row["anomaly"] and row["direction"] == "spike"
    assert det.anomalies.index.tolist() == [45]


def test_disabled_tests_do_not_vote():
    values = noisy()
    values[45] = 170
    det = detect_series(frame(values), "A", Settings(tests=("iqr",), min_votes=3, weekday_adjust=False))
    assert det.frame[["zscore", "ma", "grubbs"]].sum().sum() == 0
    assert 45 in det.anomalies.index  # votes needed is capped at the number of enabled tests
    assert det.anomalies.index.tolist() == det.frame.index[det.frame["iqr"]].tolist()


def test_weekday_adjustment_stops_weekend_flags():
    dates = pd.date_range("2099-11-02", periods=84)
    values = noisy(84) * np.where(dates.day_of_week == 6, 0.55, 1.0)
    data = pd.DataFrame({"Date": dates, "A": values})
    raw = detect_series(data, "A", Settings(weekday_adjust=False, min_votes=1))
    adjusted = detect_series(data, "A", Settings(weekday_adjust=True, min_votes=1))
    sundays = data["Date"].dt.day_of_week == 6
    assert raw.frame.loc[sundays, "ma"].sum() >= 10
    assert adjusted.frame.loc[sundays, "anomaly"].sum() == 0


def test_overlapping_episodes_merge_into_one_incident():
    a, b = noisy(seed=2), noisy(seed=3)
    a[40:43] *= 0.3
    b[41:43] *= 0.3
    data = frame(a, B=b)
    found = incidents(detect(data, ["A", "B"], Settings(weekday_adjust=False)))
    assert len(found) == 1
    incident = found[0]
    assert incident.direction == "drop" and incident.series == ["A", "B"]
    assert incident.start == data["Date"][40] and incident.days == 3


def test_demo_events_are_matched_to_incidents():
    found = incidents(detect(generate(), ["LV-426", "Origae-6", "Fiorina 161", "LV-223", "Total"], Settings()),
                      planned_events())
    matched = {i.planned.split(":")[0] for i in found if i.planned}
    assert {"Generator event 1", "Generator event 4", "Generator event 5"} <= matched
    first = found[0]
    assert first.direction == "drop" and first.start == pd.Timestamp("2099-11-10")
