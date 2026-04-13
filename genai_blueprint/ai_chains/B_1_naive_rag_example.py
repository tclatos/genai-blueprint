"""A simple RAG chain."""

from pathlib import Path

from genai_tk.core.chain_registry import Example, RunnableItem, register_runnable
from genai_tk.core.embeddings_store import EmbeddingsStore
from genai_tk.core.llm_factory import get_llm
from genai_tk.core.prompts import def_prompt
from langchain_community.document_loaders.text import TextLoader
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import Runnable, RunnableConfig, RunnableLambda, RunnablePassthrough
from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger
from rich import print  # noqa: F401


def get_retriever_fn(query: str | None, config: RunnableConfig) -> Runnable:
    path = config["configurable"].get("path")
    if path is None:
        raise ValueError("Config should have a 'path' key")
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Path in does not exists: {path}")
    vector_store = EmbeddingsStore.create_from_config("default").get()

    logger.info("indexing text document  {} in VectorStore", path)
    loader = TextLoader(path)
    docs = loader.load()
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=200)
    splits = text_splitter.split_documents(docs)
    vector_store.add_documents(documents=splits)

    return vector_store.as_retriever(search_kwargs={"k": 3})


get_retriever = RunnableLambda(func=get_retriever_fn)

prompt_system = """
    You are an assistant for question-answering tasks. Use the following pieces of retrieved context to answer the question.
    If you don't know the answer, just say that you don't know. Use three sentences maximum and keep the answer concise.
    """
prompt_user = """
    Question: {question}
    Context: {context}

    Answer:
    """
prompt = def_prompt(system=prompt_system, user=prompt_user)


def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)


def get_chain():
    chain = (
        {
            "context": get_retriever | format_docs,
            "question": RunnablePassthrough(),
        }
        | prompt
        | get_llm()
        | StrOutputParser()
    )
    return chain


register_runnable(
    RunnableItem(
        tag="RAG",
        name="Simple RAG chain",
        runnable=get_chain(),
        examples=[
            Example(
                path=Path("use_case_data/maintenance/maintenance_procedure_1.txt"),
                query=["What are the tools required for the maintenance task 'Repair of Faulty Switchgear' "],
            )
        ],
    )
)
