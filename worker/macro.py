"""Macro loader: `python -m worker.macro snapshot|load`. Owner: night-forecast.

snapshot  fetch the FRED CSVs (keyless) and write api/ml/data/macro_monthly.csv (small, committed; offline backtests).
load      the same fetch, then upsert macro_series (FRED + the Fed tables) and scenario_paths into DATABASE_URL.
The app only reads: this fetches public CSVs and never posts anything. Not a registered source, so the live worker
never runs it.
"""
import io
import subprocess
import sys
import time

import pandas as pd

from api.ml import macro

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
UA = "RentOrKnot-data/1.0"
FRED_IDS = {"ur": "CASAND5URN", "hpi": "SDXRSA", "mort": "MORTGAGE30US", "cpi_shelter": "CUSR0000SAH1"}


def fetch_fred(series_id: str) -> pd.Series:
    # curl is used because it follows the host's resolver and proxy settings reliably
    text = ""
    for attempt in range(3):
        r = subprocess.run(["curl", "-sS", "-m", "40", FRED_URL.format(series_id)],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.startswith(("observation_date", "DATE")):
            text = r.stdout
            break
        time.sleep(2 * (attempt + 1))
    if not text:
        raise OSError(f"could not fetch FRED series {series_id}")
    df = pd.read_csv(io.StringIO(text))
    if df.shape[1] != 2:
        raise ValueError(f"unexpected FRED response for {series_id}")
    s = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    s.index = pd.to_datetime(df.iloc[:, 0])
    return s.dropna()


def monthly(raw: dict[str, pd.Series], since: str = "2000-01-01") -> pd.DataFrame:
    """Monthly frame ur, hpi, mort (weekly mortgage rate averaged by month)."""
    out = pd.DataFrame({
        "ur": raw["ur"].resample("MS").last(),
        "hpi": raw["hpi"].resample("MS").last(),
        "mort": raw["mort"].resample("MS").mean(),
    })
    return out[out.index >= since].dropna(how="all").round(4)


def fed_rows(fed: dict) -> list[tuple]:
    """(series_id, period, value, source) for the hand-entered Fed tables; period = first day of the quarter."""
    year, q = int(fed["first_quarter"][:4]), int(fed["first_quarter"][-1])
    names = {"unemployment": "UNRATE", "mortgage_rate": "MORTGAGE", "house_price_index": "HPI"}
    rows = []
    for scen, tag in (("baseline", "BASE"), ("recession", "SEV")):
        for key, short in names.items():
            for i, v in enumerate(fed[scen][key]):
                k = (q - 1) + i
                period = pd.Timestamp(year + k // 4, 3 * (k % 4) + 1, 1).date()
                rows.append((f"FED_{tag}_{short}", period, v, fed[scen]["source"]))
    return rows


def load_db(conn, raw: dict[str, pd.Series], m: pd.DataFrame) -> dict:
    fed = macro.load_fed()
    ids = macro.SERIES_IDS
    rows = []
    for k in ("ur", "hpi"):
        rows += [(ids[k], d.date(), float(v), "fred") for d, v in m[k].dropna().items()]
    rows += [(ids["mort"], d.date(), float(v), "fred") for d, v in m["mort"].dropna().items()]
    sh = raw["cpi_shelter"].resample("MS").last()
    rows += [("CUSR0000SAH1", d.date(), float(v), "fred") for d, v in sh[sh.index >= "2000-01-01"].items()]
    rows += [(a, p, float(v), "fed_scenarios") for a, p, v, _ in fed_rows(fed)]
    mf = macro.to_model_frame(m)
    deltas = macro.scenario_deltas(mf, fed)
    paths = []
    sources = {"baseline": fed["baseline"]["source"], "recession": fed["recession"]["source"],
               "growth": fed["growth"]["source"]}
    for scen, d in deltas.items():
        lv = macro.scenario_levels(mf, d)
        for k, sid in ids.items():
            paths += [(scen, sid, p.date(), float(v), sources[scen]) for p, v in lv[k].items()]
    with conn.cursor() as cur:
        cur.executemany("INSERT INTO macro_series (series_id, period, value, source) VALUES (%s,%s,%s,%s) "
                        "ON CONFLICT (series_id, period) DO UPDATE SET value = EXCLUDED.value, source = EXCLUDED.source",
                        rows)
        cur.executemany("INSERT INTO scenario_paths (scenario, series_id, period, value, source) "
                        "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (scenario, series_id, period) "
                        "DO UPDATE SET value = EXCLUDED.value, source = EXCLUDED.source", paths)
    return {"macro_series": len(rows), "scenario_paths": len(paths)}


def main(argv: list[str]) -> int:
    mode = argv[0] if argv else "snapshot"
    raw = {k: fetch_fred(v) for k, v in FRED_IDS.items()}
    m = monthly(raw)
    if mode == "snapshot":
        m.rename_axis("month").to_csv(macro.SNAPSHOT)
        print(f"wrote {macro.SNAPSHOT} ({len(m)} months, last {m.index[-1].date()})")
        return 0
    if mode == "load":
        import os

        import psycopg
        url = os.environ.get("DATABASE_URL")
        if not url:
            print("DATABASE_URL is not set; nothing loaded.")
            return 0
        with psycopg.connect(url) as conn:
            print(load_db(conn, raw, m))
            conn.commit()
        return 0
    print("usage: python -m worker.macro snapshot|load")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
