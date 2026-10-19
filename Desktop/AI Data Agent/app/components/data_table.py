import streamlit as st
import pandas as pd


def render_data_table(df: pd.DataFrame) -> None:
    st.subheader("Data Preview")
    col1, col2, col3 = st.columns(3)
    col1.metric("Rows", f"{len(df):,}")
    col2.metric("Columns", len(df.columns))
    col3.metric("Missing %", f"{df.isna().mean().mean() * 100:.1f}%")
    st.dataframe(df.head(500), use_container_width=True)
