"""Deep Search Agent using GPT Researcher.

This module provides a simplified Streamlit interface for running
GPT Researcher searches with configurable parameters.
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
from md2pdf import md2pdf
from streamlit import session_state as sss

from genai_blueprint.utils.streamlit.auto_scroll import scroll_to_here

st.title("GPT Researcher Playground")

SAMPLE_SEARCH = [
    "What are the ethical issues with AI autonomous agents?",
    "What is the architecture of SmolAgents and how it compare with LangGraph?",
    "What are the Agentic AI solutions announced by AWS, Google, Microsoft, SalesForce, Service Now, UI Path, SAP, and other major software editors",
    "Define what is Agentic AI",
]

# Initialize session state
if "log_entries" not in sss:
    sss.log_entries = deque(maxlen=100)
if "research_full_report" not in sss:
    sss.research_full_report = None

# Configuration area
with st.expander("Search Configuration", expanded=True):
    gpt_researcher_config = global_config().merge_with("config/components/gpt_researcher.yaml")
    available_configs = list(gpt_researcher_config.get("gpt_researcher").keys())
    config_name = st.selectbox(
        "Research Configuration",
        options=available_configs,
        index=0,
        help="Select a preconfigured research profile",
    )

# How it works popover
with st.popover("How it works", width="content"):
    c21, c22 = st.columns([7, 12])
    c21.write("Normal Research")
    c21.image(
        "https://private-user-images.githubusercontent.com/13554167/333804350-4ac896fd-63ab-4b77-9688-ff62aafcc527.png?jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3NDY2NDgzODEsIm5iZiI6MTc0NjY0ODA4MSwicGF0aCI6Ii8xMzU1NDE2Ny8zMzM4MDQzNTAtNGFjODk2ZmQtNjNhYi00Yjc3LTk2ODgtZmY2MmFhZmNjNTI3LnBuZz9YLUFtei1BbGdvcml0aG09QVdTNC1ITUFDLVNIQTI1NiZYLUFtei1DcmVkZW50aWFsPUFLSUFWQ09EWUxTQTUzUFFLNFpBJTJGMjAyNTA1MDclMkZ1cy1lYXN0LTElMkZzMyUyRmF3czRfcmVxdWVzdCZYLUFtei1EYXRlPTIwMjUwNTA3VDIwMDEyMVomWC1BbXotRXhwaXJlcz0zMDAmWC1BbXotU2lnbmF0dXJlPTgwM2RmODQwNjVmZTU0MjI4YTljODJjMzgxY2U1N2MwOGZjNWEyOGM3OTM5ZjNmNmEzMDEwYTg0ZjE5YzllYzUmWC1BbXotU2lnbmVkSGVhZGVycz1ob3N0In0.SsI3BqipPrR8mL8soiWF0mlCbnXxNnzTip6F4wgY9aM"
    )
    c22.write("Deep Research")
    c22.image("https://github.com/user-attachments/assets/eba2d94b-bef3-4f8d-bbc0-f15bd0a40968")

# Query input area
sample_search = st.selectbox("Sample queries:", SAMPLE_SEARCH, index=None)


class CustomLogsHandler:
    """Handles real-time logging display in Streamlit UI."""

    def __init__(self, log_container, height=200) -> None:
        self.log_container = log_container.container(height=height)

    async def send_json(self, data: dict[str, Any]) -> None:
        if "log_entries" not in sss:
            sss.log_entries = deque(maxlen=100)
        log_type = data.get("type")
        if log_type == "logs":
            sss.log_entries.append(data)
            with self.log_container:
                line = textwrap.shorten(data["output"], 120)
                st.text(line)
                scroll_to_here()

    async def write_log(self, line: str) -> None:
        """Write a single log line to the streamlit container"""
        await self.send_json({"type": "logs", "output": line})


async def main() -> None:
    """Main async function handling the Streamlit UI and search operations."""

    with st.form("search_form"):
        search_input = st.text_area(
            "Your query",
            height=70,
            placeholder="Enter your research query here...",
            value=sample_search,
            label_visibility="collapsed",
        )

        col1, col2 = st.columns([1, 4])
        use_cache = col1.checkbox("Use cache", value=True, help="Use cached results if available")
        submitted = col2.form_submit_button("Start Research", disabled=not search_input, width="stretch")

        if submitted and search_input:
            log_tab, report_tab, context_tab, image_tab, sources_tab, stats_tab = st.tabs(
                ["Log", "**Report**", "Context", "Images", "Sources", "Stats"]
            )

            log_handler = CustomLogsHandler(log_tab, 200)

            # Prepare research parameters
            research_params = {
                "query": search_input,
                "config_name": config_name,
                "websocket_logger": log_handler,
            }

            with st.spinner("GPT Researcher running..."):
                try:
                    sss.research_full_report = await run_gpt_researcher(**research_params)
                    await log_handler.write_log("🍾 The search report is ready!")
                except Exception as e:
                    st.error(f"Error during research: {str(e)}")
                    return

            research_full_report = sss.research_full_report
            if research_full_report:
                # Report tab
                sss.web_research_result = research_full_report.report
                report_tab.markdown(sss.web_research_result)

                # Context tab
                context_tab.markdown(research_full_report.context)

                # Images tab
                nb_col: Final = 4
                image_tab.write(f"Found images ({len(research_full_report.images)})")
                if research_full_report.images:
                    image_cols = image_tab.columns(nb_col)
                    for index, image_path in enumerate(research_full_report.images):
                        with image_cols[index % nb_col]:
                            try:
                                st.image(image_path, width=200, caption=f"Image {index + 1}")
                            except Exception:
                                st.write(f"Cannot display {image_path}")

                # Sources tab
                if research_full_report.sources:
                    source_data = [(s.get("url", ""), s.get("title", "")) for s in research_full_report.sources]
                    df = pd.DataFrame(source_data, columns=["URL", "Title"])
                    sources_tab.dataframe(df, width="stretch")
                else:
                    sources_tab.write("No sources found")

                # Stats tab
                stats_tab.metric("Research costs", f"${research_full_report.costs:.4f}")
                stats_tab.metric("Sources found", len(research_full_report.sources))
                stats_tab.metric("Images found", len(research_full_report.images))

    # PDF download button
    if "web_research_result" in sss and sss.web_research_result:
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmpfile:
                md2pdf(
                    tmpfile.name,
                    md_content=sss.web_research_result,
                    base_url=None,
                    css_file_path=None,
                )
                timestamp = datetime.now().strftime("%Y%m%d_%H%M")
                st.download_button(
                    "📄 Download PDF Report",
                    data=Path(tmpfile.name).read_bytes(),
                    file_name=f"gptr_report_{timestamp}.pdf",
                    mime="application/pdf",
                    help="Download the full research report as PDF",
                    width="stretch",
                )
        except Exception as e:
            st.error(f"Error generating PDF: {str(e)}")


asyncio.run(main())
