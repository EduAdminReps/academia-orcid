#!/usr/bin/env python3
"""Generate faculty sections from ORCID data for vita report.

This is a thin wrapper around the academia_orcid package.
It preserves backward compatibility with the composer's
``python run_latex.py --uin ... --output-dir ...`` interface.
"""

from academia_orcid.cli import main

if __name__ == "__main__":
    main()
