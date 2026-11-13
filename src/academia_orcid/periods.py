# Vendored copy of coe-data-core/src/coe_core/periods.py -- do not edit here.
# Refresh from coe-data-core with: just vendor-set
"""Report periods: one meaning for --year, --acad_year, --cal_year and --semester.

Every COE repo selects time the same way. A period is a span of terms
(``YYYYSC``: S = 1 Spring, 2 Summer, 3 Fall; C = campus), chosen with exactly one
of four flags:

    --year       fiscal year Y   = Fall Y-1 + Spring Y            (2024: 202331 .. 202411)
    --acad_year  academic year Y = Fall Y-1 + Spring Y + Summer Y (2024: 202331 .. 202421)
    --cal_year   calendar year Y = Spring Y + Summer Y + Fall Y   (2024: 202411 .. 202431)
    --semester   one term                                         (202431)

Each flag takes the same forms:

    2024        that one period
    2020-2025   from the start of the first period to the end of the last
    2020+       from the start of that period on, open-ended
    all         every period (no limit); also what no flag at all means

For --semester the values are term codes: 202431, 202331-202521, 202331+, all.

Records are kept when they **overlap** the period. A record's own dates are
read with the same rules: an award dated 2024 is ``--cal_year 2024``; a
proposal filed in fiscal year 2024 is ``--year 2024``; a record dated by a
month is in that month's term (``Period.overlaps_date``). A blank start or end
term is open, so a record with unknown dates matches every period.

This module uses only the standard library and imports nothing from coe_core:
tamu-coe-set, tamu-scholars and academia-orcid deploy on their own, so
coe-data-core copies it verbatim into each of them (``just vendor-set``), and
``tests/test_vendored_drift.py`` fails if a copy differs. Change it here only.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass

FLAGS = ("year", "acad_year", "cal_year", "semester")

_KIND_NAMES = {"year": "FY", "acad_year": "AY", "cal_year": "CY"}
_SEMESTER_NAMES = {"1": "Spring", "2": "Summer", "3": "Fall"}
_MIN_YEAR, _MAX_YEAR = 1990, 2100

_HELP = {
    "year": "fiscal year: Fall Y-1 + Spring Y. Forms: 2024, 2020-2025, 2020+, all",
    "acad_year": "academic year: Fall Y-1 + Spring + Summer Y. Forms: 2024, 2020-2025, 2020+, all",
    "cal_year": "calendar year: Spring + Summer + Fall Y. Forms: 2024, 2020-2025, 2020+, all",
    "semester": "one term, e.g. 202431. Forms: 202431, 202331-202521, 202331+, all",
}


def _year_bounds(kind: str, year: int) -> tuple[str, str]:
    """First and last College Station term of one fiscal, academic or calendar year."""
    if kind == "year":
        return f"{year - 1}31", f"{year}11"
    if kind == "acad_year":
        return f"{year - 1}31", f"{year}21"
    if kind == "cal_year":
        return f"{year}11", f"{year}31"
    raise ValueError(f"not a year flag: {kind!r}")


def _check_year(text: str) -> int:
    year = int(text)
    if not _MIN_YEAR <= year <= _MAX_YEAR:
        raise ValueError(f"year {year} is outside {_MIN_YEAR}-{_MAX_YEAR}")
    return year


def _check_term(text: str) -> str:
    if not re.fullmatch(r"\d{4}[123][12]", text):
        raise ValueError(f"term must be YYYYSC (S 1-3, campus 1-2), got {text!r}")
    _check_year(text[:4])
    return text


def _base(term: str) -> str:
    """Campus-agnostic YYYYS, so College Station and Galveston terms compare alike."""
    return term[:5]


@dataclass(frozen=True)
class Period:
    """A span of terms. ``start_term`` / ``end_term`` are None when open."""

    kind: str | None  # one of FLAGS, or None for "all years"
    value: str  # as given, e.g. "2024", "2020-2025", "2020+", "all"
    start_term: str | None
    end_term: str | None

    @property
    def is_all(self) -> bool:
        return self.start_term is None and self.end_term is None

    def overlaps(self, start: str | None, end: str | None) -> bool:
        """True if a record spanning ``start`` .. ``end`` (terms; blank = open) meets the period."""
        start = (start or "").strip() or None
        end = (end or "").strip() or None
        if self.end_term and start and _base(start) > _base(self.end_term):
            return False
        return not (self.start_term and end and _base(end) < _base(self.start_term))

    def contains_term(self, term: str) -> bool:
        """True if a single term falls inside the period."""
        return self.overlaps(term, term)

    def overlaps_year(self, year: int | str, kind: str = "cal_year") -> bool:
        """True if a record dated by a year of ``kind`` (default calendar) meets the period."""
        start, end = _year_bounds(kind, int(year))
        return self.overlaps(start, end)

    def overlaps_date(self, year: int | str, month: int | str | None = None) -> bool:
        """True if a record dated by a calendar year, and a month when one is known,
        meets the period: the month's term if the month is known (and valid), else
        the whole calendar year (``overlaps_year``)."""
        if month:
            try:
                return self.contains_term(term_of_month(year, month))
            except ValueError:
                pass
        return self.overlaps_year(year)

    def calendar_years(self) -> tuple[int | None, int | None]:
        """Calendar years the period touches (None = open), for records that only know a year."""
        first = int(self.start_term[:4]) if self.start_term else None
        last = int(self.end_term[:4]) if self.end_term else None
        return first, last

    def label(self) -> str:
        """Human-readable name: 'FY 2024', 'AY 2020-2025', 'CY 2020+', 'Fall 2024', 'All years'."""
        if self.kind is None or self.value == "all":
            return "All years"
        if self.kind == "semester":
            first, sep, last = self.value.partition("-")
            text = _term_name(first.rstrip("+"))
            if self.value.endswith("+"):
                return f"{text} on"
            return f"{text} - {_term_name(last)}" if sep else text
        return f"{_KIND_NAMES[self.kind]} {self.value}"

    def as_args(self) -> list[str]:
        """The command-line flag that selects this period, to pass to another program."""
        if self.kind is None:
            return []
        return [f"--{self.kind}", self.value]


def term_of_month(year: int | str, month: int | str) -> str:
    """The College Station term holding a calendar month: January to May spring,
    June and July summer, August to December fall. Raises ValueError on a bad month."""
    number = int(month)
    if not 1 <= number <= 12:
        raise ValueError(f"not a month: {month!r}")
    semester = "1" if number <= 5 else "2" if number <= 7 else "3"
    return f"{int(year)}{semester}1"


def _term_name(term: str) -> str:
    return f"{_SEMESTER_NAMES[term[4]]} {term[:4]}"


ALL = Period(None, "all", None, None)


def period_from_flag(kind: str | None, value: str | None) -> Period:
    """Build the period that ``--<kind> <value>`` selects. No kind or no value means all years."""
    if kind is None or value is None:
        return ALL
    if kind not in FLAGS:
        raise ValueError(f"unknown period flag {kind!r}; expected one of {FLAGS}")
    text = str(value).strip()
    if text.lower() == "all":
        return Period(kind, "all", None, None)

    if kind == "semester":
        if m := re.fullmatch(r"(\d{6})\+", text):
            return Period(kind, text, _check_term(m[1]), None)
        if m := re.fullmatch(r"(\d{6})-(\d{6})", text):
            first, last = _check_term(m[1]), _check_term(m[2])
            if _base(first) > _base(last):
                raise ValueError(f"semester range runs backwards: {text!r}")
            return Period(kind, text, first, last)
        term = _check_term(text)
        return Period(kind, text, term, term)

    if m := re.fullmatch(r"(\d{4})\+", text):
        start, _ = _year_bounds(kind, _check_year(m[1]))
        return Period(kind, text, start, None)
    if m := re.fullmatch(r"(\d{4})-(\d{4})", text):
        first_year, last_year = _check_year(m[1]), _check_year(m[2])
        if first_year > last_year:
            raise ValueError(f"year range runs backwards: {text!r}")
        return Period(
            kind, text, _year_bounds(kind, first_year)[0], _year_bounds(kind, last_year)[1]
        )
    if re.fullmatch(r"\d{4}", text):
        start, end = _year_bounds(kind, _check_year(text))
        return Period(kind, text, start, end)
    raise ValueError(
        f"--{kind} must be YYYY, YYYY-YYYY, YYYY+ or all, got {text!r}"
        if kind != "semester"
        else f"--semester must be YYYYSC, YYYYSC-YYYYSC, YYYYSC+ or all, got {text!r}"
    )


def add_period_args(parser: argparse.ArgumentParser, *, required: bool = False) -> None:
    """Add the four mutually exclusive period flags to ``parser``."""
    group = parser.add_mutually_exclusive_group(required=required)
    for kind in FLAGS:
        group.add_argument(f"--{kind}", default=None, help=_HELP[kind])


def period_from_args(args: argparse.Namespace) -> Period:
    """The period selected by parsed arguments (all years if no flag was given)."""
    chosen = [k for k in FLAGS if getattr(args, k, None) is not None]
    if len(chosen) > 1:
        raise ValueError(f"choose one period flag, got {['--' + k for k in chosen]}")
    if not chosen:
        return ALL
    return period_from_flag(chosen[0], getattr(args, chosen[0]))
