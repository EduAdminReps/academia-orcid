"""academia-orcid: ORCID data fetcher and LaTeX/JSON generator for academic vita reports."""

from .fetch import OrcidFetchError

__version__ = "0.1.0"

# Section type constants
SECTION_PUBLICATIONS = "publications"
SECTION_DATA = "data"
VALID_SECTIONS = [SECTION_PUBLICATIONS, SECTION_DATA]

# Output filename constants
OUTPUT_PUBLICATIONS_TEX = "orcid-publications.tex"
OUTPUT_PUBLICATIONS_SUMMARY_TEX = "orcid-publications-summary.tex"  # profile link, counts
OUTPUT_DATA_TEX = "orcid-data.tex"
OUTPUT_PUBLICATIONS_JSON = "orcid-publications.json"
OUTPUT_DATA_JSON = "orcid-data.json"
OUTPUT_PUBLICATIONS_BIB = "orcid-publications.bib"

__all__ = [
    "OUTPUT_DATA_JSON",
    "OUTPUT_DATA_TEX",
    "OUTPUT_PUBLICATIONS_BIB",
    "OUTPUT_PUBLICATIONS_JSON",
    "OUTPUT_PUBLICATIONS_SUMMARY_TEX",
    "OUTPUT_PUBLICATIONS_TEX",
    "SECTION_DATA",
    "SECTION_PUBLICATIONS",
    "VALID_SECTIONS",
    "OrcidFetchError",
    "__version__",
]
