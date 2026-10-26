from dataclasses import dataclass

import numpy as np
import pandas as pd

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

@dataclass(frozen=True)
class Summary:
    series: str
    days: int
    total: float
    mean: float
    std: float
    median: float
    q1: float
    q3: float
    iqr: float
    min: float
    max: float

    @property
    def cv(self) -> float:
        return self.std / self.mean * 100 if self.mean else float("nan")


@dataclass(frozen=True)
class Trend:
    degree: int
    fitted: np.ndarray
    coefficients: tuple[float, ...]
    r2: float

    @property
    def change_pct(self) -> float:
        first, last = self.fitted[0], self.fitted[-1]
        return (last - first) / first * 100 if first else float("nan")


def summarize(name: str, values: pd.Series) -> Summary:
    v = values.dropna().astype(float)
    q1, median, q3 = v.quantile([0.25, 0.5, 0.75])
    return Summary(
        series=name, days=len(v), total=float(v.sum()), mean=float(v.mean()), std=float(v.std(ddof=1)),
        median=float(median), q1=float(q1), q3=float(q3), iqr=float(q3 - q1), min=float(v.min()), max=float(v.max()),
    )


def summary_table(data: pd.DataFrame, series: list[str]) -> pd.DataFrame:
    rows = [summarize(name, data[name]) for name in series]
    frame = pd.DataFrame([r.__dict__ | {"cv": r.cv} for r in rows]).set_index("series")
    return frame[["mean", "std", "median", "q1", "q3", "iqr", "min", "max", "cv", "total"]]


def fit_trend(values: pd.Series, degree: int) -> Trend:
    y = values.astype(float).to_numpy()
    x = np.arange(len(y), dtype=float)
    degree = min(degree, max(len(y) - 1, 0))
    poly = np.polynomial.Polynomial.fit(x, y, degree)
    fitted = poly(x)
    ss_res = float(((y - fitted) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return Trend(
        degree=degree, fitted=fitted, coefficients=tuple(float(c) for c in poly.convert().coef),
        r2=1 - ss_res / ss_tot if ss_tot else 1.0,
    )


def weekday_profile(data: pd.DataFrame, series: list[str]) -> pd.DataFrame:
    by_day = data.groupby(data["Date"].dt.day_of_week)[series].mean()
    profile = by_day / data[series].mean()
    profile.index = [WEEKDAYS[d] for d in by_day.index]
    return profile
