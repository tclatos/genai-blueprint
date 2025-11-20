"""Advanced RAG implementation using LangGraph's Functional API.

This is an adaptation of https://github.com/langchain-ai/langgraph/blob/main/examples/rag/langgraph_adaptive_rag.ipynb
using LangGraph's Functional API (@task/@entrypoint decorators) instead of the StateGraph API.
Implements the same RAG pipeline with document retrieval, grading and generation.
"""

import sys
from enum import Enum

from dotenv import load_dotenv
from genai_tk.core.embeddings_store import EmbeddingsStore
from genai_tk.core.llm_factory import get_llm
from genai_tk.core.prompts import def_prompt
from genai_tk.tools.langchain.web_search_tool import basic_web_search
from genai_tk.utils.singleton import once
from langchain_community.document_loaders.web_base import WebBaseLoader
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser

# from langchain_core.output_parsers import EnumOutputParser
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import RunnableLambda
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.checkpoint.memory import MemorySaver
from langgraph.func import entrypoint, task
from loguru import logger

load_dotenv(verbose=True)

# LLM_ID = "claude_haiku35_openrouter"

LLM_ID = "gemma3_4b_ollama"


class YesOrNo(Enum):
    YES = "yes"
    NO = "no"


class DataRoute(Enum):
    WEB_SEARCH = "websearch"
    VECTOR_STORE = "vectorstore"


# yesno_enum_parser = EnumOutputParser(enum=YesOrNo)
to_lower = RunnableLambda(lambda x: getattr(x, "content", "").lower())


# Creates and returns a retriever with pre-loaded documents if empty
@once
def retriever() -> BaseRetriever:
    urls = [
        "https://lilianweng.github.io/posts/2023-06-23-agent/",
        "https://lilianweng.github.io/posts/2023-03-15-prompt-engineering/",
        "https://lilianweng.github.io/posts/2023-10-25-adv-attack-llm/",
    ]

    embeddings_store = EmbeddingsStore.create_from_config("in_memory_chroma")
    vectorstore = embeddings_store.get()

    if embeddings_store.document_count() == 0:
        logger.info("indexing documents...")
        docs = [WebBaseLoader(url).load() for url in urls]
        docs_list = [item for sublist in docs for item in sublist]
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=250, chunk_overlap=0)
        doc_splits = text_splitter.split_documents(docs_list)
        vectorstore.add_documents(doc_splits)
    return vectorstore.as_retriever()


# Task: Retrieves documents relevant to the question from vector store
@task
def retrieve_documents(question: str) -> list[Document]:
    return retriever().invoke(question, k=5)


# Task: Grades whether a retrieved document is relevant to the question
@task
def retrieval_grader(question: str, document: str) -> YesOrNo:
    system_prompt = """
        You are a grader assessing relevance of a retrieved document to a user question.
        If the document contains keywords related to the user question, grade it as relevant.
        It does not need to be a stringent test. The goal is to filter out erroneous retrievals. \n
        Evaluate whether the document is relevant to the question. 
        Answser as JSON.
        """
    user_prompt = """
        Here is the retrieved document:
        --- \n {document} ---\n\n
        Here is the user question: {question} \n"""

    prompt = def_prompt(system_prompt, user_prompt)
    chain = prompt | get_llm(llm=LLM_ID).with_structured_output(YesOrNo)
    return chain.invoke({"question": question, "document": document})  # type: ignore


# Task: Generates an answer to the question using retrieved context
@task
def rag_chain(question: str, context: list[Document]) -> str:
    system_prompt = """
        You are an assistant for question-answering tasks.
        Use the following pieces of retrieved context to answer the question. If you don't know the answer, just say that you don't know.
        Use three sentences maximum and keep the answer concise."""
    user_prompt = """
        Question: {question}
        Context: {context}
        Answer: """
    prompt = def_prompt(system=system_prompt, user=user_prompt)
    chain = prompt | get_llm(llm=LLM_ID) | StrOutputParser()
    return chain.invoke({"question": question, "context": context})


# Task: Checks if generated answer is supported by the documents
@task
def hallucination_grader(documents: list[Document], generation: str) -> YesOrNo:
    system_prompt = """
        You are a grader assessing whether an answer is grounded in / supported by a set of facts.
        Evaluate  whether the answer is grounded in / supported by a set of facts.
        Answser as JSON.\n"""
    user_prompt = """
        Here are the facts:
        --- \n {documents} ---\n
        Here is the answer: {generation} """
    prompt = def_prompt(system_prompt, user_prompt)
    chain = prompt | get_llm(llm=LLM_ID).with_structured_output(YesOrNo)
    return chain.invoke({"documents": documents, "generation": generation})  # type: ignore


# Task: Evaluates if generated answer is useful for the question
@task
def answer_grader(question: str, generation: str) -> YesOrNo:
    system_prompt = """
        You are a grader assessing whether an answer is useful to resolve a question.
        Evaluate whether the answer is useful to resolve the question.
        Answser as JSON.\n"""
    user_prompt = """
        Here are the answer:
        \n---  {generation} \n---
        Here is the question: {question}
        """
    prompt = def_prompt(system_prompt, user_prompt)
    chain = prompt | get_llm(llm=LLM_ID).with_structured_output(YesOrNo)
    return chain.invoke({"question": question, "generation": generation})  # type: ignore


# Task: Routes question to either vector store or web search
@task
def question_router(question: str) -> DataRoute:
    system_prompt = """
        You are an expert at routing a user question to a vectorstore or web search.
        Use the vectorstore for questions on LLM agents, prompt engineering, and adversarial attacks.
        You do not need to be stringent with the keywords in the question related to these topics.
        Otherwise, use web-search.
        Answser as JSON.
        """
    user_prompt = """
        Question to route: {question}  """
    prompt = def_prompt(system_prompt, user_prompt)
    chain = prompt | get_llm(llm=LLM_ID).with_structured_output(DataRoute)
    return chain.invoke({"question": question})  # type: ignore


# Main workflow that orchestrates the RAG pipeline with fallback logic
@entrypoint(checkpointer=MemorySaver())
def advanced_rag_workflow(question: str) -> dict:
    # Route question to appropriate source
    route = question_router(question).result()

    if route == DataRoute.WEB_SEARCH:
        documents = [Document(page_content=basic_web_search.invoke(question))]
    else:
        # Retrieve and grade documents
        documents = retrieve_documents(question).result()
        # filtered_docs = []
        # for doc in documents:
        #     if retrieval_grader(question, doc.page_content).result() == YesOrNo.YES:
        #         filtered_docs.append(doc)
        futures = [retrieval_grader(question, doc.page_content) for doc in documents]
        is_appropriate = [f.result() for f in futures]
        filtered_docs = [
            doc.page_content
            for (doc, ok) in zip(documents, is_appropriate, strict=True)
            if is_appropriate == YesOrNo.YES
        ]

        if not filtered_docs:
            documents = [Document(page_content=basic_web_search.invoke(question))]
        else:
            documents = filtered_docs

    # Generate and grade answer
    generation = rag_chain(question, documents).result()

    # Check if answer is grounded and useful
    if hallucination_grader(documents, generation).result() == YesOrNo.YES:
        if answer_grader(question, generation).result() == YesOrNo.YES:
            return {"answer": generation, "documents": documents}

    # If answer is not satisfactory, try web search
    if route != DataRoute.WEB_SEARCH:
        documents = [Document(page_content=basic_web_search.invoke(question))]
        generation = rag_chain(question, documents).result()
        return {"answer": generation, "documents": documents}

    return {"answer": "I couldn't find a satisfactory answer to your question.", "documents": documents}


# # Register the workflow
# TODO : improve RunnableItem
# register_runnable(
#     RunnableItem(
#         tag="Advanced RAG",
#         name="Advanced-RAG-Functional",
#         runnable=("question", advanced_rag_workflow),
#         examples=[
#             Example(
#                 query=[
#                     "What are the types of agent memory",
#                     "Who are the Bears expected to draft first in the NFL draft?",
#                 ]
#             )
#         ],
#         diagram="genai_blueprint/webapp/static/adaptative_rag_fallback.png",
#     )
# )

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

    # Test the workflow
    config = {"configurable": {"thread_id": "1"}}
    result = advanced_rag_workflow.invoke("What are the types of agent memory?", config)
    print(result)
