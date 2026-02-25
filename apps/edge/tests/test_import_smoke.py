"""Import-level smoke tests for edge runtime dependencies."""


def test_pydantic_settings_is_importable() -> None:
    import pydantic_settings  # noqa: F401


def test_edge_app_object_imports() -> None:
    from sentinelid_edge.main import app

    assert app is not None
    assert app.title == "SentinelID Edge"
