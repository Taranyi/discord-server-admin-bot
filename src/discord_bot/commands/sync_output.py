from __future__ import annotations

from ..course_service import CourseSyncResult


def format_sync_results(
    results: list[CourseSyncResult], *, scope: str
) -> str:
    if len(results) == 1:
        return _fit_message(_format_details(results[0]))

    lines = [
        f"✅ Saved the current Discord state for {len(results)} course(s) in {scope}.",
        "No Discord resources were modified.",
        "",
    ]
    for result in results[:40]:
        warning_count = (
            len(result.missing)
            + len(result.ambiguous)
            + int(result.category_issue is not None)
        )
        changes = len(result.accepted_changes) + len(result.rebound)
        lines.append(
            f"- **{result.course.university_name} → "
            f"{result.course.semester_name} → {result.course.name}**: "
            f"{result.present_count} channel(s), {changes} accepted change(s), "
            f"{warning_count} warning(s)"
        )
    if len(results) > 40:
        lines.append(f"- … and {len(results) - 40} more")
    lines.extend(
        (
            "",
            "Run `/course sync name:<course>` with university and semester "
            "filters when needed for full details.",
        )
    )
    return _fit_message("\n".join(lines))


def _format_details(result: CourseSyncResult) -> str:
    lines = [
        "✅ Current Discord state saved locally",
        "No Discord resources were modified.",
        "",
        f"**{result.course.name}**",
        f"University: {result.course.university_name}",
        f"Semester: {result.course.semester_name}",
        f"Category: {result.category_name or 'missing'}",
        f"Observed channels: {result.present_count}",
    ]
    if result.category_rebound:
        lines.append("- Reconnected the course to its unique matching category.")
    if result.category_issue:
        lines.append(f"- ⚠️ Category: {result.category_issue}")
    _append_section(lines, "Accepted manual changes", result.accepted_changes)
    _append_section(lines, "Reconnected managed resources", result.rebound)
    _append_section(lines, "Additional channels kept and observed", result.additional)
    _append_section(lines, "Missing managed resources", result.missing, warning=True)
    _append_section(lines, "Ambiguous matches", result.ambiguous, warning=True)
    if not any(
        (
            result.category_rebound,
            result.category_issue,
            result.accepted_changes,
            result.rebound,
            result.additional,
            result.missing,
            result.ambiguous,
        )
    ):
        lines.extend(("", "No manual differences detected."))
    return "\n".join(lines)


def _append_section(
    lines: list[str], heading: str, items: tuple[str, ...], *, warning: bool = False
) -> None:
    if not items:
        return
    marker = "⚠️ " if warning else ""
    lines.extend(("", f"{marker}**{heading}:**", *(f"- {item}" for item in items)))


def _fit_message(message: str, limit: int = 1950) -> str:
    if len(message) <= limit:
        return message
    suffix = "\n\n… Output shortened. Sync one course for full details."
    return message[: limit - len(suffix)].rstrip() + suffix
