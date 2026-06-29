import streamlit as st

from pages import render_driver_page, render_manager_page
from styles import apply_styles, render_header


def main():
    """Start MilkRun and route users to the temporary Manager or Driver view."""
    apply_styles()

    # Temporary role switch. This can be replaced by a login system later.
    _, nav_col = st.columns([0.72, 0.28])
    with nav_col:
        page = st.segmented_control(
            "View",
            options=["Manager", "Driver"],
            default="Manager",
            label_visibility="collapsed",
        )

    render_header()

    # Sidebar currently gives simple product context only.
    with st.sidebar:
        st.header("MilkRun")
        st.caption("Build and assign daily milk collection routes.")

    if page == "Manager":
        render_manager_page()
    else:
        render_driver_page()


if __name__ == "__main__":
    main()
