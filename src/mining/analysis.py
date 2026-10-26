from dataclasses import dataclass

import pandas as pd

from mining.anomalies import Detection, Incident, Settings, counts_table, detect, flagged_points, incidents
from mining.stats import fit_trend, summary_table, weekday_profile
from mining.theme import TOTAL_NAME, colour_map


@dataclass
class Analysis:
    data: pd.DataFrame
    mines: list[str]
    settings: Settings
    detections: dict[str, Detection]
    incidents: list[Incident]
    summary: pd.DataFrame
    counts: pd.DataFrame
    flagged: pd.DataFrame
    planned: pd.DataFrame | None

    @property
    def series(self) -> list[str]:
        return [*self.mines, TOTAL_NAME]

    @property
    def colours(self) -> dict[str, str]:
        return colour_map(self.mines)

    @property
    def start(self) -> pd.Timestamp:
        return self.data["Date"].min()

    @property
    def end(self) -> pd.Timestamp:
        return self.data["Date"].max()

    @property
    def days(self) -> int:
        return len(self.data)

    @property
    def period(self) -> str:
        return f"{self.start:%Y-%m-%d} to {self.end:%Y-%m-%d}"

    def weekday(self) -> pd.DataFrame:
        return weekday_profile(self.data, self.series)

    def headline(self) -> list[str]:
        total = self.summary.loc[TOTAL_NAME]
        shares = self.summary.loc[self.mines, "total"] / total["total"] * 100
        lead = shares.idxmax()
        trend = fit_trend(self.data[TOTAL_NAME], 1)
        spikes = sum(i.direction == "spike" for i in self.incidents)
        lines = [
            f"{len(self.mines)} mines produced {total['total']:,.0f} units over {self.days} days "
            f"({self.period}), {total['mean']:,.1f} per day on average.",
            f"{lead} is the largest contributor with {shares[lead]:.0f}% of total output; "
            f"the linear trend of total output changes by {trend.change_pct:+.1f}% across the period.",
        ]
        if self.incidents:
            worst = max(self.incidents, key=lambda i: abs(i.peak_deviation))
            lines.append(
                f"{len(self.incidents)} anomaly incident(s) found: {spikes} spike(s) and {len(self.incidents) - spikes} drop(s). "
                f"The largest, incident {worst.number}, was a {worst.direction} of {worst.peak_deviation:+.0f}% "
                f"({worst.title.split(' ', 1)[1]}) affecting {', '.join(worst.series)}."
            )
        else:
            lines.append("No anomalies were found with the current test settings.")
        return lines


def analyze(data: pd.DataFrame, settings: Settings, planned: pd.DataFrame | None = None) -> Analysis:
    data = data.reset_index(drop=True)
    mines = [c for c in data.columns if c not in ("Date", TOTAL_NAME)]
    series = [*mines, TOTAL_NAME]
    detections = detect(data, series, settings)
    return Analysis(
        data=data, mines=mines, settings=settings, detections=detections,
        incidents=incidents(detections, planned), summary=summary_table(data, series),
        counts=counts_table(detections), flagged=flagged_points(detections), planned=planned,
    )
