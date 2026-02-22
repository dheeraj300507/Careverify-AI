"""CareVerify - Utility Helpers"""


def paginate_query(query, page: int, page_size: int):
    """Apply pagination range to a Supabase query."""
    offset = (page - 1) * page_size
    return query.range(offset, offset + page_size - 1)


def validate_claim_data(data: dict) -> list[str]:
    """Validate claim creation payload. Returns list of error strings."""
    errors = []

    if not data:
        return ["Request body is required"]

    if not data.get("claimed_amount"):
        errors.append("claimed_amount is required")
    else:
        try:
            amount = float(data["claimed_amount"])
            if amount <= 0:
                errors.append("claimed_amount must be greater than 0")
            if amount > 10_000_000:
                errors.append("claimed_amount exceeds maximum allowed value")
        except (ValueError, TypeError):
            errors.append("claimed_amount must be a valid number")

    # Validate date format if provided
    from datetime import datetime
    for date_field in ("admission_date", "discharge_date"):
        if data.get(date_field):
            try:
                datetime.fromisoformat(str(data[date_field]))
            except ValueError:
                errors.append(f"{date_field} must be a valid ISO date")

    # Validate admission before discharge
    if data.get("admission_date") and data.get("discharge_date"):
        try:
            adm = datetime.fromisoformat(str(data["admission_date"]))
            dis = datetime.fromisoformat(str(data["discharge_date"]))
            if dis < adm:
                errors.append("discharge_date cannot be before admission_date")
        except ValueError:
            pass

    return errors