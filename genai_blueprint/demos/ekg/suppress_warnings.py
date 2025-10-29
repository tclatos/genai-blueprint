"""Helper to suppress expected graph schema validation warnings."""

import warnings


def suppress_schema_warnings() -> None:
    """Suppress expected graph schema validation warnings.
    
    These warnings occur when field names don't exactly match class names,
    which is common when using BAML-generated models with different naming conventions.
    The warnings are informational and don't affect functionality.
    """
    warnings.filterwarnings(
        "ignore",
        category=UserWarning,
        message=".*No field paths found for.*in the model structure",
    )
    warnings.filterwarnings(
        "ignore",
        category=UserWarning,
        message=".*No valid field paths found for relationship.*",
    )


# Example usage in your code:
# from genai_blueprint.demos.ekg.suppress_warnings import suppress_schema_warnings
# suppress_schema_warnings()
# schema = subgraph.build_schema()  # No warnings
