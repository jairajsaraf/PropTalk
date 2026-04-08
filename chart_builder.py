"""Plotly chart generation from query results and LLM chart config."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def _detect_chart_type(df: pd.DataFrame) -> dict | None:
    """Auto-detect chart type from DataFrame columns."""
    if df.empty or len(df.columns) < 2:
        return None

    cols = df.columns.tolist()
    dtypes = df.dtypes

    # Check for lat/lon columns
    lat_cols = [c for c in cols if c.lower() in ("latitude", "lat", "parcel_level_latitude")]
    lon_cols = [c for c in cols if c.lower() in ("longitude", "lon", "lng", "parcel_level_longitude")]
    if lat_cols and lon_cols:
        color_col = None
        numeric_cols = [c for c in cols if pd.api.types.is_numeric_dtype(dtypes[c]) and c not in lat_cols + lon_cols]
        if numeric_cols:
            color_col = numeric_cols[0]
        return {
            "chart_type": "map",
            "x": lon_cols[0],
            "y": lat_cols[0],
            "color": color_col,
            "title": "Map View",
        }

    # Check for date + numeric (line chart)
    date_cols = [c for c in cols if pd.api.types.is_datetime64_any_dtype(dtypes[c])]
    numeric_cols = [c for c in cols if pd.api.types.is_numeric_dtype(dtypes[c])]

    if date_cols and numeric_cols:
        return {
            "chart_type": "line",
            "x": date_cols[0],
            "y": numeric_cols[0],
            "color": None,
            "title": f"{numeric_cols[0]} over time",
        }

    # Check for categorical + numeric (bar chart)
    cat_cols = [c for c in cols if pd.api.types.is_object_dtype(dtypes[c]) or pd.api.types.is_categorical_dtype(dtypes[c])]
    if cat_cols and numeric_cols:
        return {
            "chart_type": "bar",
            "x": cat_cols[0],
            "y": numeric_cols[0],
            "color": None,
            "title": f"{numeric_cols[0]} by {cat_cols[0]}",
        }

    return None


def build_chart(df: pd.DataFrame, chart_config: dict | None) -> go.Figure | None:
    """Build a Plotly chart from a DataFrame and chart configuration.

    Args:
        df: The query result DataFrame.
        chart_config: Dict with keys: chart_type, x, y, color, title.
                     If None, auto-detection is attempted.

    Returns:
        A Plotly Figure, or None if no chart can be generated.
    """
    if df.empty:
        return None

    # Use auto-detection if no config provided
    if not chart_config or not isinstance(chart_config, dict):
        chart_config = _detect_chart_type(df)
        if not chart_config:
            return None

    chart_type = chart_config.get("chart_type", "bar")
    x = chart_config.get("x")
    y = chart_config.get("y")
    color = chart_config.get("color")
    title = chart_config.get("title", "")

    # Validate columns exist in the DataFrame
    for col in [x, y, color]:
        if col and col not in df.columns:
            # Try case-insensitive match
            match = [c for c in df.columns if c.lower() == col.lower()]
            if match:
                if col == x:
                    x = match[0]
                elif col == y:
                    y = match[0]
                else:
                    color = match[0]
            elif col == color:
                color = None  # Skip color if not found
            else:
                # Fall back to auto-detection
                chart_config = _detect_chart_type(df)
                if not chart_config:
                    return None
                return build_chart(df, chart_config)

    try:
        if chart_type == "bar":
            fig = px.bar(df, x=x, y=y, color=color, title=title)
        elif chart_type == "line":
            fig = px.line(df, x=x, y=y, color=color, title=title)
        elif chart_type == "scatter":
            fig = px.scatter(df, x=x, y=y, color=color, title=title)
        elif chart_type == "histogram":
            fig = px.histogram(df, x=x or y, color=color, title=title)
        elif chart_type == "map":
            fig = px.scatter_mapbox(
                df,
                lat=y,
                lon=x,
                color=color,
                title=title,
                mapbox_style="open-street-map",
                zoom=5,
                height=600,
            )
        else:
            fig = px.bar(df, x=x, y=y, color=color, title=title)

        fig.update_layout(
            template="plotly_white",
            margin=dict(l=40, r=40, t=60, b=40),
        )
        return fig

    except Exception:
        # If chart generation fails, try auto-detection as last resort
        auto_config = _detect_chart_type(df)
        if auto_config and auto_config != chart_config:
            try:
                return build_chart(df, auto_config)
            except Exception:
                return None
        return None
