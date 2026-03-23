#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import os

from app.db import Database
from app.utils import compute_r_multiple


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill r_multiple for closed positions.")
    parser.add_argument("--db-path", default=os.getenv("DB_PATH", "simulator.db"))
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("backfill_r_multiple")

    db = Database(args.db_path)
    db.init()

    updated = 0
    rows = db.list_closed_positions_missing_r_multiple(args.limit)
    for row in rows:
        r_value = compute_r_multiple(row.side, row.entry_price, row.stop_price, row.exit_price)
        if r_value is None:
            logger.warning(
                "skip position=%s eval=%s side=%s entry=%s stop=%s exit=%s",
                row.id,
                row.eval_id,
                row.side,
                row.entry_price,
                row.stop_price,
                row.exit_price,
            )
            continue
        db.update_position_r_multiple(row.id, float(r_value))
        updated += 1

    logger.info("backfilled=%s scanned=%s", updated, len(rows))
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
