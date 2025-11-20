#
# Adapted from: https://python.langchain.com/docs/modules/data_connection/retrievers/self_query/
# See also https://blog.langchain.dev/query-construction/

from functools import cache

from devtools import debug  # noqa: F401
from genai_tk.core.chain_registry import (
    Example,
    RunnableItem,
    register_runnable,
)
from genai_tk.core.embeddings_store import EmbeddingsStore
from genai_tk.core.llm_factory import get_llm
from langchain_classic.chains.query_constructor.base import (
    StructuredQueryOutputParser,
    get_query_constructor_prompt,
)
from langchain_classic.chains.query_constructor.schema import AttributeInfo
from langchain_classic.retrievers.self_query.base import SelfQueryRetriever
from langchain_community.query_constructors.chroma import ChromaTranslator
from langchain_core.documents import Document
from langchain_core.vectorstores.base import VectorStore

# cSpell:disable

docs = [
    Document(
        page_content="A bunch of scientists bring back dinosaurs and mayhem breaks loose",
        metadata={"year": 1993, "rating": 7.7, "genre": "science fiction"},
    ),
    Document(
        page_content="Leo DiCaprio gets lost in a dream within a dream within a dream within a ...",
        metadata={"year": 2010, "director": "Christopher Nolan", "rating": 8.2},
    ),
    Document(
        page_content="A psychologist / detective gets lost in a series of dreams within dreams within dreams and Inception reused the idea",
        metadata={"year": 2006, "director": "Satoshi Kon", "rating": 8.6},
    ),
    Document(
        page_content="A bunch of normal-sized women are supremely wholesome and some men pine after them",
        metadata={"year": 2019, "director": "Greta Gerwig", "rating": 8.3},
    ),
    Document(
        page_content="Toys come alive and have a blast doing so",
        metadata={"year": 1995, "genre": "animated"},
    ),
    Document(
        page_content="Three men walk into the Zone, three men walk out of the Zone",
        metadata={
            "year": 1979,
            "director": "Andrei Tarkovsky",
            "genre": "thriller",
            "rating": 9.9,
        },
    ),
]


metadata_field_info = [
    AttributeInfo(
        name="genre",
        description="The genre of the movie. One of ['science fiction', 'comedy', 'drama', 'thriller', 'romance', 'action', 'animated']",
        type="string",
    ),
    AttributeInfo(
        name="year",
        description="The year the movie was released",
        type="integer",
    ),
    AttributeInfo(
        name="director",
        description="The name of the movie director",
        type="string",
    ),
    AttributeInfo(name="rating", description="A 1-10 rating for the movie", type="float"),
]

# cSpell:enable
document_content_description = "Brief summary of a movie"


@cache
def vector_store() -> VectorStore:
    vector_store = EmbeddingsStore.create_from_config("in_memory_chroma").get()
    vector_store.add_documents(docs)
    return vector_store


def get_query_constructor(config: dict):
    prompt = get_query_constructor_prompt(
        document_content_description,
        metadata_field_info,
    )
    output_parser = StructuredQueryOutputParser.from_components()
    llm = get_llm(llm=config.get("llm"))

    # debug(llm)
    query_constructor = prompt | llm | output_parser
    return query_constructor


def get_retriever(config: dict):
    query_constructor = get_query_constructor(config)
    #    print(query_constructor)
    retriever = SelfQueryRetriever(
        query_constructor=query_constructor,  # TODO: Clarify # type: ignore
        llm_chain=query_constructor,
        vectorstore=vector_store(),
        structured_query_translator=ChromaTranslator(),
        verbose=True,
    )
    #    print(query_constructor, retriever)
    return retriever


register_runnable(
    RunnableItem(
        tag="self_query",
        name="self_query_constructor",
        runnable=("query", get_query_constructor),
        examples=[
            Example(
                query=["What are some sci-fi movies from the 90's directed by Luc Besson about taxi drivers"],
            )
        ],
    )
)


register_runnable(
    RunnableItem(
        tag="self_query",
        name="self_query_retriever",
        runnable=get_retriever,
        examples=[
            Example(
                query=[
                    "What are some sci-fi movies from the 90's about taxi drivers",
                    "What's a movie after 1990 but before 2005 that's all about toys, and preferably is animated",
                    "I want to watch a movie rated higher than 8.5",
                    "Has Greta Gerwig directed any movies about women",
                    "What's a highly rated (above 8.5) science fiction film?",
                ]
            )
        ],
    )
)

if __name__ == "__main__":
    llm = "gpt_35_openai"
    r = get_retriever(config={"llm": llm}).invoke("I want to watch a movie rated higher than 8.5")
    print(r)
