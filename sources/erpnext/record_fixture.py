"""
record_fixture.py - Capture ONE real ERPNext extraction as the test fixture.

The committed fixture (sources/fixtures/erpnext_demo/erpnext_extract_*.json) is
REPRESENTATIVE: it is modeled on Frappe's documented API response shapes (two
companies, two currencies) so the mapper and validations can be developed and
tested with no live instance and no secret. Run this once, against your own
ERPNext site, to replace it with a genuine capture and harden the tests on real
multi-company / multi-currency data:

    # with ERPNEXT_BASE_URL / ERPNEXT_API_KEY / ERPNEXT_API_SECRET in .env
    python sources/erpnext/record_fixture.py --period 2026-05

It writes the combined raw responses (read-only GETs only) to the fixture path.
Nothing here writes to ERPNext.

NOTE: the exact field names / report column shapes can vary by Frappe version. If
the live capture differs from what the mapper expects, the mapper's leaf-row
parsing (sources/erpnext/mapper.py) is the single place to adjust; see the README.
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
for _s in ("canonical", "snapshots", "erpnext"):     # NOT quickbooks: avoid adapter/mapper name clash
    _p = os.path.join(SRC, _s)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from auth import Config, ERPNextAuthError  # noqa: E402  (sources/erpnext/auth.py)
from adapter import ERPNextAdapter  # noqa: E402  (sources/erpnext/adapter.py)
from connector import ERPNextConnector  # noqa: E402  (sources/canonical/connector.py)

REPO = os.path.dirname(SRC)
FIXTURE_DIR = os.path.join(SRC, "fixtures", "erpnext_demo")


def _load_dotenv(path=None):
    """Best-effort .env loader (stdlib only, no python-dotenv dependency): set any
    KEY=VALUE from the repo-root .env that is not already in the environment. The
    .env is gitignored; nothing here writes or prints a secret value."""
    path = path or os.path.join(REPO, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Record a real ERPNext extraction as the test fixture")
    ap.add_argument("--period", default="2026-05", help="reporting period YYYY-MM")
    ap.add_argument("--out", default=None, help="output path (default: the committed fixture)")
    args = ap.parse_args(argv)

    _load_dotenv()                       # so ERPNEXT_* in the repo-root .env are picked up
    try:
        config = Config().require()
    except ERPNextAuthError as e:
        print(f"cannot record: {e}\n"
              "Set ERPNEXT_BASE_URL / ERPNEXT_API_KEY / ERPNEXT_API_SECRET in the repo-root .env "
              "(see sources/erpnext/README.md for the read-only-user setup).")
        return 2
    conn = ERPNextConnector(ERPNextAdapter(config))
    raw = conn.extract_raw(args.period)

    out = args.out or os.path.join(FIXTURE_DIR, f"erpnext_extract_{args.period.replace('-', '_')}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, sort_keys=True)
    counts = {k: (len(v) if isinstance(v, list) else "obj") for k, v in raw.items()}
    print(f"recorded real ERPNext extraction for {args.period} -> {out}")
    print(f"record counts: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
