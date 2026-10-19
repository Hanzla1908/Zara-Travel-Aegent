import streamlit as st
import pandas as pd
from app.analytics import visualizer


def render_chart_viewer(df: pd.DataFrame) -> None:
    st.subheader("Chart Explorer")
    chart_type = st.selectbox("Chart type", ["Histogram", "Scatter", "Bar", "Line", "Correlation Heatmap"])
    num_cols = df.select_dtypes("number").columns.tolist()
    all_cols = df.columns.tolist()

    if chart_type == "Histogram":
        col = st.selectbox("Column", all_cols)
        st.plotly_chart(visualizer.histogram(df, col), use_container_width=True)

    elif chart_type == "Scatter":
        x = st.selectbox("X axis", num_cols, key="sx")
        y = st.selectbox("Y axis", num_cols, index=min(1, len(num_cols) - 1), key="sy")
        st.plotly_chart(visualizer.scatter(df, x, y), use_container_width=True)

    elif chart_type == "Bar":
        x = st.selectbox("X axis", all_cols, key="bx")
        y = st.selectbox("Y axis", num_cols, key="by")
        st.plotly_chart(visualizer.bar(df, x, y), use_container_width=True)

    elif chart_type == "Line":
        x = st.selectbox("X axis", all_cols, key="lx")
        y = st.selectbox("Y axis", num_cols, key="ly")
        st.plotly_chart(visualizer.line(df, x, y), use_container_width=True)

    elif chart_type == "Correlation Heatmap":
        st.plotly_chart(visualizer.correlation_heatmap(df), use_container_width=True)
