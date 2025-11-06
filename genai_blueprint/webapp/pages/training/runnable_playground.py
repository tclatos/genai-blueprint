"""Runnable Playground - Interactive testing environment for LangChain Runnables.

This module provides a Streamlit-based interface for testing and exploring LangChain Runnable components.
It allows users to:
- Select from available Runnables
- View diagrams and graphs of the Runnable structure
- Upload or select input files
- Execute Runnables with different configurations
- View execution results and traces

The playground integrates with LangSmith for tracing and monitoring when configured.
"""

import importlib
import importlib.util
from pathlib import Path

import streamlit as st
from devtools import debug
from genai_tk.core.chain_registry import ChainRegistry
from genai_tk.utils.config_mngr import global_config
from pydantic import BaseModel

st.title("💬 Runnable Playground")

# Main Streamlit components and their purposes:
# 1. Title: Displays the page title and icon
# 2. Runnable Selector: Allows user to choose which Runnable to test
# 3. Sidebar: Provides configuration options (handled by config_sidebar)
# 4. Diagram Display: Shows visual representation of the Runnable if available
# 5. File Uploader: Allows input file selection for file-based Runnables
# 6. Graph Visualization: Shows the execution graph of the selected Runnable
# 7. Input Form: Provides text input and submission controls

# Load all available runnable components from registered modules
chain_registry = ChainRegistry.instance()
ChainRegistry.load_modules()

# Get list of all available runnables with their tags and names

runnables_list = sorted([(o.tag or "", o.name) for o in chain_registry.get_runnable_list()])
selection = st.selectbox("Runnable", runnables_list, index=0, format_func=lambda x: f"[{x[0]}] {x[1]}")
if not selection:
    st.stop()
runnable_desc = chain_registry.find(selection[1])
if not runnable_desc:
    st.stop()


# Get the first example from the runnable description to use as default values
first_example = runnable_desc.examples[0]

if diagram := runnable_desc.diagram:
    file = Path.cwd() / diagram
    st.image(str(file))

if path := first_example.path:
    sel_col1, sel_col2 = st.columns(2)
    uploaded_file = sel_col1.file_uploader(
        "Upload a text file",
        accept_multiple_files=False,
        type=["txt"],
    )
    sel_col2.write("Or else use:")
    default_file_name = sel_col2.radio("", options=[first_example.path], index=None, horizontal=True)
    if uploaded_file:
        path = Path(str(uploaded_file))

llm_id = global_config().get_str("llm.models.default")
config = {}
first_example = runnable_desc.examples[0]
config |= {"llm": llm_id}
if path:
    config |= {"path": path}
elif first_example.path:
    config |= {"path": first_example.path}

with st.expander("Runnable Graph", expanded=False):
    graph = runnable_desc.get(config).get_graph()
    try:
        if importlib.util.find_spec("pygraphviz") is None:
            # st.graphviz_chart
            st.image(graph.draw_mermaid_png())
        else:
            st.image(graph.draw_png())  # type: ignore
    except Exception:
        try:
            st.write(graph.draw_ascii())
        except Exception as ex:
            st.write(f"cannot draw graph: {ex}")


# selected_runnable = st.selectbox("Select a Runnable", list(RUNNABLES.keys()))


with st.form("my_form"):
    input = st.text_area("Enter input:", first_example.query[0], placeholder="")
    submitted = st.form_submit_button("Submit")
    # print(config)
    if submitted:
        chain = runnable_desc.get().with_config(configurable=config)
        result = chain.invoke(input)
        # Tracing is controlled by environment variables
        st.write("[View traces at LangSmith](https://smith.langchain.com/)")
        if isinstance(result, BaseModel):
            result_str = debug.format(result)

            st.write(result_str)
        else:
            st.write(result)
