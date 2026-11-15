"""Load named settings from the main checkout's .env into os.environ without printing them.

Only used by night scripts run by hand; the server gets real environment variables. Existing
environment values win. Never logs values.
"""
import os
from pathlib import Path

WANTED = ("DATABASE_URL", "DEV_DATABASE_URL", "BRIGHTDATA_API_TOKEN", "BRIGHTDATA_BUDGET_USD",
          "CENSUS_API_KEY", "GEMINI_API_KEY", "ONDEMAND_DAILY_USD")


def _candidates() -> list[Path]:
    here = Path(__file__).resolve().parent.parent
    out = [Path(p) for p in [os.environ.get("ENV_FILE")] if p]
    out.append(here / ".env")
    for parent in here.parents:                  # a worktree lives under <repo>/.claude/worktrees/<name>
        out.append(parent / ".env")
    return out


def load(names=WANTED) -> list[str]:
    """Returns the names that are now set (never the values)."""
    for p in _candidates():
        if p.is_file():
            for line in p.read_text().splitlines():
                k, sep, v = line.partition("=")
                k = k.strip()
                if sep and k in names and k not in os.environ:
                    v = v.split(" #")[0].strip().strip('"').strip("'")
                    if v:
                        os.environ[k] = v
            break
    return [n for n in names if os.environ.get(n)]


if __name__ == "__main__":
    print("set:", ", ".join(load()) or "none")
