from dataclasses import dataclass, replace

import numpy as np
import pandas as pd
from scipy import stats as sps

TESTS = {"iqr": "IQR rule", "zscore": "Z-score", "ma": "Moving average", "grubbs": "Grubbs"}


@dataclass(frozen=True)
class Settings:
    iqr_k: float = 1.5
    z_threshold: float = 3.0
    ma_window: int = 7
    ma_pct: float = 25.0
    ma_centered: bool = True
    grubbs_alpha: float = 0.05
    tests: tuple[str, ...] = tuple(TESTS)
    min_votes: int = 2
    weekday_adjust: bool = True

    @property
    def votes_needed(self) -> int:
        return max(1, min(self.min_votes, len(self.tests)))

    def describe(self) -> list[tuple[str, str]]:
        window = "centred" if self.ma_centered else "trailing"
        rows = [
            ("IQR rule", f"outside Q1 - {self.iqr_k:g} x IQR .. Q3 + {self.iqr_k:g} x IQR"),
            ("Z-score", f"|value - mean| / std > {self.z_threshold:g}"),
            ("Moving average", f"more than {self.ma_pct:g}% away from the {self.ma_window}-day {window} average"),
            ("Grubbs", f"iterative two-sided test, alpha = {self.grubbs_alpha:g}"),
        ]
        rows = [(name, rule if key in self.tests else "off") for (name, rule), key in zip(rows, TESTS)]
        rows.append(("Anomaly when", f"at least {self.votes_needed} of {len(self.tests)} enabled tests agree"))
        rows.append(("Weekday pattern", "removed before testing" if self.weekday_adjust else "kept (raw values tested)"))
        return rows


@dataclass
class Detection:
    series: str
    frame: pd.DataFrame  # one row per day, see detect_series
    grubbs_steps: list[tuple[pd.Timestamp, float, float]]  # flagged date, G, critical G

    @property
    def anomalies(self) -> pd.DataFrame:
        return self.frame[self.frame["anomaly"]]

    def count(self, test: str) -> int:
        return int(self.frame[test].sum())


@dataclass
class Episode:
    series: str
    direction: str  # "spike" or "drop"
    rows: pd.DataFrame

    @property
    def start(self) -> pd.Timestamp:
        return self.rows["Date"].min()

    @property
    def end(self) -> pd.Timestamp:
        return self.rows["Date"].max()

    @property
    def peak(self) -> pd.Series:
        return self.rows.loc[self.rows["deviation_pct"].abs().idxmax()]

    @property
    def tests(self) -> list[str]:
        return [TESTS[t] for t in TESTS if self.rows[t].any()]


@dataclass
class Incident:
    number: int
    direction: str
    episodes: list[Episode]
    planned: str | None = None

    @property
    def start(self) -> pd.Timestamp:
        return min(e.start for e in self.episodes)

    @property
    def end(self) -> pd.Timestamp:
        return max(e.end for e in self.episodes)

    @property
    def series(self) -> list[str]:
        return list(dict.fromkeys(e.series for e in self.episodes))

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    @property
    def peak_deviation(self) -> float:
        return max((e.peak["deviation_pct"] for e in self.episodes), key=abs)

    @property
    def title(self) -> str:
        period = self.start.strftime("%Y-%m-%d")
        if self.days > 1:
            period += " to " + self.end.strftime("%Y-%m-%d")
        return f"{self.direction.capitalize()} {period}"


def weekday_factors(data: pd.DataFrame, column: str) -> pd.Series:
    weekday = data["Date"].dt.day_of_week
    overall = data[column].median()
    factors = data.groupby(weekday)[column].median() / overall if overall else pd.Series(1.0, index=range(7))
    return weekday.map(factors.replace(0, 1.0)).fillna(1.0).astype(float)


def iqr_test(y: pd.Series, k: float) -> tuple[pd.Series, float, float]:
    q1, q3 = y.quantile([0.25, 0.75])
    lower, upper = q1 - k * (q3 - q1), q3 + k * (q3 - q1)
    return (y < lower) | (y > upper), float(lower), float(upper)


def zscore_test(y: pd.Series, threshold: float) -> tuple[pd.Series, pd.Series]:
    std = y.std(ddof=1)
    z = (y - y.mean()) / std if std else y * 0.0
    return z.abs() > threshold, z


def moving_average(y: pd.Series, window: int, centered: bool) -> pd.Series:
    if centered:
        total = y.rolling(window + 1 - window % 2, center=True, min_periods=2).sum()
        count = y.rolling(window + 1 - window % 2, center=True, min_periods=2).count()
        return (total - y) / (count - 1)
    return y.shift(1).rolling(window, min_periods=max(2, window // 2)).mean()


def ma_test(y: pd.Series, window: int, pct: float, centered: bool) -> tuple[pd.Series, pd.Series, pd.Series]:
    expected = moving_average(y, window, centered)
    deviation = (y - expected) / expected * 100
    return deviation.abs() > pct, expected, deviation


def grubbs_critical(n: int, alpha: float) -> float:
    t = sps.t.ppf(1 - alpha / (2 * n), n - 2)
    return (n - 1) / np.sqrt(n) * np.sqrt(t * t / (n - 2 + t * t))


def grubbs_test(y: pd.Series, alpha: float) -> tuple[pd.Series, list[tuple[int, float, float]]]:
    flags = pd.Series(False, index=y.index)
    remaining = y.dropna().astype(float)
    steps = []
    while len(remaining) > 6 and len(steps) < len(y) // 4:
        std = remaining.std(ddof=1)
        if not std:
            break
        distance = (remaining - remaining.mean()).abs()
        idx = distance.idxmax()
        g, critical = distance[idx] / std, grubbs_critical(len(remaining), alpha)
        if g <= critical:
            break
        flags[idx] = True
        steps.append((idx, float(g), float(critical)))
        remaining = remaining.drop(idx)
    return flags, steps


def detect_series(data: pd.DataFrame, column: str, s: Settings) -> Detection:
    raw = data[column].astype(float)
    factor = weekday_factors(data, column) if s.weekday_adjust else pd.Series(1.0, index=data.index)
    y = raw / factor

    iqr, lower, upper = iqr_test(y, s.iqr_k)
    zflag, z = zscore_test(y, s.z_threshold)
    maflag, expected, deviation = ma_test(y, s.ma_window, s.ma_pct, s.ma_centered)
    gflag, steps = grubbs_test(y, s.grubbs_alpha)

    frame = pd.DataFrame({
        "Date": data["Date"], "value": raw, "adjusted": y, "factor": factor,
        "expected": expected * factor, "deviation_pct": deviation, "z": z,
        "iqr_low": lower * factor, "iqr_high": upper * factor,
        "iqr": iqr, "zscore": zflag, "ma": maflag, "grubbs": gflag,
    })
    for test in TESTS:
        if test not in s.tests:
            frame[test] = False
    frame["votes"] = frame[list(TESTS)].sum(axis=1)
    frame["anomaly"] = frame["votes"] >= s.votes_needed
    centre = expected.fillna(y.median())
    frame["deviation_pct"] = frame["deviation_pct"].fillna((y - centre) / centre * 100)
    frame["direction"] = np.where(y >= centre, "spike", "drop")
    return Detection(column, frame, [(data["Date"][i], g, c) for i, g, c in steps])


def detect(data: pd.DataFrame, series: list[str], s: Settings) -> dict[str, Detection]:
    return {name: detect_series(data, name, s) for name in series}


def episodes(detection: Detection, max_gap_days: int = 1) -> list[Episode]:
    rows = detection.anomalies
    found, current = [], []
    for _, row in rows.iterrows():
        if current and (
            row["direction"] != current[-1]["direction"] or (row["Date"] - current[-1]["Date"]).days > max_gap_days + 1
        ):
            found.append(current)
            current = []
        current.append(row)
    if current:
        found.append(current)
    return [Episode(detection.series, chunk[0]["direction"], pd.DataFrame(chunk)) for chunk in found]


def incidents(detections: dict[str, Detection], planned: pd.DataFrame | None = None) -> list[Incident]:
    pool = sorted((e for d in detections.values() for e in episodes(d)), key=lambda e: (e.start, e.series))
    merged: list[Incident] = []
    for ep in pool:
        target = next((i for i in merged if i.direction == ep.direction and ep.start <= i.end + pd.Timedelta(days=1)
                       and ep.end >= i.start - pd.Timedelta(days=1)), None)
        if target:
            target.episodes.append(ep)
        else:
            merged.append(Incident(0, ep.direction, [ep]))
    merged.sort(key=lambda i: i.start)
    order = list(detections)
    for incident in merged:
        incident.episodes.sort(key=lambda e: (order.index(e.series), e.start))
    return [replace(i, number=n, planned=match_planned(i, planned)) for n, i in enumerate(merged, start=1)]


def match_planned(incident: Incident, planned: pd.DataFrame | None) -> str | None:
    if planned is None or planned.empty:
        return None
    for n, ev in planned.reset_index(drop=True).iterrows():
        if pd.isna(ev.get("Day")) or pd.isna(ev.get("Factor")):
            continue
        start = pd.Timestamp(ev["Day"])
        end = start + pd.Timedelta(days=max(int(ev.get("Duration") or 1), 1) - 1)
        direction = "drop" if ev["Factor"] < 1 else "spike"
        if direction == incident.direction and incident.start <= end + pd.Timedelta(days=1) and incident.end >= start - pd.Timedelta(days=1):
            affected = ev.get("Affected")
            hit = f", hits {affected}" if isinstance(affected, str) and affected else ""
            return f"Generator event {n + 1}: {start:%Y-%m-%d}, {int(ev.get('Duration') or 1)} day(s), factor {ev['Factor']:g}{hit}"
    return None


def counts_table(detections: dict[str, Detection]) -> pd.DataFrame:
    rows = []
    for name, d in detections.items():
        anomalies = d.anomalies
        rows.append({"series": name, **{label: d.count(t) for t, label in TESTS.items()},
                     "Anomalies": len(anomalies),
                     "Spikes": int((anomalies["direction"] == "spike").sum()),
                     "Drops": int((anomalies["direction"] == "drop").sum())})
    return pd.DataFrame(rows).set_index("series")


def flagged_points(detections: dict[str, Detection]) -> pd.DataFrame:
    parts = []
    for name, d in detections.items():
        a = d.anomalies.copy()
        if a.empty:
            continue
        a["series"] = name
        a["tests"] = a.apply(lambda r: ", ".join(label for t, label in TESTS.items() if r[t]), axis=1)
        parts.append(a)
    if not parts:
        return pd.DataFrame(columns=["Date", "series", "direction", "value", "expected", "deviation_pct", "z", "votes", "tests"])
    out = pd.concat(parts, ignore_index=True)
    return out.sort_values(["Date", "series"])[["Date", "series", "direction", "value", "expected", "deviation_pct", "z", "votes", "tests"]]
