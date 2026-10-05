"""SQL literal helpers.

The app builds SQL by f-string — a deliberate trade-off for Streamlit in
Snowflake, where bind parameters are awkward. These helpers are the only thing
standing between that and an injection, so every interpolated value goes through
one of them, including the ones that "can only be" a key or a channel name.
"""
import pandas as pd


def q(v):
    """Quote a value as a SQL string literal, doubling embedded single quotes."""
    return "'" + str(v).replace("'", "''") + "'"


def num(v, decimals):
    """Render a number as a SQL numeric literal; blank/NaN becomes 0.

    Rounded to the column's scale here so the value written is exactly the one
    the user saw in the preview.
    """
    try:
        if v is None or pd.isna(v):
            v = 0
    except (TypeError, ValueError):
        pass
    return f"{round(float(v), decimals):.{decimals}f}"
