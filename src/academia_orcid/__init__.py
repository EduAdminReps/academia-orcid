"""academia-orcid: ORCID data fetcher and LaTeX/JSON generator for academic vita reports."""

__version__ = "0.1.0"

# Section type constants
SECTION_PUBLICATIONS = "publications"
SECTION_DATA = "data"
VALID_SECTIONS = [SECTION_PUBLICATIONS, SECTION_DATA]

# Output filename constants
OUTPUT_PUBLICATIONS_TEX = "orcid-publications.tex"
OUTPUT_DATA_TEX = "orcid-data.tex"
OUTPUT_PUBLICATIONS_JSON = "orcid-publications.json"
OUTPUT_DATA_JSON = "orcid-data.json"
OUTPUT_PUBLICATIONS_BIB = "orcid-publications.bib"

# Public exceptions
from .fetch import OrcidFetchError
