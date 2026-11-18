"""A guard for one classic mistake: a model with N dimensions and a database column with M."""


def check_dimensions(model_dimensions: int, column_dimensions: int) -> list:
    """Return a list of problems (empty when the sizes agree). Run it at startup or in a test."""
    if model_dimensions == column_dimensions:
        return []
    return [
        f"The embedding model produces {model_dimensions} numbers per vector but the database column "
        f"holds {column_dimensions}. Set EMBEDDING_DIMENSIONS to the model's size and create a migration "
        "(then re-embed every document), or switch back to the old model."
    ]
