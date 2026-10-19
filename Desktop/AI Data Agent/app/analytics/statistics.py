import pandas as pd


def describe(df: pd.DataFrame) -> pd.DataFrame:
    """Extended describe including skew and kurtosis."""
    stats = df.describe(include="all").T
    num = df.select_dtypes("number")
    if not num.empty:
        stats["skew"] = num.skew()
        stats["kurtosis"] = num.kurtosis()
    return stats


def correlation_matrix(df: pd.DataFrame) -> pd.DataFrame:
    return df.select_dtypes("number").corr()
