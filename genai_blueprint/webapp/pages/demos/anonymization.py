"""Streamlit page for data anonymization with Microsoft Presidio.

Demonstrates PII detection, anonymization, and reversible de-anonymization capabilities.
"""
# https://python.langchain.com/v0.1/docs/guides/productionization/safety/presidio_data_anonymization/

from typing import Any

import streamlit as st
from genai_tk.extra.custom_presidio_anonymizer import CustomizedPresidioAnonymizer
from genai_tk.utils.config_mngr import global_config
from loguru import logger
from pydantic import BaseModel, ConfigDict
from streamlit import session_state as sss

from genai_blueprint.webapp.ui_components.config_editor import edit_config_dialog

SPACY_MODEL = "en_core_web_sm"


class AnonymizationDemo(BaseModel):
    """Configuration for Presidio anonymization demo."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    anonymizer: Any = None


st.title("Data Anonymization")
st.caption("...using Microsoft Presidio")

CONF_YAML_FILE = "config/demos/presidio_anonymization.yaml"

# Configuration options
with st.sidebar:
    st.header("Configuration")

    # Add edit button for configuration
    if st.button(":material/edit: Edit Config", help="Edit anonymization configuration"):
        edit_config_dialog(CONF_YAML_FILE)

    # Load configuration from YAML
    config = global_config()
    analyzed_fields = config.get_list("anonymization_config.analyzed_fields")
    company_names = config.get_list("anonymization_config.company_names")
    product_names = config.get_list("anonymization_config.product_names")
    sample_texts = config.get_list("anonymization_config.examples")
    use_fuzzy_matching = config.get_bool("anonymization_config.fuzzy_matching", default=True)


# Initialize session state
config_hash = hash(str(analyzed_fields) + str(company_names) + str(product_names))
if "anon" not in sss or sss.get("config_hash") != config_hash:
    with st.spinner("Loading Spacy Model and initializing anonymizer..."):
        anonymizer = CustomizedPresidioAnonymizer(
            analyzed_fields=analyzed_fields,
            faker_seed=42,
            company_names=company_names,
            product_names=product_names,
            spacy_model=SPACY_MODEL,
        )

    sss.anon = AnonymizationDemo(anonymizer=anonymizer)
    sss.config_hash = config_hash

# Main layout
col1, col2 = st.columns(2)

with col1:
    st.subheader("Original Text")

    # Sample selector
    input_text = st.text_area("Enter text containing PII:", height=300, value=sample_texts[0])


with col2:
    if st.button("Anonymize Text", icon=":material/domino_mask:"):
        with st.spinner("Detecting and anonymizing PII..."):
            try:
                # Anonymize the text
                sss.anonymized_text = sss.anon.anonymizer.anonymize(input_text)
                sss.show_reversible = True
            except Exception as e:
                logger.exception(f"Anonymization failed: {e}")
                st.error(f"Anonymization error: {str(e)}")

    if "anonymized_text" in sss:
        st.subheader("Anonymized Text:")
        st.code(sss.anonymized_text, language="text", wrap_lines=True)

        if st.button("De-anonymize Text:"):
            try:
                # De-anonymize the text
                deanon_text = sss.anon.anonymizer.deanonymize(
                    sss.anonymized_text,
                    use_fuzzy_matching=use_fuzzy_matching,
                )
                st.subheader("🔓 De-anonymized Text")
                st.code(deanon_text, language="text", wrap_lines=True)
            except Exception as e:
                logger.error(f"De-anonymization failed: {e}")
                st.error(f"De-anonymization error: {str(e)}")

        with st.expander("Anonymization Mapping"):
            mapping = sss.anon.anonymizer.get_mapping()
            if mapping:
                st.json(mapping)
            else:
                st.info("No reversible mappings available")
