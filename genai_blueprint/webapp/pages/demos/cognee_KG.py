"""Cognee demonstration page with file upload and knowledge graph processing."""

import asyncio
import json
import tempfile
from pathlib import Path
from typing import BinaryIO, Callable, List

import cognee
import streamlit as st
import streamlit.components.v1 as components
from beartype.door import is_bearable
from cognee.api.v1.search import SearchType
from cognee.api.v1.visualize.visualize import visualize_graph
from devtools import debug  # noqa: F401
from genai_tk.extra.cognee_utils import get_search_type_description, set_cognee_config
from genai_tk.utils.config_mngr import global_config
from loguru import logger
from pydantic import BaseModel, ConfigDict
from streamlit import session_state as sss
from streamlit.delta_generator import DeltaGenerator
from upath import UPath

CogneeInputType = BinaryIO | list[BinaryIO] | str | list[str]  # Arguments accepted by cognee.add()


class CogneeDemoData(BaseModel):
    """Configuration for a Cognee demo preset."""

    name: str
    texts: List[str] = []
    example_queries: List[str] = []
    files: List[UPath] = []
    ontology: UPath | None = None
    uploaded_file_paths: List[UPath] = []

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def all_data(self) -> list[str]:
        """Return combined texts and file paths for processing."""
        return self.texts + [str(f) for f in self.files + self.uploaded_file_paths]

    def has_content(self) -> bool:
        """Check if there's any content to process."""
        return bool(self.all_data())

    def display_content(self):
        """Display texts and files in tabs."""
        items = []
        for idx, text in enumerate(self.texts):
            items.append(("text", text, f"Text {idx + 1}"))
        for file_path in self.files + self.uploaded_file_paths:
            try:
                if file_path.suffix.lower() == ".pdf":
                    items.append(("pdf", file_path, f"PDF: {file_path.name}"))
                else:
                    content = file_path.read_text()
                    items.append(("text_content", content, f"File: {file_path.name}"))
            except Exception as e:
                items.append(("error", f"Error loading {file_path}: {e}", f"File: {file_path.name}"))
        return items


async def process_files(demo_data: CogneeDemoData, node_set: list[str] | None) -> bool:
    """Process demo data through cognee pipeline."""
    if not demo_data.has_content():
        return False

    try:
        await _process_documents(demo_data=demo_data, node_set=node_set)
    except Exception as e:
        logger.error(f"Error processing files: {e}")
        return False
    return True


async def query_knowledge_graph(query: str, search_type: SearchType) -> list:
    """Query the knowledge graph with specified search type."""
    try:
        results = await cognee.search(query_type=SearchType.INSIGHTS, query_text=query)
        return results
    except Exception as e:
        logger.error(f"Error querying knowledge graph: {e}")
        return [f"error: {e}"]


async def display_graph_visualization():
    """Display the knowledge graph visualization."""
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as tmp_file:
            tmp_path = tmp_file.name
            html_content = await visualize_graph(tmp_path)
            components.html(html_content, height=600, scrolling=True)
    except Exception as e:
        st.error(f"Error displaying graph: {e}")


def load_demos_from_config() -> List[CogneeDemoData]:
    """Load demo configurations from global config."""
    try:
        config = global_config()
        demos = []
        for demo_name in config.get_dict("cognee-demo").keys():
            texts = config.get_list(f"cognee-demo.{demo_name}.texts", [])
            example_queries = config.get_list(f"cognee-demo.{demo_name}.example_queries", [])
            files = config.get_list(f"cognee-demo.{demo_name}.files", [])
            files_url = [UPath(f) for f in files]
            ontology = config.get_str(f"cognee-demo.{demo_name}.ontology", "")

            ontology_url = UPath(ontology) if ontology else None
            demos.append(
                CogneeDemoData(
                    name=demo_name, texts=texts, example_queries=example_queries, files=files_url, ontology=ontology_url
                )
            )
        return demos
    except Exception as e:
        logger.error(f"Error loading demos from config: {e}")
        return []


cognee_demos = load_demos_from_config()


async def _render_input_section():
    """Render the input section for file upload or demo selection."""
    TEXT1 = "Upload Files"
    TEXT2 = "Predefined demo"
    option = st.radio(
        "Choose input method:",
        [TEXT1, TEXT2],
        horizontal=True,
        key="input_option",
    )

    if option == TEXT1:
        await _handle_file_upload()
    elif option == TEXT2:
        await _handle_demo_selection()


async def _handle_file_upload():
    """Handle file upload and processing."""
    uploaded_files = st.file_uploader(
        "Choose files:",
        accept_multiple_files=True,
        type=["txt", "pdf", "docx", "md", "json"],
        key="file_uploader_main",
    )
    if uploaded_files:
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = []
            for uploaded_file in uploaded_files:
                file_path = Path(tmpdir) / uploaded_file.name
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                paths.append(file_path)

            demo_data = CogneeDemoData(name="uploaded_files", uploaded_file_paths=[UPath(p) for p in paths])
            await _handle_cognify_process(
                demo_data=demo_data,
                process_func=process_files,
                clear_before_key="clear_before_upload",
            )


async def _process_documents(demo_data: CogneeDemoData, node_set: list[str] | None = None):
    dataset_name = demo_data.name
    data = demo_data.all_data()
    await cognee.add(data=data, node_set=node_set, dataset_name=dataset_name)
    await cognee.cognify(datasets=[dataset_name])
    return True


async def _handle_demo_selection():
    """Handle demo selection and processing."""
    if not cognee_demos:
        st.warning("No demos found in config/demos/cognee_kg.yaml")
        return

    demo_names = [demo.name for demo in cognee_demos]
    selected_demo_name = st.pills("Select a demo:", demo_names, key="demo_select2")

    if selected_demo_name is None:
        st.info("👆 Select a demo above to see its contents")
        return

    selected_demo = next(d for d in cognee_demos if d.name == selected_demo_name)
    sss.selected_demo = selected_demo

    if selected_demo.ontology:
        st.write(f"ontology: {selected_demo.ontology}")

    # Display content
    content_items = selected_demo.display_content()
    if content_items:
        tabs = st.tabs([title for _, _, title in content_items])
        for idx, (content_type, content, _) in enumerate(content_items):
            with tabs[idx]:
                if content_type in ["text", "text_content"]:
                    st.text_area("", value=content, height=150, key=f"demo_content_{idx}", disabled=True)
                elif content_type == "pdf":
                    st.pdf(content)
                elif content_type == "error":
                    st.error(content)
                else:
                    st.write(f"Cannot display: {content_type}")

    if not selected_demo.has_content():
        st.warning("This demo has no texts or files to process")
        return

    await _handle_cognify_process(
        demo_data=selected_demo,
        process_func=_process_documents,
        clear_before_key="clear_before_demo",
    )


async def _handle_cognify_process(demo_data: CogneeDemoData, process_func: Callable, clear_before_key: str = False):
    """Common handler for cognify operations with optional data clearing."""
    clear_before = st.checkbox("Clear stored data first", value=False, key=clear_before_key)
    if st.button("🚀 Cognify !", type="primary"):
        if clear_before:
            with st.spinner("Clearing stored data..."):
                try:
                    await cognee.prune.prune_data()
                    await cognee.prune.prune_system(metadata=True)
                    st.success("✅ Stored data cleared")
                except Exception as e:
                    logger.error(f"Error clearing data: {e}")
                    st.error(f"❌ Failed to clear stored data: {e}")
                    return

        with st.spinner("Processing through cognee pipeline..."):
            try:
                success = await process_func(demo_data)
                if success:
                    sss.processing_complete = True
                    sss.graph_generated = True
                    st.success("✅ Knowledge graph generated successfully!")
                    st.rerun()
                else:
                    st.error("❌ Failed to process data")
            except Exception as e:
                logger.error(f"Error processing data: {e}")
                st.error(f"❌ Failed to process data: {e}")


async def _render_results_section():
    """Render the results section with query and visualization."""
    st.success("✅ Knowledge graph generated! You can now query and explore the data.")

    # Show texts and files in an expander if available
    if sss.selected_demo:
        with st.expander("📄 Demo Content (Texts and Files)", expanded=False):
            content_items = sss.selected_demo.display_content()
            if content_items:
                tabs = st.tabs([title for _, _, title in content_items])
                for idx, (content_type, content, _) in enumerate(content_items):
                    with tabs[idx]:
                        if content_type in ["text", "text_content"]:
                            st.text_area("", value=content, height=150, key=f"results_content_{idx}", disabled=True)
                        elif content_type == "pdf":
                            st.pdf(content)
                        elif content_type == "error":
                            st.error(content)

    col1, col2 = st.columns([1, 1])

    with col1:
        await _render_query_section()
    with col2:
        st.header("🕸️ Knowledge Graph Visualization")
        await display_graph_visualization()


def _display_input_form(w: DeltaGenerator, suggested_queries: list[str], value: str = "") -> tuple[str, bool]:
    """Displays the input form and returns user input."""
    with w.form("my_form", border=False):
        cf1, cf2 = st.columns([15, 1], vertical_alignment="bottom")
        prompt = cf1.text_area(
            "Your task",
            height=68,
            placeholder="Enter or modify your query here...",
            value=value,
            label_visibility="collapsed",
        )
        submitted = cf2.form_submit_button(label="", icon=":material/send:")
    return prompt, submitted


async def _render_query_section():
    """Render the query section for knowledge graph exploration."""
    st.header("🔍 Query Knowledge Graph")

    # Build list of suggested queries

    suggested_queries = []
    if sss.selected_demo and cognee_demos:
        suggested_queries.extend(sss.selected_demo.example_queries)

    sample_search = st.selectbox(
        label="Sample queries",
        placeholder="Select an example (optional)",
        options=suggested_queries,
        index=None,
        key="sample_query_select",
    )

    col1, col2 = st.columns([1, 4])
    search_type = col1.selectbox(
        "Search Type:",
        options=[  # from https://docs.cognee.ai/core-concepts/main-operations/search
            ("RAG Completion", SearchType.RAG_COMPLETION),
            ("Graph Completion", SearchType.GRAPH_COMPLETION),
            ("Insights", SearchType.INSIGHTS),
            ("Summaries", SearchType.SUMMARIES),
            ("Chunks", SearchType.CHUNKS),
            ("Graph Summary Completion", SearchType.GRAPH_SUMMARY_COMPLETION),
            ("Code", SearchType.CODE),
            ("Cypher", SearchType.CYPHER),
            ("Natural Language", SearchType.NATURAL_LANGUAGE),
            ("Graph Completion CoT", SearchType.GRAPH_COMPLETION_COT),
            ("Graph Completion Context Extension", SearchType.GRAPH_COMPLETION_CONTEXT_EXTENSION),
            ("Feeling Lucky", SearchType.FEELING_LUCKY),
            ("Feedback", SearchType.FEEDBACK),
        ],
        format_func=lambda x: x[0],
        key="search_type_select",
        label_visibility="collapsed",
        placeholder="Search type",
    )
    # Display the description
    st.caption(f"🔍 {get_search_type_description(search_type[1])}")

    query, submitted = _display_input_form(
        col2,
        suggested_queries,
        value=sample_search or "",
    )

    if submitted:
        if not query:
            st.warning("Please enter a query")
        else:
            with st.spinner("Searching knowledge graph..."):
                try:
                    results = await cognee.search(query_type=search_type[1], query_text=query)
                except Exception as ex:
                    logger.exception(ex)
                    st.error(f"error: {ex}")
                    return
                # results_type = infer_hint(results)

                if is_bearable(results, list[dict]) and results:
                    st.success("Results found!")
                    # Define fields to exclude
                    fields_to_exclude = {"id", "source_node_id", "target_node_id", "created_at", "updated_at"}

                    # Filter out specified fields from each dict
                    filtered_results = []
                    for dict_item in results:
                        filtered_dict = {k: v for k, v in dict_item.items() if k not in fields_to_exclude}
                        filtered_results.append(filtered_dict)

                    st.dataframe(filtered_results)
                elif is_bearable(results, list[str]) and results:
                    st.success("Results found!")
                    for r in results:
                        st.write(r)
                elif is_bearable(results, list[tuple[dict, dict, dict]]) and results:
                    st.success("Results found (a list of 3-tuples: from, relation, to)!")

                    # Define fields to exclude
                    fields_to_exclude = {"id", "source_node_id", "target_node_id", "created_at", "updated_at"}

                    # Create dataframe with from, relation, to columns
                    dataframe_rows = []
                    for from_dict, relation_dict, to_dict in results:
                        # Filter out specified fields from each dict
                        filtered_from = {k: v for k, v in from_dict.items() if k not in fields_to_exclude}
                        filtered_relation = {k: v for k, v in relation_dict.items() if k not in fields_to_exclude}
                        filtered_to = {k: v for k, v in to_dict.items() if k not in fields_to_exclude}

                        row = {
                            "from": json.dumps(filtered_from),
                            "relation": json.dumps(filtered_relation),
                            "to": json.dumps(filtered_to),
                        }
                        dataframe_rows.append(row)

                    if dataframe_rows:
                        st.dataframe(dataframe_rows)
                    else:
                        st.info("No data found in tuples")
                elif is_bearable(results, list[tuple[dict, ...]]) and results:
                    st.success("Results found (a list of tuples) !")
                    # Define fields to exclude
                    fields_to_exclude = {"id", "source_node_id", "target_node_id", "created_at", "updated_at"}

                    # Convert each dict in each tuple to a row with JSON-formatted cells
                    rows = []
                    for tuple_item in results:
                        for dict_item in tuple_item:
                            # Filter out specified fields
                            filtered_dict = {k: v for k, v in dict_item.items() if k not in fields_to_exclude}
                            json_row = {k: json.dumps(v) for k, v in filtered_dict.items()}
                            rows.append(json_row)

                    if rows:
                        st.dataframe(rows)
                    else:
                        st.info("No data found in tuples")
                else:
                    st.success("Results found! ")
                    st.json(results)


async def main():
    """Main Streamlit page for Cognee demonstration."""
    st.set_page_config(page_title="Cognee Demo", page_icon="🧠", layout="wide")

    st.title("🧠 Knowledge Graph Demo")
    st.markdown("Upload documents or use predefined demos to explore knowledge graph insights")

    # Initialize cognee
    set_cognee_config()

    # Initialize session state
    if "processing_complete" not in sss:
        sss.processing_complete = False
    if "graph_generated" not in sss:
        sss.graph_generated = False
    if "show_upload_popup" not in sss:
        sss.show_upload_popup = False
    if "selected_demo" not in sss:
        sss.selected_demo = None

    if not sss.processing_complete:
        await _render_input_section()
    if sss.processing_complete:
        await _render_results_section()


if __name__ == "__main__":
    # Handle both direct execution and Streamlit execution
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(main())
        else:
            asyncio.run(main())
    except RuntimeError:
        asyncio.run(main())
