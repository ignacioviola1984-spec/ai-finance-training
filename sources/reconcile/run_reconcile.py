"""
run_reconcile.py - independent ERP tie-out: do my canonical + finance_core
REPRODUCE the financial statements the ERP itself generates?

Orchestration (the ONLY place that touches both sides):
  1. canonical  = connector.canonical_tables(period)        # my pipeline's data
  2. mine       = finance_core over that canonical (BLIND)   # compute path
  3. native     = connector.fetch_native_statements(period)  # the ERP's own reports (answer key)
  4. result     = reconcile(mine, native)                    # line-by-line, fail-closed
  5. snapshot   = immutable: my statements + the ERP raw reports + the reconciliation
Exits non-zero on any break (mirrors test-dlocal/audit_dlocal_test.py).

HARD RULE: step 2 (the compute path) never sees the native reports; only this
orchestrator and the reconciler read both. compute.py imports nothing from the
native path.

CLI:
    python sources/reconcile/run_reconcile.py --period 2026-05 --source quickbooks
"""

import argparse
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.dirname(HERE)
for _s in ("canonical", "quickbooks", "snapshots", "reconcile"):
    _p = os.path.join(_SRC, _s)
    if _p not in sys.path:
        sys.path.insert(0, _p)

import materialize
import writer as snapshot_writer
from compute import compute_statements
from reconcile import reconcile, render_table

SNAPSHOT_BASE = os.path.join(_SRC, "snapshots", "data")
ACTIVE_DIR = os.path.join(_SRC, "canonical", "_active")


def _identity(connector, source):
    cfg = getattr(getattr(connector, "adapter", None), "config", None)
    if source == "erpnext":
        return getattr(cfg, "site_label", "") or "erpnext"
    return getattr(cfg, "realm_id", "") or os.environ.get("QBO_REALM_ID", "sandbox")


def reconcile_connector(connector, period, source="quickbooks", out_dir=ACTIVE_DIR,
                        snapshot_base=SNAPSHOT_BASE, now_iso=None, write_snapshot=True):
    """Run the tie-out for a connector. Returns (result, snapshot_dir|None)."""
    tables = connector.canonical_tables(period)
    materialize.write_canonical_tables(tables, out_dir)
    mine = compute_statements(out_dir, period)                  # BLIND compute path
    native = connector.fetch_native_statements(period)          # answer key (reconciler-only)
    result = reconcile(mine, native)

    snap_dir = None
    if write_snapshot:
        now_iso = now_iso or datetime.datetime.now(datetime.timezone.utc).isoformat()
        raw = dict(getattr(connector, "extract_raw", lambda p: {})(period))
        raw["computed_statements"] = mine
        raw["native_statements"] = native
        raw["reconciliation"] = result
        snap_dir, _ = snapshot_writer.write_snapshot(
            snapshot_base, _identity(connector, source), period, raw, tables, result, now_iso,
            source=source, extra={"reconciliation_pass": result["pass"]})
    return result, snap_dir


def main(argv=None):
    ap = argparse.ArgumentParser(description="Independent ERP tie-out (statements vs native reports)")
    ap.add_argument("--period", default="2026-05", help="reporting period YYYY-MM")
    ap.add_argument("--source", default=None, help="quickbooks|erpnext (default: $SOURCE)")
    ap.add_argument("--no-snapshot", action="store_true", help="do not write a snapshot")
    args = ap.parse_args(argv)
    source = materialize.current_source(args.source)
    if source == "synthetic":
        print("the synthetic source has no native ERP reports to reconcile against; "
              "use --source quickbooks (or erpnext).")
        return 2

    connector = materialize.build_connector(source)
    result, snap_dir = reconcile_connector(connector, args.period, source=source,
                                           write_snapshot=not args.no_snapshot)
    print(f"ERP tie-out | period {args.period} | source {source}")
    print(render_table(result))
    if snap_dir:
        print(f"\nsnapshot: {snap_dir}")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
