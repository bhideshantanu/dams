"""America's dams: turn the National Inventory of Dams (NID) CSV into the page's data files.

Usage
  python scripts/build_dams.py path/to/nation.csv [path/to/removals.csv]

Download nation.csv from https://nid.sec.usace.army.mil/api/nation/csv (the monthly
GitHub workflow does this automatically). The American Rivers Dam Removal Database
(https://doi.org/10.6084/m9.figshare.5234068, CC BY 4.0) is read from the second argument,
or, if none is given, from the newest ARDamRemovalList*.csv in the sources/ folder.

Writes
  data/dams.json      one entry per dam for the map (position, year, hazard, purpose...)
  data/names.json     dam names and places, loaded only when someone hovers a dam
  data/removals.json  one entry per removed dam (American Rivers)
  data/summary.json   national and per-state statistics for the charts and scorecard

Choices worth knowing
- Associated structures (saddle dams, dikes listed under a main dam) are dropped, so each
  dam is counted once. The NID calls these out with "Is Associated Structure? = Yes".
- "Year Completed" is unknown for about a fifth of dams. Those count in totals but not in
  age statistics.
- Condition ratings, inspection dates and Emergency Action Plans are only summarized by
  state, never shown per dam.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

STATE_ABBR = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
    "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "District of Columbia": "DC",
    "Florida": "FL", "Georgia": "GA", "Guam": "GU", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY",
    "Louisiana": "LA", "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA",
    "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO",
    "Montana": "MT", "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH",
    "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY", "North Carolina": "NC",
    "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR",
    "Pennsylvania": "PA", "Puerto Rico": "PR", "Rhode Island": "RI",
    "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX",
    "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}
HAZARDS = ["Low", "Significant", "High", "Undetermined"]
FIRST_DECADE = 1850  # earlier dams are grouped as "Before 1850"
AGING_FROM, AGING_TO = 1980, 2050


def read_nid(path: Path) -> tuple[pd.DataFrame, str]:
    first = path.open(encoding="utf-8-sig").readline()
    data_date = first.split(",")[1].strip() if first.lower().startswith("data last updated") else ""
    df = pd.read_csv(path, skiprows=1 if data_date else 0, low_memory=False, dtype=str)
    return df, data_date


def clean(df: pd.DataFrame, as_of_year: int) -> pd.DataFrame:
    df = df[df["Is Associated Structure?"].fillna("No") != "Yes"].copy()
    num = lambda c: pd.to_numeric(df[c], errors="coerce")
    out = pd.DataFrame({
        "nid": df["NID ID"].fillna(""),
        "name": df["Dam Name"].fillna("Unnamed dam").str.strip(),
        "river": df["River or Stream Name"].fillna("").str.strip(),
        "city": df["City"].fillna("").str.strip(),
        "county": df["County"].fillna("").str.strip(),
        "state_name": df["State"].fillna(""),
        "lat": num("Latitude"),
        "lon": num("Longitude"),
        "year": num("Year Completed"),
        "height": num("NID Height (Ft)"),
        "storage": num("NID Storage (Acre-Ft)"),
        "hazard": df["Hazard Potential Classification"].fillna("Undetermined"),
        "purpose": df["Primary Purpose"].fillna("Not listed"),
        "owner": df["Primary Owner Type"].fillna("Not Listed").replace({"Not Listed": "Not listed"}),
        "dtype": df["Primary Dam Type"].fillna("Not listed"),
        "condition": df["Condition Assessment"].fillna("Not Available"),
        "eap": df["EAP Prepared"].fillna("Unknown"),
        "inspected": pd.to_datetime(df["Last Inspection Date"], errors="coerce", format="%m/%d/%Y"),
        "state_reg": df["State Regulated Dam"].fillna("No"),
    })
    out["state"] = out["state_name"].map(STATE_ABBR).fillna("")
    out.loc[~out["year"].between(1600, as_of_year), "year"] = np.nan
    out.loc[~out["hazard"].isin(HAZARDS), "hazard"] = "Undetermined"
    bad_pos = out["lat"].isna() | out["lon"].isna() | (out["lat"] == 0) | (out["lon"] == 0)
    out.loc[bad_pos, ["lat", "lon"]] = np.nan
    return out.reset_index(drop=True)


def decade_labels(as_of_year: int) -> list[str]:
    last = as_of_year // 10 * 10
    return ["Before 1850"] + [f"{d}s" for d in range(FIRST_DECADE, last + 1, 10)]


def decade_counts(years: pd.Series, as_of_year: int) -> list[int]:
    labels = decade_labels(as_of_year)
    counts = [0] * len(labels)
    for y in years.dropna().astype(int):
        idx = 0 if y < FIRST_DECADE else 1 + (y - FIRST_DECADE) // 10
        counts[min(idx, len(labels) - 1)] += 1
    return counts


def pct(part: float, whole: float) -> float | None:
    return round(100 * part / whole, 1) if whole else None


def stats(d: pd.DataFrame, as_of_year: int, data_date: str) -> dict:
    years = d["year"].dropna()
    n_known = len(years)
    high = d[d["hazard"] == "High"]
    cutoff = pd.Timestamp(data_date) - pd.DateOffset(years=5) if data_date else None
    insp = high["inspected"].where(high["inspected"].between("1950-01-01", data_date or "2100-01-01"))
    rated = high["condition"].isin(["Satisfactory", "Fair", "Poor", "Unsatisfactory"])
    s = {
        "dams": int(len(d)),
        "known_year": int(n_known),
        "median_year": int(years.median()) if n_known else None,
        "median_age": int(as_of_year - years.median()) if n_known else None,
        "pct_over50_now": pct((years <= as_of_year - 50).sum(), n_known),
        "pct_over50_2035": pct((years <= 2035 - 50).sum(), n_known),
        "decades": decade_counts(years, as_of_year),
        "hh_decades": decade_counts(high["year"], as_of_year),
        "unknown_year": int(len(d) - n_known),
        "aging": [pct((years <= y - 50).sum(), n_known) for y in range(AGING_FROM, AGING_TO + 1)],
        "purposes": [[k, int(v)] for k, v in d["purpose"].value_counts().items()],
        "owners": [[k, int(v)] for k, v in d["owner"].value_counts().items()],
        "hazard": {h: int((d["hazard"] == h).sum()) for h in HAZARDS},
        "state_regulated_pct": pct((d["state_reg"] == "Yes").sum(), len(d)),
        "high": {
            "n": int(len(high)),
            "eap_yes": int((high["eap"] == "Yes").sum()),
            "eap_no": int((high["eap"] == "No").sum()),
            "eap_not_required": int((high["eap"] == "Not Required").sum()),
            "condition": {c: int((high["condition"] == c).sum())
                          for c in ["Satisfactory", "Fair", "Poor", "Unsatisfactory"]},
            "rated": int(rated.sum()),
            "not_rated": int(len(high) - rated.sum()),
            "inspected_5y": int((insp >= cutoff).sum()) if cutoff is not None else None,
            "inspection_known": int(insp.notna().sum()),
            "over50_pct": pct((high["year"].dropna() <= as_of_year - 50).sum(), high["year"].notna().sum()),
        },
    }
    return s


def map_payload(d: pd.DataFrame, data_date: str) -> tuple[dict, dict]:
    m = d[d["lat"].notna()].reset_index(drop=True)
    states = sorted(s for s in d["state"].unique() if s)
    purposes = list(d["purpose"].value_counts().index)
    owners = list(d["owner"].value_counts().index)
    dtypes = list(d["dtype"].value_counts().index)
    idx = lambda values, col: m[col].map({v: i for i, v in enumerate(values)}).fillna(-1).astype(int).tolist()
    as_int = lambda col: m[col].round().fillna(-1).astype(int).tolist()
    dams = {
        "date": data_date,
        "states": states, "hazards": HAZARDS, "purposes": purposes,
        "owners": owners, "types": dtypes,
        "lat": (m["lat"] * 1000).round().astype(int).tolist(),
        "lon": (m["lon"] * 1000).round().astype(int).tolist(),
        "year": m["year"].fillna(0).astype(int).tolist(),
        "hz": idx(HAZARDS, "hazard"),
        "pu": idx(purposes, "purpose"),
        "ow": idx(owners, "owner"),
        "ty": idx(dtypes, "dtype"),
        "h": as_int("height"),
        "s": as_int("storage"),
        "st": idx(states, "state"),
    }
    place = np.where(m["city"] != "", m["city"],
                     np.where(m["county"] != "", m["county"] + " County", ""))
    names = {"name": m["name"].tolist(), "river": m["river"].tolist(),
             "place": place.tolist(), "nid": m["nid"].tolist()}
    return dams, names


# ---------------------------------------------------------------- removals (American Rivers)

REMOVAL_REASONS = ["Ecology", "Safety", "Dilapidated", "Economics", "Obsolete",
                   "No useful purpose", "Failure", "Liability", "Mitigation", "Recreation"]
REMOVAL_CHART_FROM = 1975


def _last_year(text) -> int | None:
    """'2018', '2018-2019', '2014 (or 1993)' -> the last four-digit year mentioned."""
    years = re.findall(r"(1[6-9]\d\d|20\d\d)", str(text or ""))
    return int(years[-1]) if years else None


def _reasons(text) -> list[str]:
    if text is None or (isinstance(text, float) and np.isnan(text)):
        return []
    synonyms = {"delapidated": "Dilapidated", "disrepair": "Dilapidated", "economic": "Economics",
                "economy": "Economics", "ecological": "Ecology", "public safety": "Safety",
                "abandoned": "Obsolete"}
    out = []
    for part in re.split(r"[/,;]", str(text)):
        p = part.strip()
        match = synonyms.get(p.lower()) or next((r for r in REMOVAL_REASONS if r.lower() == p.lower()), None)
        if match:
            out.append(match)
        elif p:
            out.append("Other")
    return sorted(set(out))


def find_removals_csv() -> Path | None:
    """Newest American Rivers file in sources/, judged by its latest Last_Updated date."""
    files = sorted((ROOT / "sources").glob("ARDamRemovalList*.csv"))
    if not files:
        return None
    def latest(p: Path):
        d = pd.read_csv(p, usecols=["Last_Updated"], dtype=str, encoding_errors="replace")
        return pd.to_datetime(d["Last_Updated"], errors="coerce").max()
    return max(files, key=latest)


def read_removals(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, encoding_errors="replace")
    df.columns = [c.strip().lstrip("﻿") for c in df.columns]
    lat_col = "Latitude" if "Latitude" in df.columns else "Latitiude"
    num = lambda c: pd.to_numeric(df[c], errors="coerce") if c in df.columns else pd.Series(np.nan, index=df.index)
    miles = num("Miles_Restored_US").fillna(num("River_Miles_Reported"))
    out = pd.DataFrame({
        "name": df["Dam_Name"].fillna("Unnamed dam").str.strip(),
        "river": df["River"].fillna("").str.strip(),
        "place": df["City_County"].fillna("").str.strip(),
        "state": df["State"].fillna("").str.strip().str.upper(),
        # border dams are listed as "MN; ND": they count for each state
        "states": df["State"].fillna("").str.upper().map(lambda s: [p.strip() for p in s.split(";") if p.strip()]),
        "lat": num(lat_col), "lon": num("Longitude"),
        "year": df["Year_Removed"].map(_last_year),
        "built": df["Year_Built"].map(_last_year),
        "height": num("Dam_Height_ft"),
        "use": df["Original_Use"].fillna("").str.strip(),
        "reasons": df["Reason_for_removal"].map(_reasons),
        "miles_up": miles,
        "nid": df["NID_ID"].fillna("").str.strip(),
        "updated": pd.to_datetime(df["Last_Updated"], errors="coerce"),
    })
    bad = out["lat"].isna() | out["lon"].isna() | (out["lat"] == 0) | (out["lon"] == 0)
    out.loc[bad, ["lat", "lon"]] = np.nan
    return out


def removal_stats(r: pd.DataFrame, last_year: int) -> dict:
    """last_year: the latest year American Rivers has data for (not the NID year)."""
    years = r["year"].dropna().astype(int)
    by_year = years.value_counts()
    first = REMOVAL_CHART_FROM
    reasons = pd.Series([x for lst in r["reasons"] for x in lst]).value_counts()
    peak = by_year.idxmax() if len(by_year) else None
    return {
        "n": int(len(r)),
        "dated": int(len(years)),
        "since2000": int((years >= 2000).sum()),
        "before_chart": int((years < first).sum()),
        "per_year": [int(by_year.get(y, 0)) for y in range(first, last_year + 1)],
        "peak_year": int(peak) if peak is not None else None,
        "peak_n": int(by_year.max()) if len(by_year) else 0,
        "reasons": [[k, int(v)] for k, v in reasons.items()],
        "no_reason": int(sum(1 for lst in r["reasons"] if not lst)),
    }


def removals_payload(r: pd.DataFrame) -> dict:
    """Every removal, so counts match the database; those without coordinates get null."""
    m = r.reset_index(drop=True)
    to_int = lambda s: s.round().fillna(-1).astype(int).tolist()
    coord = lambda s: [None if pd.isna(v) else int(round(v * 1000)) for v in s]
    return {
        "lat": coord(m["lat"]),
        "lon": coord(m["lon"]),
        "year": m["year"].fillna(0).astype(int).tolist(),
        "built": m["built"].fillna(0).astype(int).tolist(),
        "h": to_int(m["height"]),
        "miles": [None if pd.isna(v) else round(float(v), 1) for v in m["miles_up"]],
        "name": m["name"].tolist(), "river": m["river"].tolist(),
        "place": m["place"].tolist(), "state": [";".join(x) for x in m["states"]],
        "use": m["use"].tolist(), "reasons": [", ".join(x) for x in m["reasons"]],
    }


def write_json(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))
    print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size / 1e6:.2f} MB)")


def main(csv_path: str, removals_path: str | None = None) -> int:
    raw, data_date = read_nid(Path(csv_path))
    as_of_year = int(data_date[:4]) if data_date else pd.Timestamp.today().year
    d = clean(raw, as_of_year)
    print(f"{len(raw):,} records -> {len(d):,} dams (associated structures removed); "
          f"{d['lat'].notna().sum():,} with map positions; data date {data_date}")

    dams, names = map_payload(d, data_date)
    summary = {
        "date": data_date, "as_of_year": as_of_year,
        "decade_labels": decade_labels(as_of_year),
        "aging_years": [AGING_FROM, AGING_TO],
        "state_names": {v: k for k, v in STATE_ABBR.items() if v in set(d["state"])},
        "national": stats(d, as_of_year, data_date),
        "states": {st: stats(g, as_of_year, data_date) for st, g in d.groupby("state") if st},
    }

    rpath = Path(removals_path) if removals_path else find_removals_csv()
    if rpath:
        r = read_removals(rpath)
        nid_ids = set(raw["NID ID"].dropna().str.strip())
        last_year = int(r["year"].max()) if r["year"].notna().any() else as_of_year
        summary["removals"] = {
            "source_file": rpath.name,
            "updated": r["updated"].max().strftime("%Y-%m-%d") if r["updated"].notna().any() else "",
            "chart_from": REMOVAL_CHART_FROM, "chart_to": last_year,
            "still_in_nid": int(r["nid"].isin(nid_ids - {""}).sum()),
            "by_state": {k: int(v) for k, v in
                         pd.Series([s for lst in r["states"] for s in lst]).value_counts().items()},
        }
        summary["national"]["removals"] = removal_stats(r, last_year)
        for st in summary["states"]:
            summary["states"][st]["removals"] = removal_stats(r[r["states"].map(lambda l: st in l)], last_year)
        write_json(removals_payload(r), DATA / "removals.json")
        rn = summary["national"]["removals"]
        print(f"removals ({rpath.name}): {rn['n']:,} total, {rn['since2000']:,} since 2000, "
              f"peak {rn['peak_year']} ({rn['peak_n']}); {r['lat'].notna().sum():,} mapped")
    else:
        print("No American Rivers removal file found in sources/; skipping removals.")

    write_json(dams, DATA / "dams.json")
    write_json(names, DATA / "names.json")
    write_json(summary, DATA / "summary.json")
    n = summary["national"]
    print(f"median age {n['median_age']} yrs; {n['pct_over50_now']}% over 50 now, "
          f"{n['pct_over50_2035']}% by 2035; high hazard {n['high']['n']:,}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print(__doc__)
        sys.exit(1)
    sys.exit(main(*sys.argv[1:]))
