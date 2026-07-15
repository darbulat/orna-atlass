def reject_required_nulls(data: dict, fields: set[str]) -> dict:
    """Allow omitted PATCH fields while rejecting explicit null for required values."""
    null_fields = sorted(field for field in fields if field in data and data[field] is None)
    if null_fields:
        raise ValueError(
            f"Fields may be omitted but cannot be null: {', '.join(null_fields)}"
        )
    return data
