"""Advanced RAG implementation using LangGraph's StateGraph API.

Implements a robust RAG pipeline with:
- Dynamic query routing
- Document relevance grading
- Answer generation with hallucination detection
- Web search fallback
"""

import sys
from enum import Enum
from operator import itemgetter
from typing import Any, Literal

from dotenv import load_dotenv
from genai_tk.core.chain_registry import Example, RunnableItem, register_runnable
from genai_tk.core.embeddings_store import EmbeddingsStore
from genai_tk.core.llm_factory import get_llm
from genai_tk.core.prompts import def_prompt
from genai_tk.tools.langchain.web_search_tool import basic_web_search
from langchain_classic.output_parsers import EnumOutputParser
from langchain_classic.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders.web_base import WebBaseLoader
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import Runnable, RunnableLambda
from langgraph.graph import END, StateGraph
from langgraph.pregel import Pregel
from loguru import logger
from typing_extensions import TypedDict

"""
Suggested extensions :
- Rewrite query as in https://github.com/langchain-ai/langgraph/blob/main/examples/rag/langgraph_adaptive_rag.ipynb

"""

load_dotenv(verbose=True)

LLM_ID = None


class YesOrNo(Enum):
    YES = "yes"
    NO = "no"


class DataRoute(Enum):
    WEB_SEARCH = "web_search"
    VECTOR_STORE = "vectorstore"


yesno_enum_parser = EnumOutputParser(enum=YesOrNo)
to_lower = RunnableLambda(lambda x: x.content.lower())  # type: ignore


class GraphState(TypedDict, total=False):
    """Represents the state of our graph."""

    question: str  # the question
    generation: str  # LLM generation
    web_search: str  # whether to add search
    documents: list[Document]  # list of documents


# Routes question to either vector store or web search
def question_router() -> Runnable[Any, DataRoute]:
    parser = EnumOutputParser(enum=DataRoute)

    system_prompt = """
        You are an expert at routing a user question to a vectorstore or web search.
        Use the vectorstore for questions on LLM  agents, prompt engineering, and adversarial attacks.
        You do not need to be stringent with the keywords in the question related to these topics.
        Otherwise, use web-search.
        Give a binary choice 'web_search' or 'vectorstore' based on the question with no permeable or explanation.

        """
    user_prompt = """
        Question to route: {question} \n
        Instructions: {instructions} """

    prompt = def_prompt(system_prompt, user_prompt).partial(instructions=parser.get_format_instructions())
    question_router = prompt | get_llm(llm_id=LLM_ID) | parser
    return question_router  # type: ignore


def route_question(state: GraphState) -> Literal["websearch", "vectorstore"]:
    """Entry point that routes question to appropriate search method.

    Input state:
        question (str): The user's question

    Returns:
        str: Next node name ('websearch' or 'vectorstore')

    Side effects:
        Logs routing decision
    """
    logger.debug("---ROUTE QUESTION---")
    question = state["question"]
    source = question_router().invoke({"question": question})
    logger.debug(question, source)
    if source == DataRoute.WEB_SEARCH:
        logger.debug("---ROUTE QUESTION TO WEB SEARCH---")
        return "websearch"
    elif source == DataRoute.VECTOR_STORE:
        logger.debug("---ROUTE QUESTION TO RAG---")
        return "vectorstore"
    else:
        raise Exception("Bug: unknown source")


# Performs web search and stores results
def web_search(state: GraphState) -> GraphState:
    logger.debug("---WEB SEARCH---")
    question = state["question"]
    documents = state.get("documents") or []

    web_results = basic_web_search(question)

    if documents is not None:
        documents.append(web_results)
    else:
        documents = [web_results]
    return {"documents": documents, "question": question}


# Functions and node to retrive read data from Internet and put it in the vector store
# Creates retriever with pre-loaded documents if empty
def retriever() -> BaseRetriever:
    urls = [
        "https://lilianweng.github.io/posts/2023-06-23-agent/",
        "https://lilianweng.github.io/posts/2023-03-15-prompt-engineering/",
        "https://lilianweng.github.io/posts/2023-10-25-adv-attack-llm/",
    ]

    embeddings_store = EmbeddingsStore.create_from_config("in_memory_chroma")
    vectorstore = embeddings_store.get()

    print(embeddings_store.document_count())
    if embeddings_store.document_count() == 0:
        logger.info("indexing documents...")

        docs = [WebBaseLoader(url).load() for url in urls]
        docs_list = [item for sublist in docs for item in sublist]
        text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(chunk_size=250, chunk_overlap=0)
        doc_splits = text_splitter.split_documents(docs_list)
        vectorstore.add_documents(doc_splits)  # Add to vectorDB
    retriever = vectorstore.as_retriever()
    return retriever


# Retrieves documents relevant to the question from vector store
def retrieve(state: GraphState) -> GraphState:
    logger.debug("---RETRIEVE---")
    question = state["question"]

    # Retrieval
    documents = retriever().invoke(question)
    return {"documents": documents, "question": question}


# Generates an answer to the question using retrieved context
def rag_chain() -> Runnable[Any, str]:
    system_prompt = """
        You are an assistant for question-answering tasks.
        Use the following pieces of retrieved context to answer the question. If you don't know the answer, just say that you don't know.
        Use three sentences maximum and keep the answer concise."""
    user_prompt = """
        Question: {question}
        Context: {context}
        Answer: """
    logger.debug("Rag chain'")
    prompt = def_prompt(system=system_prompt, user=user_prompt)
    return prompt | get_llm(llm_id=LLM_ID) | StrOutputParser()


# Generates answer using RAG chain
def generate(state: GraphState) -> GraphState:
    logger.debug("---GENERATE---")
    question = state["question"]
    documents = state["documents"]

    # RAG generation
    generation = rag_chain().invoke({"context": documents, "question": question})
    return {"documents": documents, "question": question, "generation": generation}


# Evaluates if generated answer is useful for the question
def answer_grader() -> Runnable[Any, YesOrNo]:
    system_prompt = """
        You are a grader assessing whether an answer is useful to resolve a question.
        Evaluate whether the answer is useful to resolve a question.
        Answer only by 'yes' or 'no', without any other comment.\n"""
    user_prompt = """
        Here are the answer:
        \n---  {generation} \n---
        Here is the question: {question} \n
        Instructions: {instructions}
        """
    prompt = def_prompt(system_prompt, user_prompt).partial(instructions=yesno_enum_parser.get_format_instructions())
    return prompt | get_llm(llm_id=LLM_ID) | to_lower | yesno_enum_parser  # type: ignore


# Grades whether a retrieved document is relevant to the question
def retrieval_grader() -> Runnable[Any, YesOrNo]:
    ### Retrieval Grader

    system_prompt = """
        You are a grader assessing relevance  of a retrieved document to a user question.
        If the document contains keywords related to the user question, grade it as relevant.
        It does not need to be a stringent test. The goal is to filter out erroneous retrievals. \n
        Evaluate whether the document is relevant to the question. Answer only by 'yes' or 'no', without any other comment.
        """
    user_prompt = """
        Here is the retrieved document:
        --- \n {document} ---\n\n
        Here is the user question: {question} \n,
        Instructions: {instructions}"""

    prompt = def_prompt(system_prompt, user_prompt).partial(instructions=yesno_enum_parser.get_format_instructions())

    logger.debug("Retrieval Grader'")
    retrieval_grader = prompt | get_llm(llm_id=LLM_ID) | to_lower | yesno_enum_parser
    return retrieval_grader  # type: ignore


# Filters documents by relevance to the question
def grade_documents(state: GraphState) -> GraphState:
    logger.debug("---CHECK DOCUMENT RELEVANCE TO QUESTION---")
    question = state["question"]
    documents = state["documents"]

    # Score each doc
    filtered_docs = []
    web_search = "No"
    for d in documents:
        grade = retrieval_grader().invoke({"question": question, "document": d.page_content})
        # Document relevant
        if grade == YesOrNo.YES:
            logger.debug("---GRADE: DOCUMENT RELEVANT---")
            filtered_docs.append(d)
        # Document not relevant
        else:
            logger.debug("---GRADE: DOCUMENT NOT RELEVANT---")
            # We do not include the document in filtered_docs
            # We set a flag to indicate that we want to run web search
            web_search = "Yes"
            continue
    return {"documents": filtered_docs, "question": question, "web_search": web_search}


# Decides next step based on document relevance
def decide_to_generate(state: GraphState) -> Literal["websearch", "generate"]:
    logger.debug("---ASSESS GRADED DOCUMENTS---")
    # state["question"]
    web_search = state["web_search"]
    # state["documents"]

    if web_search == "Yes":
        # All documents have been filtered check_relevance
        # We will re-generate a new query
        logger.debug("---DECISION: ALL DOCUMENTS ARE NOT RELEVANT TO QUESTION, INCLUDE WEB SEARCH---")
        return "websearch"
    else:
        # We have relevant documents, so generate answer
        logger.debug("---DECISION: GENERATE---")
        return "generate"


# Function and node to detect allucination


# Checks if generated answer is supported by the documents
def hallucination_grader() -> Runnable[Any, YesOrNo]:
    system_prompt = """
        You are a grader assessing whether an answer is grounded in / supported by a set of facts.
        Evaluate  whether the answer is grounded in / supported by a set of facts.
        Answer only by 'yes' or 'no', without any other comment.\n"""
    user_prompt = """
        Here are the facts:
        --- \n {documents} ---\n
        Here is the answer: {generation} \n
        Instructions: {instructions} """
    prompt = def_prompt(system_prompt, user_prompt).partial(instructions=yesno_enum_parser.get_format_instructions())
    return prompt | get_llm(llm_id=LLM_ID) | to_lower | yesno_enum_parser  # type: ignore


# Evaluates answer quality and grounding
def grade_generation_v_documents_and_question(
    state: GraphState,
) -> Literal["useful", "not useful", "not supported"]:
    logger.debug("---CHECK HALLUCINATIONS---")
    question = state["question"]
    documents = state["documents"]
    generation = state["generation"]

    grounded = hallucination_grader().invoke({"documents": documents, "generation": generation})

    # Check hallucination
    if grounded == YesOrNo.YES:
        logger.debug("---DECISION: GENERATION IS GROUNDED IN DOCUMENTS---")
        # Check question-answering
        logger.debug("---GRADE GENERATION vs QUESTION---")
        grade = answer_grader().invoke({"question": question, "generation": generation})
        if grade == YesOrNo.YES:
            logger.debug("---DECISION: GENERATION ADDRESSES QUESTION---")
            return "useful"
        else:
            logger.debug("---DECISION: GENERATION DOES NOT ADDRESS QUESTION---")
            return "not useful"
    else:
        logger.debug("---DECISION: GENERATION IS NOT GROUNDED IN DOCUMENTS, RE-TRY---")
        return "not supported"


#####
## Create Graph
####
def create_graph(conf: dict) -> Pregel:
    workflow = StateGraph(GraphState)

    # Define the nodes
    workflow.add_node("websearch", web_search)  # web search
    workflow.add_node("retrieve", retrieve)  # retrieve
    workflow.add_node("grade_documents", grade_documents)  # grade documents
    workflow.add_node("generate", generate)  # generate
    ### Graph Build
    # Build graph
    workflow.set_conditional_entry_point(
        route_question,  # type: ignore
        {
            "websearch": "websearch",
            "vectorstore": "retrieve",
        },
    )

    workflow.add_edge("retrieve", "grade_documents")
    workflow.add_conditional_edges(
        "grade_documents",
        decide_to_generate,
        {
            "websearch": "websearch",
            "generate": "generate",
        },
    )
    workflow.add_edge("websearch", "generate")
    workflow.add_conditional_edges(
        "generate",
        grade_generation_v_documents_and_question,
        {
            "not supported": "generate",
            "useful": END,
            "not useful": "websearch",
        },
    )
    # Compile
    app = workflow.compile()
    return app


def query_graph(config: dict):
    return create_graph({}) | itemgetter("generation")


register_runnable(
    RunnableItem(
        tag="Advanced RAG",
        name="Advanced-RAG-Langgraph",
        runnable=("question", query_graph),
        examples=[
            Example(
                query=[
                    "What are the types of agent memory",
                    "Who are the Bears expected to draft first in the NFL draft?",
                ]
            )
        ],
        diagram="genai_blueprint/webapp/static/adaptative_rag_fallback.png",
    )
)

ri = RunnableItem(
    tag="Advanced RAG",
    name="Advanced-RAG-Langgraph",
    runnable=("question", query_graph),
    examples=[
        Example(
            query=[
                "What are the types of agent memory",
                "Who are the Bears expected to draft first in the NFL draft?",
            ]
        )
    ],
)


# Test


def test_graph_stream() -> None:
    app = create_graph({})
    inputs = {"question": "What are the types of agent memory?"}
    for output in app.stream(inputs):
        for key, value in output.items():
            logger.info(f"Finished running: {key}:")
    print(value["generation"])

    inputs = {"question": "Who are the Bears expected to draft first in the NFL draft?"}
    for output in app.stream(inputs):
        for key, value in output.items():
            logger.info(f"Finished running: {key}:")
    print(value["generation"])

    # https://smith.langchain.com/public/c785f9c0-f519-4a38-ad5a-febb59a2139c/r
    app.get_graph().draw_png("test_graph")


def test_graph() -> None:
    chain = query_graph({})
    input = {"question": "What are the types of agent memory?"}
    r = chain.invoke(input)
    print(r)


def test_nodes() -> None:
    question = "agent memory"
    docs = retriever().invoke(question)
    assert len(docs) > 0
    doc_txt = docs[1].page_content
    print(retrieval_grader().invoke({"question": question, "document": doc_txt}))

    # Run
    docs = retriever().invoke(question)
    generation = rag_chain().invoke({"context": docs, "question": question})
    print(generation)
    ### Hallucination Grader

    hallucination = hallucination_grader().invoke({"documents": docs, "generation": generation})
    print(hallucination)

    answer = answer_grader().invoke({"question": question, "generation": generation})
    print(answer)

    question = "llm agent memory"
    docs = retriever().invoke(question)
    doc_txt = docs[1].page_content
    logger.debug(question_router().invoke({"question": question}))


if __name__ == "__main__":
    from langchain_core.globals import set_debug, set_verbose

    set_debug(True)
    set_verbose(True)
    logger.remove()
    logger.add(
        sys.stderr,
        format="<blue>{level}</blue> | <green>{message}</green>",
        colorize=True,
    )
    test_nodes()
    # test_graph()
