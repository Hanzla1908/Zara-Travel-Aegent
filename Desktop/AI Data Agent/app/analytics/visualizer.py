import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def histogram(df: pd.DataFrame, column: str) -> go.Figure:
    return px.histogram(df, x=column, title=f"Distribution of {column}")


def scatter(df: pd.DataFrame, x: str, y: str, color: str | None = None) -> go.Figure:
    return px.scatter(df, x=x, y=y, color=color, title=f"{y} vs {x}")


def correlation_heatmap(df: pd.DataFrame) -> go.Figure:
    corr = df.select_dtypes("number").corr()
    return px.imshow(corr, text_auto=True, title="Correlation Matrix")


def bar(df: pd.DataFrame, x: str, y: str) -> go.Figure:
    return px.bar(df, x=x, y=y, title=f"{y} by {x}")


def line(df: pd.DataFrame, x: str, y: str) -> go.Figure:
    return px.line(df, x=x, y=y, title=f"{y} over {x}")
