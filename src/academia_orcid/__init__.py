"""academia-orcid: ORCID publications and profile data as structured JSON for the faculty composer."""

from .fetch import OrcidFetchError

__version__ = "0.1.0"

# Section type constants
SECTION_PUBLICATIONS = "publications"
SECTION_DATA = "data"
VALID_SECTIONS = [SECTION_PUBLICATIONS, SECTION_DATA]

# Output filename constants
OUTPUT_PUBLICATIONS_JSON = "orcid-publications.json"
OUTPUT_DATA_JSON = "orcid-data.json"

__all__ = [
    "OUTPUT_DATA_JSON",
    "OUTPUT_PUBLICATIONS_JSON",
    "SECTION_DATA",
    "SECTION_PUBLICATIONS",
    "VALID_SECTIONS",
    "OrcidFetchError",
    "__version__",
]
