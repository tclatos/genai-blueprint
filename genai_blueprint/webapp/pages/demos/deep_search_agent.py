"""Deep Search Agent using GPT Researcher.

This module provides an enhanced Streamlit interface for running
GPT Researcher searches
"""

import asyncio
import tempfile
import textwrap
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Final

import pandas as pd
import streamlit as st
from genai_tk.extra.gpt_researcher_helper import run_gpt_researcher
from genai_tk.utils.config_mngr import global_config
from loguru import logger
from md2pdf import md2pdf
from streamlit import session_state as sss

from genai_blueprint.webapp.ui_components.config_editor import edit_config_dialog

# Page configuration
st.set_page_config(page_title="GPT Researcher", page_icon="🔍", layout="wide")

st.title("🔍 GPT Researcher Playground")

SAMPLE_SEARCH = [
    "What are the ethical issues with AI autonomous agents?",
    "What is the architecture of SmolAgents and how it compare with LangGraph?",
    "What are the Agentic AI solutions announced by AWS, Google, Microsoft, SalesForce, Service Now, UI Path, SAP, and other major software editors",
    "Define what is Agentic AI",
]


def initialize_session_state() -> None:
    """Initialize all session state variables."""
    if "log_entries" not in sss:
        sss.log_entries = deque(maxlen=100)
    if "research_full_report" not in sss:
        sss.research_full_report = None
    if "web_research_result" not in sss:
        sss.web_research_result = None
    if "research_history" not in sss:
        sss.research_history = []
    if "is_researching" not in sss:
        sss.is_researching = False


def clear_research() -> None:
    """Clear current research results and logs."""
    sss.research_full_report = None
    sss.web_research_result = None
    sss.log_entries = deque(maxlen=100)
    sss.is_researching = False


# Initialize session state
initialize_session_state()


class CustomLogsHandler:
    """Handles logging from GPT Researcher and stores for display."""

    def __init__(self, status_widget: Any) -> None:
        """Initialize the log handler.

        Args:
            status_widget: Streamlit status widget for showing current operation
        """
        self.status_widget = status_widget
        self.log_count = 0
        self.last_status = ""

    async def send_json(self, data: dict[str, Any]) -> None:
        """Process and store log entries from GPT Researcher.

        Args:
            data: Log data dictionary from GPT Researcher
        """
        if "log_entries" not in sss:
            sss.log_entries = deque(maxlen=200)

        log_type = data.get("type")
        if log_type == "logs":
            output = data.get("output", "")
            timestamp = datetime.now().strftime("%H:%M:%S")

            # Add timestamp to entry
            entry = {
                "type": "logs",
                "output": output,
                "timestamp": timestamp,
            }
            sss.log_entries.append(entry)
            self.log_count += 1

            # Update status widget with key actions
            if any(keyword in output for keyword in ["🔍 Starting", "✍️ Writing", "🤔 Planning", "🌐 Browsing"]):
                self.status_widget.update(label=output[:80], state="running")
                self.last_status = output

    async def write_log(self, line: str) -> None:
        """Write a single log line.

        Args:
            line: Log message to display
        """
        await self.send_json({"type": "logs", "output": line})


def display_logs_expander() -> None:
    """Display research logs in a collapsible expander."""
    if sss.log_entries:
        with st.expander(f"📋 Research Logs ({len(sss.log_entries)} entries)", expanded=False):
            st.caption("Detailed execution trace from GPT Researcher")

            # Option to show full or abbreviated logs
            col1, col2 = st.columns([3, 1])
            show_full = col1.checkbox("Show full logs", value=False, key="show_full_logs")

            if col2.button("📥 Export Logs", width="stretch"):
                log_text = "\n".join([f"[{e.get('timestamp', '')}] {e.get('output', '')}" for e in sss.log_entries])
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                st.download_button(
                    "Download Log File",
                    data=log_text,
                    file_name=f"research_logs_{timestamp}.txt",
                    mime="text/plain",
                    key="download_logs",
                )

            # Display logs in a container
            log_display = st.container(height=400)
            with log_display:
                for entry in sss.log_entries:
                    timestamp = entry.get("timestamp", "")
                    output = entry.get("output", "")

                    if show_full:
                        st.text(f"[{timestamp}] {output}")
                    else:
                        # Abbreviate long lines
                        abbreviated = textwrap.shorten(output, 150, placeholder="...")
                        st.text(f"[{timestamp}] {abbreviated}")


def display_configuration_section() -> str:
    """Display the configuration section and return selected config.

    Returns:
        Selected configuration name (defaults to 'default' on error)
    """
    with st.sidebar:
        st.header("⚙️ Configuration")

        # Load configuration
        try:
            gpt_researcher_config = global_config().merge_with("config/components/gpt_researcher.yaml")
            available_configs = list(gpt_researcher_config.get("gpt_researcher").keys())

            config_name = st.selectbox(
                "Research Profile",
                options=available_configs,
                index=0,
                help="Select a preconfigured research profile with specific settings",
            )

            # Ensure we have a valid config name
            if not config_name:
                return "default"

            # Display selected config details in expander
            with st.expander("📋 Config Details", expanded=False):
                config_details = gpt_researcher_config.get("gpt_researcher").get(config_name, {})
                st.json(config_details)

            # Config editor button
            if st.button("✏️ Edit Configuration", help="Edit GPT Researcher configuration file"):
                edit_config_dialog("config/components/gpt_researcher.yaml")

            return config_name

        except Exception as e:
            st.error(f"Failed to load configuration: {e}")
            logger.error(f"Configuration loading error: {e}", exc_info=True)
            return "default"


def display_how_it_works() -> None:
    """Display the 'How it works' information section."""
    with st.sidebar:
        st.header("❓ How It Works")

        with st.expander("Research Workflow", expanded=False):
            st.write("**Normal Research**")
            st.image(
                "https://private-user-images.githubusercontent.com/13554167/333804350-4ac896fd-63ab-4b77-9688-ff62aafcc527.png?jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3NDY2NDgzODEsIm5iZiI6MTc0NjY0ODA4MSwicGF0aCI6Ii8xMzU1NDE2Ny8zMzM4MDQzNTAtNGFjODk2ZmQtNjNhYi00Yjc3LTk2ODgtZmY2MmFhZmNjNTI3LnBuZz9YLUFtei1BbGdvcml0aG09QVdTNC1ITUFDLVNIQTI1NiZYLUFtei1DcmVkZW50aWFsPUFLSUFWQ09EWUxTQTUzUFFLNFpBJTJGMjAyNTA1MDclMkZ1cy1lYXN0LTElMkZzMyUyRmF3czRfcmVxdWVzdCZYLUFtei1EYXRlPTIwMjUwNTA3VDIwMDEyMVomWC1BbXotRXhwaXJlcz0zMDAmWC1BbXotU2lnbmF0dXJlPTgwM2RmODQwNjVmZTU0MjI4YTljODJjMzgxY2U1N2MwOGZjNWEyOGM3OTM5ZjNmNmEzMDEwYTg0ZjE5YzllYzUmWC1BbXotU2lnbmVkSGVhZGVycz1ob3N0In0.SsI3BqipPrR8mL8soiWF0mlCbnXxNnzTip6F4wgY9aM",
                width="stretch",
            )

            st.write("**Deep Research**")
            st.image(
                "https://github.com/user-attachments/assets/eba2d94b-bef3-4f8d-bbc0-f15bd0a40968",
                width="stretch",
            )

            st.markdown("""
            **Process Overview:**
            1. **Query Analysis**: Parse and understand research question
            2. **Source Discovery**: Find relevant web sources
            3. **Content Extraction**: Extract and process information
            4. **Synthesis**: Generate comprehensive report
            5. **Verification**: Validate sources and citations
            """)


def display_research_history() -> str | None:
    """Display research history in sidebar.

    Returns:
        Query string if reload button clicked, None otherwise
    """
    if sss.research_history:
        with st.sidebar:
            st.header("📚 Recent Searches")
            with st.expander("History", expanded=False):
                for idx, item in enumerate(reversed(sss.research_history[-5:])):
                    col1, col2 = st.columns([4, 1])
                    col1.caption(f"{item['timestamp']}: {textwrap.shorten(item['query'], 50)}")
                    if col2.button("🔄", key=f"reload_{idx}", help="Reload this query"):
                        return item["query"]
    return None


def display_statistics_sidebar() -> None:
    """Display statistics in sidebar."""
    with st.sidebar:
        st.header("📊 Statistics")

        if sss.research_full_report:
            report = sss.research_full_report
            st.metric("Research Cost", f"${report.costs:.4f}")
            st.metric("Sources Found", len(report.sources))
            st.metric("Images Found", len(report.images))
            st.metric("Log Entries", len(sss.log_entries))
        else:
            st.info("Run a search to see statistics")


def display_report_tabs(research_full_report: Any) -> None:
    """Display research results in organized tabs.

    Args:
        research_full_report: Research report object from GPT Researcher
    """
    report_tab, context_tab, image_tab, sources_tab, stats_tab = st.tabs(
        ["📄 Report", "🔍 Context", "🖼️ Images", "🔗 Sources", "📊 Statistics"]
    )

    # Report tab
    with report_tab:
        if research_full_report and research_full_report.report:
            sss.web_research_result = research_full_report.report
            st.markdown(research_full_report.report)
        else:
            st.info("Report will appear here after research completes")

    # Context tab
    with context_tab:
        if research_full_report and research_full_report.context:
            st.markdown(research_full_report.context)
        else:
            st.info("Context information will appear here")

    # Images tab
    with image_tab:
        if research_full_report and research_full_report.images:
            nb_col: Final = 4
            st.caption(f"Found {len(research_full_report.images)} images")

            image_cols = st.columns(nb_col)
            for index, image_path in enumerate(research_full_report.images):
                with image_cols[index % nb_col]:
                    try:
                        st.image(image_path, caption=f"Image {index + 1}", width="stretch")
                    except Exception as e:
                        st.warning(f"Cannot display image: {image_path[:50]}...")
                        logger.warning(f"Image display error: {e}")
        else:
            st.info("No images found in this research")

    # Sources tab
    with sources_tab:
        if research_full_report and research_full_report.sources:
            st.caption(f"Found {len(research_full_report.sources)} sources")

            source_data = []
            for idx, s in enumerate(research_full_report.sources, 1):
                source_data.append(
                    {
                        "No.": idx,
                        "Title": s.get("title", "N/A"),
                        "URL": s.get("url", ""),
                    }
                )

            df = pd.DataFrame(source_data)
            st.dataframe(
                df,
                width="stretch",
                hide_index=True,
                column_config={
                    "URL": st.column_config.LinkColumn("URL", display_text="Open"),
                },
            )
        else:
            st.info("No sources found")

    # Stats tab
    with stats_tab:
        if research_full_report:
            col1, col2, col3 = st.columns(3)
            col1.metric("💰 Research Cost", f"${research_full_report.costs:.4f}")
            col2.metric("🔗 Sources", len(research_full_report.sources))
            col3.metric("🖼️ Images", len(research_full_report.images))

            st.divider()

            st.subheader("Detailed Statistics")
            stats_df = pd.DataFrame(
                [
                    {
                        "Metric": "Total Sources",
                        "Value": str(len(research_full_report.sources)),
                    },
                    {
                        "Metric": "Total Images",
                        "Value": str(len(research_full_report.images)),
                    },
                    {
                        "Metric": "Research Cost",
                        "Value": f"${research_full_report.costs:.4f}",
                    },
                    {
                        "Metric": "Log Entries",
                        "Value": str(len(sss.log_entries)),
                    },
                ]
            )
            st.dataframe(stats_df, width="stretch", hide_index=True)
        else:
            st.info("Statistics will appear here after research completes")


def generate_pdf_report() -> None:
    """Generate and provide PDF download for the research report."""
    if "web_research_result" in sss and sss.web_research_result:
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmpfile:
                md2pdf(
                    Path(tmpfile.name),
                    raw=sss.web_research_result,
                )
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    st.download_button(
                        "📥 Download PDF Report",
                        data=Path(tmpfile.name).read_bytes(),
                        file_name=f"gptr_report_{timestamp}.pdf",
                        mime="application/pdf",
                        help="Download the full research report as PDF",
                        width="stretch",
                    )
        except Exception as e:
            st.error(f"❌ Failed to generate PDF: {e}")
            logger.error(f"PDF generation error: {e}", exc_info=True)


async def run_research(search_input: str, config_name: str, log_handler: CustomLogsHandler) -> None:
    """Execute the research process with error handling.

    Args:
        search_input: Research query
        config_name: Configuration profile name
        log_handler: Log handler for displaying progress
    """
    try:
        # Mark as researching
        sss.is_researching = True

        # Prepare research parameters
        research_params = {
            "query": search_input,
            "config_name": config_name,
            "websocket_logger": log_handler,
        }

        # Run research
        with st.spinner("🔍 GPT Researcher is working..."):
            sss.research_full_report = await run_gpt_researcher(**research_params)
            await log_handler.write_log("✅ Research completed successfully!")

            # Add to history
            sss.research_history.append(
                {
                    "query": search_input,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "config": config_name,
                }
            )

    except Exception as e:
        error_msg = f"❌ Research failed: {str(e)}"
        st.error(error_msg)
        logger.error(f"Research execution error: {e}", exc_info=True)
        await log_handler.write_log(error_msg)
        sss.research_full_report = None

    finally:
        sss.is_researching = False


async def main() -> None:
    """Main async function handling the Streamlit UI and search operations."""
    # Display sidebar configuration
    config_name = display_configuration_section()
    display_how_it_works()

    # Check for reloaded query from history
    reloaded_query = display_research_history()

    display_statistics_sidebar()

    # Main content area
    st.markdown("### 🔎 Research Query")
    st.caption("Enter your research question below or select from sample queries")

    # Sample queries selector
    sample_search = st.selectbox(
        "Sample Queries",
        options=[""] + SAMPLE_SEARCH,
        index=0,
        help="Select a sample query or enter your own",
        label_visibility="collapsed",
    )

    # Main form for search input
    with st.form("search_form", clear_on_submit=False):
        # Use reloaded query if available, otherwise use sample
        default_value = reloaded_query if reloaded_query else (sample_search if sample_search else "")

        search_input = st.text_area(
            "Your Research Query",
            height=100,
            placeholder="Enter your research query here... (e.g., 'What are the latest developments in quantum computing?')",
            value=default_value,
            help="Enter a detailed research question for GPT Researcher to investigate",
            label_visibility="collapsed",
        )

        col1, col2, col3, col4 = st.columns([2, 2, 1, 1])

        # use_cache = col1.checkbox(
        #     "Use Cache",
        #     value=True,
        #     help="Use cached results if available to save time and costs",
        # )

        submitted = col2.form_submit_button(
            "🚀 Start Research",
            disabled=not search_input or sss.is_researching,
            width="stretch",
            type="primary",
        )

        clear_button = col3.form_submit_button(
            "🗑️ Clear",
            width="stretch",
        )

        if clear_button:
            clear_research()
            st.rerun()

    # Research execution
    if submitted and search_input:
        st.divider()

        # Create status widget for real-time updates
        status_widget = st.status("🔍 Initializing research...", expanded=True)

        # Initialize log handler with status widget
        log_handler = CustomLogsHandler(status_widget)

        # Run research
        await run_research(search_input, config_name, log_handler)

        # Update status to complete
        if sss.research_full_report:
            status_widget.update(label="✅ Research completed!", state="complete", expanded=False)

    # Display results if available
    if sss.research_full_report:
        st.divider()

        # Display research logs in expander
        display_logs_expander()

        st.divider()
        st.success("✅ Research completed! View results in the tabs below.")

        display_report_tabs(sss.research_full_report)

        st.divider()
        # PDF export section
        st.markdown("### 📥 Export Results")
        generate_pdf_report()

        st.divider()
        # Additional actions
        st.markdown("### 🎯 Actions")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("🔄 New Research", width="stretch"):
                clear_research()
                st.rerun()

        with col2:
            if st.button("📋 Copy Report", width="stretch"):
                if sss.web_research_result:
                    st.code(sss.web_research_result, language="markdown")
                    st.success("Report text is displayed above for copying")

        with col3:
            # Clear history button
            if st.button("🗑️ Clear History", width="stretch"):
                sss.research_history = []
                st.success("History cleared")
                st.rerun()


# Run the async main function
try:
    asyncio.run(main())
except Exception as e:
    st.error(f"❌ Application error: {e}")
    logger.error(f"Application error: {e}", exc_info=True)
    if st.button("🔄 Restart Application"):
        st.rerun()
