"""Replay raw_records into tables without scraping again (night-data).

uv run python -m worker.replay --source <key> --target shared|staging|dev
"""


def main(argv: list[str] | None = None) -> int:
    raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit(main())
