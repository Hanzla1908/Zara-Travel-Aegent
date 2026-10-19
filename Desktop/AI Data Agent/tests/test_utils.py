import pytest
import pandas as pd
from app.utils.validators import validate_dataframe, validate_upload


def test_validate_upload_bad_ext():
    with pytest.raises(ValueError, match="not supported"):
        validate_upload("file.txt", 100)


def test_validate_upload_too_large():
    with pytest.raises(ValueError, match="exceeds"):
        validate_upload("file.csv", 999 * 1024 * 1024)


def test_validate_upload_empty_file():
    with pytest.raises(ValueError, match="empty"):
        validate_upload("file.csv", 0)


def test_validate_upload_no_extension():
    with pytest.raises(ValueError, match="no extension"):
        validate_upload("nodotfile", 100)


def test_validate_df_no_columns():
    with pytest.raises(ValueError, match="no columns"):
        validate_dataframe(pd.DataFrame())


def test_validate_df_none():
    with pytest.raises(ValueError):
        validate_dataframe(None)


def test_validate_df_headers_only():
    with pytest.raises(ValueError, match="no data rows"):
        validate_dataframe(pd.DataFrame({"a": [], "b": []}))
