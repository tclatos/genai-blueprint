"""
LLM model selector widget for Streamlit applications.

Provides a UI component for selecting and configuring the default LLM model.
"""

from genai_tk.core.llm_factory import LlmFactory
from genai_tk.utils.config_mngr import global_config
from streamlit.delta_generator import DeltaGenerator


# LLM Model Selection
def llm_selector_widget(w: DeltaGenerator) -> None:
    current_llm = global_config().get_str("llm.models.default")
    available_models = LlmFactory.known_items()

    try:
        index = available_models.index(current_llm)
    except ValueError:
        index = 0

    selected_llm = w.selectbox(
        "Default LLM Model",
        available_models,
        index=index,
        key="select_llm_widget",
        help="Select the default LLM model to use across the application",
    )

    if selected_llm != current_llm:
        global_config().set("llm.models.default", str(selected_llm))
        w.success(f"Default LLM changed to: {selected_llm}")
