import pandas as pd
import pytest
from app.analytics.profiler import profile
from app.analytics.statistics import describe, correlation_matrix
from app.analytics.visualizer import histogram


@pytest.fixture
def sample_df():
    return pd.DataFrame({"a": [1, 2, 3, 4, 5], "b": [5, 4, 3, 2, 1], "c": ["x", "y", "x", "y", "x"]})


def test_profile_keys(sample_df):
    p = profile(sample_df)
    assert "rows" in p and p["rows"] == 5
    assert "columns" in p and p["columns"] == 3


def test_describe_shape(sample_df):
    s = describe(sample_df)
    assert "a" in s.index


def test_correlation_matrix(sample_df):
    corr = correlation_matrix(sample_df)
    assert corr.shape == (2, 2)


def test_histogram_returns_figure(sample_df):
    fig = histogram(sample_df, "a")
    assert fig is not None
