from fastapi import HTTPException, status


def refuse_if_in_use(name: str, uses: dict[str, int], advice: str) -> None:
    """
    Raise 409 when anything still points at the record being deleted, e.g.
    "Sales still has 3 employees and 1 shift. Move them first." The database
    would refuse the delete anyway; this says why instead of a generic error.
    """
    parts = [
        f"{count} {label if count != 1 else label.rstrip('s')}"
        for label, count in uses.items()
        if count
    ]
    if not parts:
        return
    listed = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"{name} still has {listed}. {advice}",
    )
