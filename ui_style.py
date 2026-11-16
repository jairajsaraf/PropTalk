"""The little CSS the theme cannot express (Streamlit 1.66.1 selectors; re-check them on upgrade).

Kept short on purpose: colors, fonts, radii and chart palettes live in .streamlit/config.toml.
"""

import streamlit as st

CSS = """
<style>
/* Headings in the serif face the theme registers (the theme's headingFont is not applied to headings in this build). */
h1, h2, h3, h4 { font-family: "Source Serif 4", Georgia, serif !important; letter-spacing: -0.01em; }
/* A readable measure on wide screens instead of edge-to-edge. */
[data-testid="stMainBlockContainer"] { max-width: 1100px; margin: 0 auto; }
/* The question box is the main control: make it feel like one. */
[data-testid="stTextInput"] input { font-size: 1.05rem; padding: 0.85rem 1rem; }
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
