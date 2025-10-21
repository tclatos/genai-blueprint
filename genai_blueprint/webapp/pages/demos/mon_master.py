"""Demo of Semantic Search."""

# cSpell: disable

import timeit
from pathlib import Path

import pandas as pd
import streamlit as st
from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.runnables import Runnable
from streamlit import session_state as sss

try:
    import src.demos.mon_master_search.search as master_search
    from genai_tk.utils.config_mngr import global_config

    from genai_blueprint.demos.mon_master_search.loader import add_accronym
    from genai_blueprint.demos.mon_master_search.model_subset import EXAMPLE_QUERIES
except Exception as ex:
    st.error(f"Problem loading demo: {ex} ")
    st.stop()

LLM = "gemini_pro_google"


DEFAULT_RESULT_COUNT = 100

################################
#  UI
################################

title_col1, title_col2 = st.columns([2, 1])

logo_eviden = str(Path.cwd() / "genai_blueprint/webapp/static/eviden-logo-white.png")

st.logo(logo_eviden)

title_col1.title("Recherche Sémantique de Masters")
title_col2.image(logo_eviden, width=250)


# Check if spacy is available
if "spacy_available" not in sss:
    try:
        master_search.get_bm25_retriever()

        sss.spacy_available = True
    except Exception:
        sss.spacy_available = False

if not sss.spacy_available:
    st.warning("Spacy model is not installed. Keyword and Hybrid search modes are disabled..")


with st.sidebar:
    # Only show search method options if spacy is available
    if sss.spacy_available:
        search_method = st.radio("Select Search Method:", ["Vector", "Keyword", "Hybrid"], index=2)
        if search_method == "Hybrid":
            ratio_spinner = st.slider("Keyword  / Vector ratio", min_value=0.0, max_value=1.0, value=0.5, step=0.1)
    else:
        search_method = "Vector"

    default_embeddings = global_config().get_str("embeddings.models.default")
    embeddings_model = st.radio(
        "Embedding Model:",
        options=[
            default_embeddings,
            "mistral_1024_edenai",
            "ada_002_edenai",
            "camembert_large_local",
            "solon_large_local",
        ],
        captions=[
            "Default model",
            "Mistral 1024",
            "OpenAI Ada 002",
            "Large model for French",
            "SOTA model for French",
        ],
        index=0,
    )
    result_count = int(
        st.number_input(
            "Nombre de parcours recherchés",
            min_value=1,
            max_value=100,
            value=DEFAULT_RESULT_COUNT,
        )
    )

example = st.selectbox("Examples:", EXAMPLE_QUERIES, index=None)
with st.form(key="form"):
    user_input = st.text_area(label="Recherche:", value=example or "", height=70)
    submit_clicked = st.form_submit_button("Rechercher")


@st.cache_resource(show_spinner="Load vector store...")
def _get_sparse_retriever(embeddings_model_id: str) -> Runnable:
    return master_search.get_sparse_retriever(embeddings_model_id)


@st.cache_resource(show_spinner="index documents for keyword search...")
def _get_bm25_retriever() -> Runnable:
    return master_search.get_bm25_retriever()


@st.cache_resource(show_spinner="load hybrid model...")
def get_ensemble_retriever(embeddings_model_id: str, ratio_sparse: float) -> EnsembleRetriever:
    return master_search.get_ensemble_retriever(embeddings_model_id, ratio_sparse)


df = pd.DataFrame()
known_set: set[str] = set()
if submit_clicked:
    assert embeddings_model is not None
    try:
        if search_method == "Vector":
            retriever = _get_sparse_retriever(embeddings_model)
        elif search_method == "Keyword":
            retriever = _get_bm25_retriever()
        elif search_method == "Hybrid":
            retriever = get_ensemble_retriever(embeddings_model, ratio_sparse=ratio_spinner)
    except ImportError as e:
        st.error(f"Error: {str(e)}. Please ensure all required dependencies are installed.")
        st.stop()

    #  quick and dirty hack to have enough results
    count = result_count * 2

    config = {"configurable": {"k": count, "search_kwargs": {"k": count}}}
    user_input = "query : " + add_accronym(user_input)  # supposed to work well for Solon Embeddings

    start_time = timeit.default_timer()
    result = retriever.invoke(user_input, config=config)  # type: ignore
    #    print(user_input, result)
    delta_t = timeit.default_timer() - start_time
    for doc in result:
        # obj = json.loads(doc.page_content)
        intitule = doc.page_content.removeprefix("intitulé: ")
        eta = doc.metadata.get("eta_name")
        inm = doc.metadata.get("source")
        for_intitule = doc.metadata["for_intitule"]
        key = doc.metadata["for_intitule"] + doc.metadata["eta_uai"]
        parcours = intitule.partition('" : ')[2]
        parcours = parcours.replace("parcours: ", "=> ").replace("libelés:", " -- ")

        row = {
            "Intitulé formation:": for_intitule,
            "Formation => Parcours -- libelés": parcours.lower(),
            "ETA": eta,
            "INM(P)": inm,
            "Content": doc.page_content,
        }
        if key not in known_set:
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        known_set.add(key)

    st.dataframe(df)
    st.write(f"search duration : {delta_t:9.5f} s")
