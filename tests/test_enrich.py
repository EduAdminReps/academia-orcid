"""Tests for DOI content negotiation enrichment (academia_orcid.enrich)."""

from unittest.mock import MagicMock, patch

import pytest

from academia_orcid.enrich import (
    _extract_authors_from_csl,
    _extract_month_from_csl,
    _needs_enrichment,
    enrich_publication,
    enrich_publications,
    fetch_doi_metadata,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def csl_response():
    """A realistic CSL-JSON response from DOI content negotiation."""
    return {
        "type": "article-journal",
        "title": "A Great Paper on Signal Processing",
        "author": [
            {"given": "Alice", "family": "Smith"},
            {"given": "Bob", "family": "Jones"},
        ],
        "container-title": "IEEE Transactions on Signal Processing",
        "issued": {"date-parts": [[2024, 3]]},
        "volume": "72",
        "page": "1234-1245",
        "issue": "5",
        "publisher": "IEEE",
        "DOI": "10.1109/TSP.2024.001",
        "abstract": "We present a novel approach to signal processing.",
    }


@pytest.fixture
def minimal_pub():
    """A publication dict with only basic ORCID fields."""
    return {
        "authors": "Smith, A.",
        "raw_authors": ["Alice Smith"],
        "title": "A Great Paper",
        "venue": "",
        "year": "2024",
        "month": "",
        "doi": "10.1109/TSP.2024.001",
        "url": "",
        "pub_type": "journal-article",
        "external_ids": {"doi": "10.1109/TSP.2024.001"},
        "citation": None,
    }


@pytest.fixture
def complete_pub():
    """A publication dict with all fields already populated."""
    return {
        "authors": "Smith, A., Jones, B.",
        "raw_authors": ["Alice Smith", "Bob Jones"],
        "title": "A Great Paper",
        "venue": "IEEE Trans. Signal Processing",
        "year": "2024",
        "month": "3",
        "doi": "10.1109/TSP.2024.001",
        "url": "https://example.com",
        "pub_type": "journal-article",
        "external_ids": {"doi": "10.1109/TSP.2024.001"},
        "citation": None,
        "volume": "72",
        "pages": "1234-1245",
        "number": "5",
        "publisher": "IEEE",
        "abstract": "Existing abstract.",
    }


# ---------------------------------------------------------------------------
# Tests: fetch_doi_metadata
# ---------------------------------------------------------------------------

class TestFetchDoiMetadata:
    """Test DOI content negotiation requests."""

    @patch("academia_orcid.enrich.requests.get")
    def test_successful_fetch(self, mock_get, csl_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = csl_response
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        result = fetch_doi_metadata("10.1109/TSP.2024.001")
        assert result is not None
        assert result["title"] == "A Great Paper on Signal Processing"
        mock_get.assert_called_once()

        # Verify correct headers
        call_kwargs = mock_get.call_args
        assert "application/vnd.citationstyles.csl+json" in call_kwargs.kwargs["headers"]["Accept"]

    @patch("academia_orcid.enrich.requests.get")
    def test_timeout(self, mock_get):
        import requests as req
        mock_get.side_effect = req.exceptions.Timeout("timed out")

        result = fetch_doi_metadata("10.1109/TSP.2024.001", timeout=5)
        assert result is None

    @patch("academia_orcid.enrich.requests.get")
    def test_http_404(self, mock_get):
        import requests as req
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.raise_for_status.side_effect = req.exceptions.HTTPError(
            response=mock_resp
        )
        mock_get.return_value = mock_resp

        result = fetch_doi_metadata("10.9999/nonexistent")
        assert result is None

    @patch("academia_orcid.enrich.requests.get")
    def test_invalid_json(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.side_effect = ValueError("invalid json")
        mock_get.return_value = mock_resp

        result = fetch_doi_metadata("10.1109/TSP.2024.001")
        assert result is None

    @patch("academia_orcid.enrich.requests.get")
    def test_connection_error(self, mock_get):
        import requests as req
        mock_get.side_effect = req.exceptions.ConnectionError("no network")

        result = fetch_doi_metadata("10.1109/TSP.2024.001")
        assert result is None


# ---------------------------------------------------------------------------
# Tests: CSL-JSON extraction helpers
# ---------------------------------------------------------------------------

class TestExtractMonthFromCSL:
    """Test month extraction from CSL-JSON."""

    def test_with_month(self):
        csl = {"issued": {"date-parts": [[2024, 3]]}}
        assert _extract_month_from_csl(csl) == "3"

    def test_year_only(self):
        csl = {"issued": {"date-parts": [[2024]]}}
        assert _extract_month_from_csl(csl) == ""

    def test_no_issued(self):
        assert _extract_month_from_csl({}) == ""

    def test_empty_date_parts(self):
        csl = {"issued": {"date-parts": []}}
        assert _extract_month_from_csl(csl) == ""

    def test_full_date(self):
        csl = {"issued": {"date-parts": [[2024, 11, 15]]}}
        assert _extract_month_from_csl(csl) == "11"


class TestExtractAuthorsFromCSL:
    """Test author extraction from CSL-JSON."""

    def test_basic_authors(self):
        csl = {"author": [
            {"given": "Alice", "family": "Smith"},
            {"given": "Bob", "family": "Jones"},
        ]}
        result = _extract_authors_from_csl(csl)
        assert result == ["Alice Smith", "Bob Jones"]

    def test_family_only(self):
        csl = {"author": [{"family": "Consortium"}]}
        assert _extract_authors_from_csl(csl) == ["Consortium"]

    def test_given_only(self):
        csl = {"author": [{"given": "Madonna"}]}
        assert _extract_authors_from_csl(csl) == ["Madonna"]

    def test_no_authors(self):
        assert _extract_authors_from_csl({}) == []

    def test_empty_author_list(self):
        csl = {"author": []}
        assert _extract_authors_from_csl(csl) == []

    def test_skips_empty_entries(self):
        csl = {"author": [
            {"given": "Alice", "family": "Smith"},
            {},
            {"given": "Bob", "family": "Jones"},
        ]}
        result = _extract_authors_from_csl(csl)
        assert result == ["Alice Smith", "Bob Jones"]


# ---------------------------------------------------------------------------
# Tests: enrich_publication (fill-only semantics)
# ---------------------------------------------------------------------------

class TestEnrichPublication:
    """Test single publication enrichment with fill-only semantics."""

    def test_fills_empty_fields(self, minimal_pub, csl_response):
        enrich_publication(minimal_pub, csl_response)

        assert minimal_pub["venue"] == "IEEE Transactions on Signal Processing"
        assert minimal_pub["month"] == "3"
        assert minimal_pub["volume"] == "72"
        assert minimal_pub["pages"] == "1234-1245"
        assert minimal_pub["number"] == "5"
        assert minimal_pub["publisher"] == "IEEE"
        assert "novel approach" in minimal_pub["abstract"]

    def test_never_overrides_existing(self, complete_pub, csl_response):
        # Modify CSL to have different values
        csl_response["container-title"] = "Different Journal"
        csl_response["volume"] = "99"
        csl_response["page"] = "999-9999"
        csl_response["abstract"] = "Different abstract."

        enrich_publication(complete_pub, csl_response)

        # All original values preserved
        assert complete_pub["venue"] == "IEEE Trans. Signal Processing"
        assert complete_pub["month"] == "3"
        assert complete_pub["volume"] == "72"
        assert complete_pub["pages"] == "1234-1245"
        assert complete_pub["number"] == "5"
        assert complete_pub["publisher"] == "IEEE"
        assert complete_pub["abstract"] == "Existing abstract."

    def test_preserves_existing_authors(self, csl_response):
        pub = {
            "raw_authors": ["Original Author"],
            "venue": "",
            "month": "",
        }
        csl_response["author"] = [{"given": "Different", "family": "Author"}]

        enrich_publication(pub, csl_response)

        # Original authors preserved
        assert pub["raw_authors"] == ["Original Author"]

    def test_fills_authors_when_empty(self, csl_response):
        pub = {
            "raw_authors": [],
            "venue": "",
            "month": "",
        }

        enrich_publication(pub, csl_response)

        assert pub["raw_authors"] == ["Alice Smith", "Bob Jones"]

    def test_container_title_as_list(self):
        pub = {"venue": "", "month": "", "raw_authors": ["A"]}
        csl = {"container-title": ["Journal of Testing", "J. Test."]}

        enrich_publication(pub, csl)
        assert pub["venue"] == "Journal of Testing"

    def test_container_title_as_string(self):
        pub = {"venue": "", "month": "", "raw_authors": ["A"]}
        csl = {"container-title": "Journal of Testing"}

        enrich_publication(pub, csl)
        assert pub["venue"] == "Journal of Testing"

    def test_empty_csl(self, minimal_pub):
        """Enrichment with empty CSL-JSON changes nothing."""
        original_venue = minimal_pub["venue"]
        enrich_publication(minimal_pub, {})
        assert minimal_pub["venue"] == original_venue


# ---------------------------------------------------------------------------
# Tests: _needs_enrichment
# ---------------------------------------------------------------------------

class TestNeedsEnrichment:
    """Test whether a publication needs enrichment."""

    def test_needs_enrichment_missing_venue(self):
        pub = {"venue": "", "month": "3", "raw_authors": ["A"]}
        assert _needs_enrichment(pub) is True

    def test_needs_enrichment_missing_authors(self):
        pub = {"venue": "J", "month": "3", "volume": "1", "pages": "1",
               "number": "1", "publisher": "P", "abstract": "A",
               "raw_authors": []}
        assert _needs_enrichment(pub) is True

    def test_complete_no_enrichment_needed(self, complete_pub):
        assert _needs_enrichment(complete_pub) is False

    def test_missing_volume(self):
        pub = {"venue": "J", "month": "3", "raw_authors": ["A"]}
        assert _needs_enrichment(pub) is True


# ---------------------------------------------------------------------------
# Tests: enrich_publications (batch)
# ---------------------------------------------------------------------------

class TestEnrichPublications:
    """Test batch enrichment with mocked network calls."""

    def test_empty_list(self):
        result = enrich_publications([])
        assert result == []

    @patch("academia_orcid.enrich.fetch_doi_metadata")
    def test_enriches_pubs_with_doi(self, mock_fetch, minimal_pub, csl_response):
        mock_fetch.return_value = csl_response

        result = enrich_publications([minimal_pub])

        assert len(result) == 1
        assert result[0]["venue"] == "IEEE Transactions on Signal Processing"
        mock_fetch.assert_called_once_with("10.1109/TSP.2024.001", timeout=10)

    @patch("academia_orcid.enrich.fetch_doi_metadata")
    def test_skips_pubs_without_doi(self, mock_fetch):
        pub = {"doi": "", "venue": "", "month": "", "raw_authors": []}

        enrich_publications([pub])

        mock_fetch.assert_not_called()

    @patch("academia_orcid.enrich.fetch_doi_metadata")
    def test_skips_complete_pubs(self, mock_fetch, complete_pub):
        enrich_publications([complete_pub])

        mock_fetch.assert_not_called()

    @patch("academia_orcid.enrich.fetch_doi_metadata")
    def test_handles_fetch_failure(self, mock_fetch, minimal_pub):
        mock_fetch.return_value = None

        result = enrich_publications([minimal_pub])

        # Publication unchanged (no crash)
        assert result[0]["venue"] == ""

    @patch("academia_orcid.enrich.time.sleep")
    @patch("academia_orcid.enrich.fetch_doi_metadata")
    def test_rate_limiting(self, mock_fetch, mock_sleep, csl_response):
        mock_fetch.return_value = csl_response

        pub1 = {"doi": "10.1/a", "venue": "", "month": "", "raw_authors": ["A"]}
        pub2 = {"doi": "10.1/b", "venue": "", "month": "", "raw_authors": ["B"]}

        enrich_publications([pub1, pub2], rate_limit_delay=0.5)

        # Sleep called once (between first and second request)
        mock_sleep.assert_called_once_with(0.5)

    @patch("academia_orcid.enrich.time.sleep")
    @patch("academia_orcid.enrich.fetch_doi_metadata")
    def test_no_sleep_for_single_pub(self, mock_fetch, mock_sleep, csl_response):
        mock_fetch.return_value = csl_response

        pub = {"doi": "10.1/a", "venue": "", "month": "", "raw_authors": ["A"]}
        enrich_publications([pub])

        mock_sleep.assert_not_called()

    @patch("academia_orcid.enrich.fetch_doi_metadata")
    def test_mixed_pubs(self, mock_fetch, csl_response, minimal_pub, complete_pub):
        """Mix of enrichable, complete, and no-DOI pubs."""
        mock_fetch.return_value = csl_response

        no_doi_pub = {"doi": "", "venue": "", "month": "", "raw_authors": []}

        result = enrich_publications([minimal_pub, complete_pub, no_doi_pub])

        assert len(result) == 3
        # Only the minimal_pub should have been enriched
        mock_fetch.assert_called_once_with("10.1109/TSP.2024.001", timeout=10)
        assert result[0]["venue"] == "IEEE Transactions on Signal Processing"
        assert result[1]["venue"] == "IEEE Trans. Signal Processing"  # unchanged
        assert result[2]["venue"] == ""  # unchanged (no DOI)

    @patch("academia_orcid.enrich.fetch_doi_metadata")
    def test_custom_timeout(self, mock_fetch, minimal_pub, csl_response):
        mock_fetch.return_value = csl_response

        enrich_publications([minimal_pub], timeout=30)

        mock_fetch.assert_called_once_with("10.1109/TSP.2024.001", timeout=30)
