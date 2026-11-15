"""Source adapter base class. Owner: lane A.

Each source has a YAML template in sources/<key>.yaml. An adapter only fetches raw records;
worker/mapping.py turns them into CanonicalListing (or area_metrics rows) using the template.
Adapters only read: nothing here posts, messages or submits anything to a source site.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class RawRecord:
    source_key: str
    payload: dict                      # personal fields (template drop_fields) already removed
    content_hash: str                  # sha256 of the canonical JSON of payload
    snapshot_id: str | None = None
    meta: dict = field(default_factory=dict)


class SourceAdapter(ABC):
    """Subclasses: brightdata_dataset.py, brightdata_collector.py, csv_file.py, http_api.py."""

    fetch_method: str = ""             # matches sources.fetch_method

    def __init__(self, template: dict):
        self.template = template
        self.source_key: str = template["source_key"]

    @abstractmethod
    def fetch(self, inputs: list[dict] | None = None) -> Iterator[RawRecord]:
        """Yield raw records with personal fields dropped. Log each call with status and duration."""

    def drop_personal(self, payload: dict) -> dict:
        drop = set(self.template.get("drop_fields") or [])
        return {k: v for k, v in payload.items() if k not in drop}
