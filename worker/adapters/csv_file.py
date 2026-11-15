"""CSV adapter for Zillow Research ZIP-level indexes (ZORI, ZHVI).

Downloads the full CSV once, keeps only the template's ZIPs and writes that extract to data/ (committed);
later runs read the extract. Yields one RawRecord per (ZIP, month) with the payload shape area loaders use:
{"metric", "geo_id", "period", "value"}.
"""
import csv
import io
import logging
import re
from datetime import date
from typing import Iterator

import httpx

from worker.adapters.base import RawRecord, SourceAdapter
from worker.clean import content_hash
from worker.mapping import ROOT, load_zips

log = logging.getLogger("worker.csv")
DATE_COL = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class CsvFileAdapter(SourceAdapter):
    fetch_method = "csv"

    def _rows(self, spec: dict, zips: set[str]) -> tuple[list[str], list[dict]]:
        extract = ROOT / spec["extract"]
        if extract.exists():
            text = extract.read_text()
        else:
            log.info("downloading %s", spec["url"])
            r = httpx.get(spec["url"], timeout=300, follow_redirects=True)
            r.raise_for_status()
            reader = csv.DictReader(io.StringIO(r.text))
            col = self.template["columns"]["zip"]
            keep = [row for row in reader if str(row.get(col, "")).zfill(5) in zips]
            out = io.StringIO()
            w = csv.DictWriter(out, fieldnames=reader.fieldnames)
            w.writeheader()
            w.writerows(keep)
            text = out.getvalue()
            extract.write_text(text)
        reader = csv.DictReader(io.StringIO(text))
        return reader.fieldnames or [], list(reader)

    def fetch(self, inputs: list[dict] | None = None) -> Iterator[RawRecord]:
        f = self.template["fetch"]
        zips = set(load_zips(f["zip_file"]))
        zcol = self.template["columns"]["zip"]
        for spec in f["files"]:
            header, rows = self._rows(spec, zips)
            for row in rows:
                zip_ = str(row[zcol]).zfill(5)
                if zip_ not in zips:
                    continue
                for col in header:
                    if DATE_COL.match(col) and row[col] not in ("", None):
                        y, m, _ = col.split("-")
                        p = {"metric": spec["metric"], "geo_id": zip_, "period": date(int(y), int(m), 1).isoformat(),
                             "value": float(row[col])}
                        yield RawRecord(self.source_key, p, content_hash(p))
