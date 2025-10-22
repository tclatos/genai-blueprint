"""Agentic RAG implementation using LangGraph's Functional API.

This is an adaptation of the agentic RAG pattern from langgraph_agentic_rag.ipynb
using LangGraph's Functional API (@task/@entrypoint decorators) instead of the StateGraph API.
Implements an agent that can decide when to retrieve documents and answer questions dynamically.
"""

# Original : https://github.com/langchain-ai/langgraph/blob/main/examples/rag/langgraph_agentic_rag.ipynb
# NOT TESTED

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
#from langchain_core.output_parsers.enum import EnumOutputParser
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import RunnableLambda
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.checkpoint.memory import MemorySaver
from langgraph.func import entrypoint, task
from loguru import logger
from pydantic import BaseModel, Field

load_dotenv(verbose=True)

LLM_ID = None


class YesOrNo(Enum):
    YES = "yes"
    NO = "no"


class DataRoute(Enum):
    WEB_SEARCH = "web_search"
    VECTOR_STORE = "vectorstore"


class AgentState(BaseModel):
    question: str = Field(description="The user's question")
    context: list[Document] = Field(default_factory=list, description="Retrieved documents")
    generation: str = Field(default="", description="Generated answer")
    documents: list[Document] = Field(default_factory=list, description="All retrieved documents")
    steps: list[str] = Field(default_factory=list, description="Agent reasoning steps")


yesno_enum_parser = EnumOutputParser(enum=YesOrNo)
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
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        doc_splits = text_splitter.split_documents(docs_list)
        vectorstore.add_documents(doc_splits)
    return vectorstore.as_retriever()


# Task: Retrieves documents relevant to the question from vector store
@task
def retrieve_documents(question: str) -> list[Document]:
    """Retrieve relevant documents from vector store based on question."""
    return retriever().invoke(question)


# Task: Determines if retrieval is needed for the question
@task
def should_retrieve(question: str) -> YesOrNo:
    """Determine if document retrieval is needed to answer the question."""
    system_prompt = """                                                                                               
        You are an expert at determining whether a question requires document retrieval.                              
        If the question is about factual information that would benefit from context, answer 'yes'.                   
        If the question is conversational or doesn't need external knowledge, answer 'no'.                            
        Answer only 'yes' or 'no'.                                                                                    
        """
    user_prompt = """Question: {question}"""
    prompt = def_prompt(system_prompt, user_prompt)
    chain = prompt | get_llm(llm_id=LLM_ID) | to_lower | yesno_enum_parser
    return chain.invoke({"question": question})


# Task: Generates an answer to the question using retrieved context
@task
def generate_answer(question: str, context: list[Document]) -> str:
    """Generate an answer using the provided context."""
    system_prompt = """                                                                                               
        You are an assistant for question-answering tasks. Use the following pieces of retrieved context to answer the
question.                                                                                                             
        If you don't know the answer, just say that you don't know. Use three sentences maximum and keep the answer   
concise.                                                                                                              
        """
    user_prompt = """                                                                                                 
        Question: {question}                                                                                          
        Context: {context}                                                                                            
        Answer: """
    prompt = def_prompt(system=system_prompt, user=user_prompt)
    chain = prompt | get_llm(llm_id=LLM_ID) | StrOutputParser()
    return chain.invoke({"question": question, "context": context})


# Task: Determines if the generated answer is sufficient
@task
def answer_sufficient(question: str, answer: str) -> YesOrNo:
    """Determine if the generated answer sufficiently answers the question."""
    system_prompt = """                                                                                               
        You are evaluating whether an answer sufficiently addresses the question.                                     
        Consider if the answer provides complete and accurate information to resolve the question.                    
        Answer only 'yes' or 'no'.                                                                                    
        """
    user_prompt = """                                                                                                 
        Question: {question}                                                                                          
        Answer: {answer}                                                                                              
        Is this answer sufficient? """
    prompt = def_prompt(system_prompt, user_prompt)
    chain = prompt | get_llm(llm_id=LLM_ID) | to_lower | yesno_enum_parser
    return chain.invoke({"question": question, "answer": answer})


# Task: Performs web search if needed
@task
def web_search(question: str) -> list[Document]:
    """Perform web search and return results as documents."""
    search_result = basic_web_search(question)
    return [Document(page_content=search_result)]


# Task: Routes question to appropriate retrieval method
@task
def route_question(question: str) -> DataRoute:
    """Route question to vector store or web search."""
    parser = EnumOutputParser(enum=DataRoute)
    system_prompt = """                                                                                               
        You are an expert at routing questions. For questions about LLM agents, prompt engineering,                   
        and adversarial attacks, use vectorstore. For current events or broad topics, use web search.                 
        Give a binary choice 'web_search' or 'vectorstore' with no explanation.                                       
        """
    user_prompt = """Question: {question}"""
    prompt = def_prompt(system_prompt, user_prompt).partial(instructions=parser.get_format_instructions())
    chain = prompt | get_llm(llm_id=LLM_ID) | parser
    return chain.invoke({"question": question})


# Main agentic RAG workflow
@entrypoint(checkpointer=MemorySaver())
def agentic_rag_workflow(question: str) -> dict:
    """Agentic RAG workflow that decides when and how to retrieve information."""
    logger.info(f"Processing question: {question}")

    # Initialize state
    state = AgentState(question=question)
    state.steps.append("Starting agentic RAG workflow")

    # Check if retrieval is needed
    needs_retrieval = should_retrieve(question).result()
    state.steps.append(f"Retrieval needed: {needs_retrieval}")

    if needs_retrieval == YesOrNo.YES:
        # Route to appropriate data source
        route = route_question(question).result()
        state.steps.append(f"Routing to: {route}")

        if route == DataRoute.VECTOR_STORE:
            documents = retrieve_documents(question).result()
            state.steps.append(f"Retrieved {len(documents)} documents from vector store")
        else:
            documents = web_search(question).result()
            state.steps.append(f"Retrieved {len(documents)} documents from web search")

        state.documents = documents

        # Generate answer with context
        generation = generate_answer(question, documents).result()
        state.generation = generation
        state.steps.append("Generated answer with retrieved context")

        # Check if answer is sufficient
        sufficient = answer_sufficient(question, generation).result()
        state.steps.append(f"Answer sufficient: {sufficient}")

        if sufficient == YesOrNo.NO:
            # Try web search as fallback
            fallback_docs = web_search(question).result()
            state.documents.extend(fallback_docs)
            state.steps.append("Using web search as fallback")

            generation = generate_answer(question, state.documents).result()
            state.generation = generation
            state.steps.append("Generated new answer with fallback context")
    else:
        # Direct generation without retrieval
        generation = generate_answer(question, []).result()
        state.generation = generation
        state.steps.append("Generated answer without retrieval")

    return {"answer": state.generation, "documents": state.documents, "steps": state.steps}


if __name__ == "__main__":
    from langchain.globals import set_debug, set_verbose

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
    result = agentic_rag_workflow.invoke("What are the types of agent memory?", config)
    logger.info(f"Final result: {result}")
