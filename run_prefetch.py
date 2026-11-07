#!/usr/bin/env python3
"""Fill ORCID_JSON/ with every mapped faculty member's ORCID record.

Thin wrapper around ``academia_orcid.prefetch``; the cache lands next to this
file unless ``--data-dir`` says otherwise. Run it ahead of report generation so
the composer can use ``--no-fetch``.

    python run_prefetch.py --mapping-db ../coe-data-db/en.db
"""

import sys
from pathlib import Path

from academia_orcid.prefetch import main

if __name__ == "__main__":
    sys.exit(main(default_data_dir=Path(__file__).resolve().parent))
