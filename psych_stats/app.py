import streamlit as st

from modules import correlation, data_manager, descriptives, export, inferential
from modules.data_manager import KEY_MAPPING_DONE, init_session_state

st.set_page_config(page_title="PsychStats", layout="wide")

init_session_state()

st.title("PsychStats — Thesis Analysis Tool")

PAGES = [
    ("Data Upload & Preprocessing", data_manager.render, True),
    ("Descriptive Statistics", descriptives.render, False),
    ("Group Comparisons", inferential.render, False),
    ("Correlation & Moderation", correlation.render, False),
    ("Export to Word", export.render, False),
]

mapping_done = st.session_state.get(KEY_MAPPING_DONE, False)

with st.sidebar:
    st.header("Navigation")
    labels = []
    for title, _render, always_enabled in PAGES:
        if always_enabled or mapping_done:
            labels.append(title)
        else:
            labels.append(f"{title} (complete Module 1 first)")

    choice = st.radio("Go to", labels, label_visibility="collapsed")

selected_index = labels.index(choice)
_page_title, render_fn, always_enabled = PAGES[selected_index]

if not always_enabled and not mapping_done:
    st.warning("Complete Module 1 (column role mapping) before using this section.")
else:
    render_fn()
