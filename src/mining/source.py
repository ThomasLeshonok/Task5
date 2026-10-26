import io
import re
from urllib.parse import quote

import pandas as pd
import requests

DATA_TAB = "Data"
GENERATOR_TAB = "Generator"
EVENTS_RANGE = "B12:G18"
SHEET_ID = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]{20,})")
BARE_ID = re.compile(r"^[a-zA-Z0-9-_]{30,}$")


class SourceError(Exception):
    pass


def sheet_id(url: str) -> str:
    url = url.strip()
    match = SHEET_ID.search(url)
    if match:
        return match.group(1)
    if BARE_ID.match(url):
        return url
    raise SourceError("That does not look like a Google Sheets link. Paste the address of the spreadsheet.")


def csv_url(url: str, tab: str = DATA_TAB, cell_range: str | None = None) -> str:
    if "/d/e/" in url or "output=csv" in url:
        return url.strip()
    address = f"https://docs.google.com/spreadsheets/d/{sheet_id(url)}/gviz/tq?tqx=out:csv&headers=1&sheet={quote(tab)}"
    return address + (f"&range={cell_range}" if cell_range else "")


def fetch_csv(address: str) -> str:
    try:
        response = requests.get(address, timeout=20)
    except requests.RequestException as error:
        raise SourceError(f"Could not reach Google Sheets: {error.__class__.__name__}") from error
    if response.status_code in (401, 403, 404) or "text/html" in response.headers.get("Content-Type", ""):
        raise SourceError("Google Sheets refused the request. Share the spreadsheet as 'Anyone with the link' and check the link.")
    response.raise_for_status()
    return response.content.decode("utf-8-sig")


def parse_table(text: str | bytes) -> pd.DataFrame:
    raw = pd.read_csv(io.BytesIO(text) if isinstance(text, bytes) else io.StringIO(text))
    raw = raw.loc[:, [c for c in raw.columns if str(c).strip() and not str(c).startswith("Unnamed")]]
    raw.columns = [str(c).strip() for c in raw.columns]
    date_col = next((c for c in raw.columns if c.casefold() == "date"), raw.columns[0] if len(raw.columns) else None)
    if date_col is None:
        raise SourceError("The table is empty.")

    frame = pd.DataFrame({"Date": pd.to_datetime(raw[date_col], errors="coerce", format="mixed")})
    mines = [c for c in raw.columns if c != date_col and c.casefold() != "total"]
    for name in mines:
        values = pd.to_numeric(raw[name].astype(str).str.replace(",", "").str.strip(), errors="coerce")
        if values.notna().any():
            frame[name] = values
    frame = frame.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
    mines = [c for c in frame.columns if c != "Date"]
    if not mines or frame.empty:
        raise SourceError("No mine columns found. Expected a 'Date' column followed by one numeric column per mine.")
    frame[mines] = frame[mines].fillna(0.0)
    frame.insert(1, "Total", frame[mines].sum(axis=1).round(1))
    return frame


def parse_events(text: str) -> pd.DataFrame:
    events = pd.read_csv(io.StringIO(text))
    events.columns = [str(c).strip() for c in events.columns]
    if "Day" not in events.columns:
        return pd.DataFrame()
    events["Day"] = pd.to_datetime(events["Day"], errors="coerce", format="mixed")
    for col in ("Duration", "Factor", "Probability", "Mines"):
        if col in events.columns:
            events[col] = pd.to_numeric(events[col], errors="coerce")
    return events.dropna(subset=["Day"]).reset_index(drop=True)


def load_sheet(url: str, tab: str = DATA_TAB) -> pd.DataFrame:
    return parse_table(fetch_csv(csv_url(url, tab)))


def load_sheet_events(url: str) -> pd.DataFrame | None:
    if "/d/e/" in url or "output=csv" in url:
        return None
    try:
        return parse_events(fetch_csv(csv_url(url, GENERATOR_TAB, EVENTS_RANGE)))
    except (SourceError, requests.RequestException, ValueError, pd.errors.ParserError):
        return None
