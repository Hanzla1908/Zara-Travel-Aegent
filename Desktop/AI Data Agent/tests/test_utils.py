import pytest
import pandas as pd
from app.utils.validators import validate_dataframe, validate_upload


def test_validate_upload_bad_ext():
    with pytest.raises(ValueError, match="Unsupported"):
        validate_upload("file.txt", 100)


def test_validate_upload_too_large():
    with pytest.raises(ValueError, match="exceeds"):
        validate_upload("file.csv", 999 * 1024 * 1024)


def test_validate_empty_df():
    with pytest.raises(ValueError, match="empty"):
        validate_dataframe(pd.DataFrame())
