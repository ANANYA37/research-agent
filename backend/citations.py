"""Citation verification for generated reports."""

import re


SOURCE_REF_RE = re.compile(r"\[Source\s+(\d+)\]", re.IGNORECASE)


def verify_citations(report: str, sources: list[dict]) -> dict:
    """Validate that [Source N] references point at collected source URLs."""
    source_count = len(sources)
    cited_numbers = [int(match) for match in SOURCE_REF_RE.findall(report or "")]
    unique_cited = sorted(set(cited_numbers))

    invalid = [
        number
        for number in unique_cited
        if number < 1 or number > source_count or not sources[number - 1].get("url")
    ]
    uncited = [
        index + 1
        for index, source in enumerate(sources)
        if source.get("url") and index + 1 not in unique_cited
    ]

    return {
        "valid": not invalid,
        "invalid_references": invalid,
        "uncited_sources": uncited,
        "cited_sources": unique_cited,
    }


def append_citation_warning(report: str, verification: dict) -> str:
    """Add a compact warning when generated citations do not validate."""
    invalid = verification.get("invalid_references", [])
    if not invalid:
        return report

    refs = ", ".join(f"[Source {number}]" for number in invalid)
    warning = (
        "\n\n---\n\n"
        "## Citation Verification\n\n"
        f"The following citations did not match a collected source URL and should be reviewed: {refs}.\n"
    )
    return report.rstrip() + warning

