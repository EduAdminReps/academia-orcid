"""ORCID Record Schema - subset of fields used by this repository.

Full schema documentation:
    https://github.com/ORCID/orcid-model/tree/master/src/main/resources/record_3.0
    https://info.orcid.org/documentation/integration-guide/orcid-record/

API version: 3.0
Endpoint: https://pub.orcid.org/v3.0/{orcid}/record

This file documents the ORCID JSON structure we depend on. If the API changes,
update these types and the extraction logic in extract.py accordingly.
"""

from typing import TypedDict


# =============================================================================
# Value Wrappers
# ORCID often wraps simple values in {"value": ...} objects
# =============================================================================

class StringValue(TypedDict, total=False):
    """Wrapper for string values."""
    value: str


class DatePart(TypedDict, total=False):
    """Year, month, or day component."""
    value: str  # e.g., "2024", "01", "15"


# =============================================================================
# Identifiers
# =============================================================================

class OrcidIdentifier(TypedDict, total=False):
    """ORCID identifier block.

    Path: orcid-identifier
    Docs: https://info.orcid.org/documentation/integration-guide/orcid-record/#h-orcid-identifier
    """
    uri: str   # "https://orcid.org/0000-0000-0000-0000"
    path: str  # "0000-0000-0000-0000"
    host: str  # "orcid.org"


class ExternalId(TypedDict, total=False):
    """External identifier (DOI, PMID, etc.).

    Path: works/group/work-summary/external-ids/external-id[]
    Docs: https://info.orcid.org/documentation/integration-guide/orcid-record/#h-external-identifiers
    """
    external_id_type: str   # "doi", "pmid", "isbn", "issn", etc.
    external_id_value: str  # The actual identifier value
    external_id_url: StringValue  # Optional URL


class ExternalIds(TypedDict, total=False):
    """Container for external identifiers."""
    external_id: list[ExternalId]


# =============================================================================
# Publication Date
# =============================================================================

class PublicationDate(TypedDict, total=False):
    """Publication date with optional precision.

    Path: works/group/work-summary/publication-date
    Note: May have year only, year+month, or full date
    """
    year: DatePart
    month: DatePart
    day: DatePart


# =============================================================================
# Contributors (Authors)
# =============================================================================

class ContributorAttributes(TypedDict, total=False):
    """Contributor role and sequence."""
    contributor_sequence: str  # "first", "additional"
    contributor_role: str      # "author", "editor", etc.


class Contributor(TypedDict, total=False):
    """Individual contributor to a work.

    Path: works/group/work-summary/contributors/contributor[]
    Docs: https://info.orcid.org/documentation/integration-guide/orcid-record/#h-contributors
    """
    credit_name: StringValue           # Display name
    contributor_orcid: OrcidIdentifier  # Optional ORCID of contributor
    contributor_attributes: ContributorAttributes


class Contributors(TypedDict, total=False):
    """Container for contributors."""
    contributor: list[Contributor]


# =============================================================================
# Work Title
# =============================================================================

class WorkTitleWrapper(TypedDict, total=False):
    """Work title with optional subtitle and translated title.

    Path: works/group/work-summary/title
    """
    title: StringValue
    subtitle: StringValue
    translated_title: StringValue


# =============================================================================
# Work (Publication)
# =============================================================================

class WorkSummary(TypedDict, total=False):
    """Summary of a single work/publication.

    Path: works/group/work-summary[]
    Docs: https://info.orcid.org/documentation/integration-guide/orcid-record/#h-works

    Work types we handle:
        Journal articles: "journal-article", "journal-issue"
        Conference: "conference-paper", "conference-abstract", "conference-poster"
        Other: "book", "book-chapter", "report", "dissertation", etc.

    Full list: https://info.orcid.org/documentation/integration-guide/orcid-record/#h-work-types
    """
    put_code: int                    # Unique identifier for this work
    type: str                        # Publication type (see above)
    title: WorkTitleWrapper
    journal_title: StringValue       # Journal or venue name
    publication_date: PublicationDate
    external_ids: ExternalIds
    contributors: Contributors
    url: StringValue                 # Link to the work

    # Less commonly used but available:
    short_description: str           # Abstract/summary
    citation: dict                   # Citation in various formats
    country: StringValue             # Country of publication


class WorkGroup(TypedDict, total=False):
    """Group of related works (e.g., same work from multiple sources).

    Path: works/group[]
    Note: We typically use the first work-summary in each group.
    """
    work_summary: list[WorkSummary]
    external_ids: ExternalIds  # Merged external IDs across group


class Works(TypedDict, total=False):
    """Container for all works."""
    group: list[WorkGroup]


# =============================================================================
# Person Section
# =============================================================================

class Biography(TypedDict, total=False):
    """Biography/summary text.

    Path: person/biography
    """
    content: str  # Free-text biography
    visibility: str  # "public", "limited", "private"


class PersonExternalIdentifier(TypedDict, total=False):
    """External identifier linked to person profile (Scopus, ResearcherID, etc.).

    Path: person/external-identifiers/external-identifier[]
    Note: Different from work external-ids (DOIs, etc.)
    """
    external_id_type: str   # "Scopus Author ID", "ResearcherID", etc.
    external_id_value: str  # The identifier value
    external_id_url: StringValue  # Link to the profile


class PersonExternalIdentifiers(TypedDict, total=False):
    """Container for person external identifiers."""
    external_identifier: list[PersonExternalIdentifier]


class Person(TypedDict, total=False):
    """Person section containing biographical info.

    Path: person
    Docs: https://info.orcid.org/documentation/integration-guide/orcid-record/#h-person
    """
    name: dict  # Contains given-names, family-name, credit-name
    biography: Biography
    external_identifiers: PersonExternalIdentifiers


# =============================================================================
# Organization (shared by affiliations and fundings)
# =============================================================================

class OrganizationAddress(TypedDict, total=False):
    """Organization address."""
    city: str
    region: str  # State/province
    country: str  # ISO country code


class Organization(TypedDict, total=False):
    """Organization associated with an affiliation or funding.

    Used by: employments, educations, distinctions, memberships, services, fundings
    """
    name: str
    address: OrganizationAddress


# =============================================================================
# Affiliation Sections (Employment, Education, Distinction, Membership, Service)
# =============================================================================

class AffiliationSummary(TypedDict, total=False):
    """Common structure for affiliation-type entries.

    Used by: employment-summary, education-summary, distinction-summary,
             membership-summary, service-summary

    Path examples:
        - activities-summary/employments/affiliation-group[]/summaries[]/employment-summary
        - activities-summary/educations/affiliation-group[]/summaries[]/education-summary
    """
    put_code: int
    department_name: str  # Department or field of study
    role_title: str       # Job title, degree, award name, etc.
    start_date: PublicationDate  # Reuses date structure
    end_date: PublicationDate
    organization: Organization


class AffiliationGroup(TypedDict, total=False):
    """Group of related affiliations.

    Path: activities-summary/{section}/affiliation-group[]
    """
    summaries: list[dict]  # Contains {section}-summary objects


class Affiliations(TypedDict, total=False):
    """Container for affiliation-based sections.

    Used by: employments, educations, distinctions, memberships, services
    """
    affiliation_group: list[AffiliationGroup]


# =============================================================================
# Funding Section
# =============================================================================

class FundingTitle(TypedDict, total=False):
    """Funding/grant title."""
    title: StringValue


class FundingSummary(TypedDict, total=False):
    """Summary of a funding/grant entry.

    Path: activities-summary/fundings/group[]/funding-summary[]
    Docs: https://info.orcid.org/documentation/integration-guide/orcid-record/#h-fundings

    Funding types: "award", "contract", "grant", "salary-award"
    """
    put_code: int
    type: str  # Funding type
    title: FundingTitle
    start_date: PublicationDate
    end_date: PublicationDate
    organization: Organization  # Funder


class FundingGroup(TypedDict, total=False):
    """Group of related fundings."""
    funding_summary: list[FundingSummary]


class Fundings(TypedDict, total=False):
    """Container for fundings."""
    group: list[FundingGroup]


# =============================================================================
# Activities Summary
# =============================================================================

class ActivitiesSummary(TypedDict, total=False):
    """Summary of all activities (works, education, employment, etc.).

    Path: activities-summary
    Docs: https://info.orcid.org/documentation/integration-guide/orcid-record/#h-activities
    """
    works: Works
    employments: Affiliations
    educations: Affiliations
    distinctions: Affiliations
    memberships: Affiliations
    services: Affiliations
    fundings: Fundings
    # Sections we don't currently use:
    # invited_positions: Affiliations
    # qualifications: Affiliations
    # peer_reviews: dict
    # research_resources: dict


# =============================================================================
# Top-Level Record
# =============================================================================

class OrcidRecord(TypedDict, total=False):
    """Top-level ORCID record structure.

    Endpoint: GET https://pub.orcid.org/v3.0/{orcid}/record

    Used by:
        - academia_orcid.fetch: Fetches and caches full record
        - academia_orcid.extract: Extracts publications and data for LaTeX output
    """
    orcid_identifier: OrcidIdentifier
    person: Person
    activities_summary: ActivitiesSummary
    # Other sections available:
    # preferences: dict     # Locale settings
    # history: dict         # Account creation, modification dates


# =============================================================================
# Field Mapping: JSON keys to Python
# =============================================================================
# ORCID JSON uses kebab-case, Python uses snake_case.
# When accessing the actual JSON, use the kebab-case keys:
#
#   record["orcid-identifier"]["path"]
#   record["activities-summary"]["works"]["group"]
#   work["work-summary"][0]["type"]
#   work["publication-date"]["year"]["value"]
#   work["external-ids"]["external-id"]
#   contributor["credit-name"]["value"]
#
# The TypedDict definitions above use snake_case for Python conventions,
# but the actual JSON access must use the original kebab-case keys.
# =============================================================================


# =============================================================================
# Publication Type Constants
# =============================================================================

JOURNAL_ARTICLE_TYPES = frozenset({
    "journal-article",
    "journal-issue",
    "article-journal",  # Alternate form
})

CONFERENCE_PAPER_TYPES = frozenset({
    "conference-paper",
    "conference-abstract",
    "conference-poster",
    "paper-conference",  # Alternate form
})

# Types we categorize as "other"
OTHER_PUBLICATION_TYPES = frozenset({
    "book",
    "book-chapter",
    "book-review",
    "dictionary-entry",
    "dissertation",
    "dissertation-thesis",
    "edited-book",
    "encyclopedia-entry",
    "magazine-article",
    "manual",
    "newsletter-article",
    "newspaper-article",
    "online-resource",
    "preprint",
    "report",
    "research-tool",
    "supervised-student-publication",
    "technical-standard",
    "test",
    "translation",
    "website",
    "working-paper",
    "other",
})
