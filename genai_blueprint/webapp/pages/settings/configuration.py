"""Configuration page for GenAI Lab.

Displays current configuration information and provides controls for:
- LLM model selection
- Cache settings
- Debug/verbose modes
- Monitoring configuration
"""

import os

import streamlit as st
from genai_tk.core.cache import LlmCache
from genai_tk.core.llm_factory import PROVIDER_INFO
from genai_tk.utils.config_mngr import global_config
from langchain_core.globals import set_debug, set_verbose

from genai_blueprint.webapp.ui_components.llm_selector import llm_selector_widget


def display_config_info() -> None:
    """Display current configuration and available API keys."""
    config = global_config()

    st.subheader("Current Configuration")
    st.info(f"**Selected configuration:** {config.selected_config}")

    # Display key configuration values
    st.markdown("**Key Configuration Values:**")
    config_data = []

    # LLM configuration
    try:
        llm_model = config.get_str("llm.models.default", "Not set")
        config_data.append({"Setting": "LLM Default Model", "Value": llm_model})
    except Exception:
        config_data.append({"Setting": "LLM Default Model", "Value": "Not available"})

    # Embeddings configuration
    try:
        embeddings_model = config.get_str("embeddings.models.default", "Not set")
        config_data.append({"Setting": "Embeddings Default Model", "Value": embeddings_model})
    except Exception:
        config_data.append({"Setting": "Embeddings Default Model", "Value": "Not available"})

    # Vector store configuration
    try:
        vector_store = config.get_str("vector_store.default", "Not set")
        config_data.append({"Setting": "Vector Store Default", "Value": vector_store})
    except Exception:
        config_data.append({"Setting": "Vector Store Default", "Value": "Not available"})

    # Cache configuration
    try:
        cache_method = config.get_str("llm.cache", "Not set")
        config_data.append({"Setting": "LLM Cache Method", "Value": cache_method})
    except Exception:
        config_data.append({"Setting": "LLM Cache Method", "Value": "Not available"})

    if config_data:
        st.table(config_data)

    st.subheader("Available LLM API Keys")

    # Create a table showing API key status
    api_key_data = []
    for provider, (_, key_name) in PROVIDER_INFO.items():
        if key_name and key_name in os.environ:
            is_set = key_name in os.environ
            status = "✅ Set" if is_set else "❌ Not set"
            api_key_data.append({"Provider": provider, "Environment Variable": key_name, "Status": status})

    if api_key_data:
        st.table(api_key_data)
    else:
        st.warning("No API key information available")


def llm_configuration_section() -> None:
    """LLM configuration controls."""
    st.subheader("LLM Configuration")

    llm_selector_widget(st)

    # Cache Configuration
    cache_method = st.selectbox(
        "Cache Method",
        ["memory", "sqlite", "no_cache"],
        index=1,  # Default to sqlite
        help="Choose caching strategy for LLM responses",
    )
    LlmCache.set_method(cache_method)

    # Debug and Verbose Settings
    col1, col2 = st.columns(2)

    with col1:
        debug_mode = st.checkbox("Debug Mode", value=False, help="Enable LangChain debug mode for detailed logging")
        set_debug(debug_mode)

    with col2:
        verbose_mode = st.checkbox(
            "Verbose Mode", value=True, help="Enable LangChain verbose mode for operation details"
        )
        set_verbose(verbose_mode)


def monitoring_configuration_section() -> None:
    """Monitoring configuration controls."""
    st.subheader("Monitoring Configuration")

    monitoring_options = []

    # Check for Lunary
    if "LUNARY_APP_ID" in os.environ:
        lunary_enabled = st.checkbox(
            "Use Lunary.ai for monitoring", value=False, disabled=True, help="Lunary monitoring (currently disabled)"
        )
        if lunary_enabled:
            global_config().set("monitoring.lunary", "true")
        monitoring_options.append("Lunary.ai detected")

    # Check for LangSmith
    if "LANGCHAIN_API_KEY" in os.environ:
        langsmith_enabled = st.checkbox(
            "Use LangSmith for monitoring", value=True, help="Enable LangSmith tracing and monitoring"
        )

        if langsmith_enabled:
            global_config().set("monitoring.langsmith", "true")
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_PROJECT"] = global_config().get_str("monitoring.project")
            os.environ["LANGCHAIN_TRACING_SAMPLING_RATE"] = "1.0"
        else:
            os.environ["LANGCHAIN_TRACING_V2"] = "false"
            global_config().set("monitoring.langsmith", "false")

        monitoring_options.append("LangSmith detected")

    if not monitoring_options:
        st.info(
            "No monitoring services detected. Set LUNARY_APP_ID or LANGCHAIN_API_KEY environment variables to enable monitoring."
        )


def main() -> None:
    """Main configuration page."""
    st.title("⚙️ Configuration")
    st.markdown("Configure your GenAI Lab settings and view current configuration status.")

    # Configuration Information Section
    with st.expander("📋 Configuration Information", expanded=False):
        display_config_info()

    # LLM Configuration Section
    with st.expander("🤖 LLM Settings", expanded=True):
        llm_configuration_section()

        # LLM Test Section
        st.subheader("Test LLM")
        test_input = st.text_area(
            "Test Input", value="Tell me a joke in french", help="Enter text to test the currently configured LLM"
        )

        if st.button("Run Test"):
            from genai_tk.core.llm_factory import get_llm
            from langchain_core.messages import HumanMessage

            with st.spinner("Running LLM test..."):
                try:
                    llm = get_llm()
                    response = llm.invoke([HumanMessage(content=test_input)])
                    st.success("LLM Response:")
                    st.write(response.content)
                except Exception as e:
                    st.error(f"Error running LLM test: {str(e)}")
                    with st.expander("Show full error details"):
                        import traceback

                        st.text(traceback.format_exc())

    # Monitoring Configuration Section
    with st.expander("📊 Monitoring Settings", expanded=False):
        monitoring_configuration_section()

    # Additional Information
    st.markdown("---")
    st.markdown("### 💡 Tips")
    st.markdown("""
    - **Cache Method**: Use 'sqlite' for persistent caching across sessions, 'memory' for session-only caching
    - **Debug Mode**: Enable for troubleshooting LangChain operations
    - **Monitoring**: LangSmith provides detailed tracing of LLM calls and chain executions
    """)


if __name__ == "__main__":
    main()
else:
    main()
