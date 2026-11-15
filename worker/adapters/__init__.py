"""Adapter registry: the template's fetch.method picks the class."""
from worker.adapters.base import RawRecord, SourceAdapter


def get_adapter(template: dict) -> SourceAdapter:
    method = template["fetch"]["method"]
    if method == "brightdata_dataset":
        from worker.adapters.brightdata_dataset import BrightDataDatasetAdapter as A
    elif method == "brightdata_collector":
        from worker.adapters.brightdata_collector import BrightDataCollectorAdapter as A
    elif method == "csv":
        from worker.adapters.csv_file import CsvFileAdapter as A
    elif method == "census_api":
        from worker.adapters.http_api import CensusAcsAdapter as A
    elif method == "overpass":
        from worker.adapters.overpass import OverpassAdapter as A
    else:
        raise ValueError(f"unknown fetch method {method!r}")
    return A(template)


__all__ = ["RawRecord", "SourceAdapter", "get_adapter"]
