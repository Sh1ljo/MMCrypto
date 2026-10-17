import streamlit as st

st.set_page_config(page_title="MM-Lab", layout="wide")
st.navigation(
    {
        "Lab": [
            st.Page("home.py", title="Home", icon=":material/home:", default=True),
            st.Page("pages/1_Run_Backtest.py", title="Run Backtest", icon=":material/play_arrow:"),
            st.Page("pages/2_Run_Explorer.py", title="Run Explorer", icon=":material/monitoring:"),
        ],
        "Learn": [
            st.Page("pages/3_Strategies.py", title="Strategies", icon=":material/menu_book:"),
        ],
    }
).run()
