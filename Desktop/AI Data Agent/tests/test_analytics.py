import pandas as pd
import numpy as np
import pytest
from app.analytics.profiler import profile
from app.analytics.statistics import describe, correlation_matrix
from app.analytics.visualizer import histogram


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        "a": [1, 2, 3, 4, 5],
        "b": [5, 4, 3, 2, 1],
        "c": ["x", "y", "x", "y", "x"],
    })


@pytest.fixture
def messy_df():
    return pd.DataFrame({
        "id":       [1, 2, 2, 3, 4],
        "val":      [10.0, 20.0, 20.0, None, 40.0],
        "tag":      ["a", "b", "b", "c", None],
        "num_str":  ["10", "20", "20", "30", "40"],
        "constant": ["X", "X", "X", "X", "X"],
    })


# ── profiler ──────────────────────────────────────────────────────────────────

def test_profile_top_keys(sample_df):
    p = profile(sample_df)
    assert set(p.keys()) == {"summary", "columns", "quality"}


def test_profile_summary_shape(sample_df):
    p = profile(sample_df)
    assert p["summary"]["rows"] == 5
    assert p["summary"]["columns"] == 3


def test_profile_column_keys(sample_df):
    p = profile(sample_df)
    cp = p["columns"]["a"]
    assert "dtype_category" in cp
    assert "null_count" in cp
    assert "unique_count" in cp
    assert "issues" in cp


def test_profile_numeric_stats(sample_df):
    p = profile(sample_df)
    cp = p["columns"]["a"]
    assert cp["dtype_category"] == "numeric"
    assert cp["null_count"] == 0
    assert cp.get("mean") == pytest.approx(3.0)


def test_profile_detects_duplicate(messy_df):
    p = profile(messy_df)
    assert p["summary"]["duplicate_rows"] >= 1


def test_profile_detects_missing(messy_df):
    p = profile(messy_df)
    assert p["summary"]["missing_cells"] >= 2


def test_profile_detects_constant(messy_df):
    p = profile(messy_df)
    assert "constant" in p["columns"]["constant"]["issues"]


def test_profile_detects_numeric_as_string(messy_df):
    p = profile(messy_df)
    assert "numeric_as_string" in p["columns"]["num_str"]["issues"]


def test_profile_quality_score_range(sample_df):
    p = profile(sample_df)
    score = p["quality"]["score"]
    assert 0 <= score <= 100


def test_profile_all_null_column():
    df = pd.DataFrame({"a": [1, 2, 3], "b": [None, None, None]})
    p = profile(df)
    assert "all_null" in p["columns"]["b"]["issues"]


# ── statistics ───────────────────────────────────────────────────────────────

def test_describe_shape(sample_df):
    s = describe(sample_df)
    assert "a" in s.index


def test_describe_includes_skew(sample_df):
    s = describe(sample_df)
    assert "skew" in s.columns


def test_correlation_matrix(sample_df):
    corr = correlation_matrix(sample_df)
    assert corr.shape == (2, 2)


def test_correlation_self_is_one(sample_df):
    corr = correlation_matrix(sample_df)
    assert corr.loc["a", "a"] == pytest.approx(1.0)


def test_correlation_no_numeric_returns_empty():
    df = pd.DataFrame({"x": ["a", "b"], "y": ["c", "d"]})
    corr = correlation_matrix(df)
    assert corr.empty


# ── visualizer ───────────────────────────────────────────────────────────────

def test_histogram_returns_figure(sample_df):
    fig = histogram(sample_df, "a")
    assert fig is not None
