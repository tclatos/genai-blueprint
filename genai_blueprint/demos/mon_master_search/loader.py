# cSpell: disable
import codecs
import fnmatch
import re
import tarfile
from collections.abc import Iterator
from pathlib import Path

import json_repair
import pandas as pd
import typer
from genai_tk.utils.config_mngr import global_config
from genai_tk.utils.pydantic.jsonl_store import load_objects_from_jsonl, store_objects_to_jsonl

try:
    from abbreviations import schwartz_hearst
except ImportError as ex:
    raise ImportError("abbreviations package is required. Install with: uv add abbreviations --group demos") from ex
from genai_tk.core.embeddings_store import EmbeddingsStore
from genai_tk.core.llm_factory import get_llm
from genai_tk.core.prompts import def_prompt
from genai_tk.extra.retrievers.bm25s_retriever import BM25FastRetriever, get_spacy_preprocess_fn
from langchain_community.document_loaders.base import BaseLoader
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from loguru import logger
from pydantic import BaseModel
from unidecode import unidecode

from genai_blueprint.demos.mon_master_search.model_subset import (
    ACRONYMS,
    STOP_WORDS,
    ParcoursFormations,
)

app = typer.Typer()


class Description(BaseModel):
    inm: str
    for_intitule: str
    libeles: set[str] = set()
    intitule_parcours: set[str] = set()
    modalite_enseignement: set[str] = set()
    licences_conseillees: set[str] = set()
    disciplines: set[str] = set()
    secteurs: set[str] = set()
    metiers: set[str] = set()
    autre: set[str] = set()
    lien_fiche: set[str] = set()


REGEXP_ACRONYMS = r"(?<!\()\b[A-Z]{2,}\b(?!\))"


def add_accronym(s: str) -> str:
    accronyms = re.findall(REGEXP_ACRONYMS, s)
    result = s

    pairs = schwartz_hearst.extract_abbreviation_definition_pairs(doc_text=s)
    for a in accronyms:
        if pairs.get(a) is None:
            if found := ACRONYMS.get(a):
                if set(found.split(" ")).isdisjoint(set(s.split(" "))):
                    result += f" ({found})"
    return result


def process_json(source: str, formation: ParcoursFormations) -> Iterator[Document]:
    logger.debug(f"load {source}")

    metadata_offre = {
        "eta_uai": formation.etab.desgn_etab.eta_uai,
        "eta_libelle": formation.etab.desgn_etab.eta_libelle,
        "eta_name": formation.etab.desgn_etab.eta_name,
    }
    for dmn in formation.dnms:
        desc = Description(
            inm=dmn.for_inm,
            for_intitule=dmn.for_intitule,
        )

        desc.inm = dmn.for_inm
        info_pedago = dmn.informations_pedagogiques
        # print(dmn.for_intitule, dmn.dom_libelle)
        if info_pedago:
            desc.libeles.update(dmn.dom_libelle)
            desc.disciplines.update(info_pedago.mot_cle_disciplinaire or [])
            desc.metiers.update(info_pedago.mot_cle_metier or {})
            desc.secteurs.update(info_pedago.mot_cle_sectoriel or {})
            desc.autre.update(info_pedago.mot_cle_libre or {})
            desc.lien_fiche.update([info_pedago.lien_fiche] or {})

        for parcours in dmn.parcours or []:
            desc.intitule_parcours.update([parcours.intitule_parcours] or {})
            desc.modalite_enseignement.update(parcours.modalite_enseignement or {})
            desc.licences_conseillees.update(parcours.licences_conseillees or {})

            if info_pedago := parcours.informations_pedagogiques:
                intitule_p = add_accronym(parcours.intitule_parcours)
                desc.intitule_parcours.update([intitule_p])
                desc.disciplines.update(info_pedago.mot_cle_disciplinaire or [])
                desc.metiers.update(info_pedago.mot_cle_metier or [])
                desc.secteurs.update(info_pedago.mot_cle_sectoriel or [])
                desc.autre.update(info_pedago.mot_cle_libre or [])
                desc.lien_fiche.update(info_pedago.lien_fiche or [])

        content_fmt = [f'"{desc.for_intitule}" : {add_accronym(desc.for_intitule)}']
        if desc.libeles:
            content_fmt.append(f"libelés: {'; '.join(desc.libeles)}")
        if desc.intitule_parcours:
            content_fmt.append(f"parcours: {'; '.join(desc.intitule_parcours)}")
        if desc.disciplines:
            content_fmt.append(f"disciplines: {'; '.join(desc.disciplines)}")
        if desc.secteurs:
            content_fmt.append(f"secteurs: {'; '.join(desc.secteurs)}")
        if desc.metiers:
            content_fmt.append(f"métiers: {' '.join(desc.metiers)}")
        if desc.autre:
            content_fmt.append(f"autre: {'; '.join(desc.autre)}")

        content_str = "\n".join(content_fmt)
        meta = metadata_offre | {
            "source": desc.inm,
            "for_intitule": desc.for_intitule,
            "modalite_enseignement": ";".join(desc.modalite_enseignement),
            "licences_conseillees": ";".join(desc.licences_conseillees),
        }
        doc = Document(page_content=content_str, metadata=meta)
        yield doc


class offre_formation_loader(BaseLoader):
    def __init__(self, doc_list: Path) -> None:
        self.parcours_json_archive = doc_list

    def lazy_load(self) -> Iterator[Document]:
        with tarfile.open(self.parcours_json_archive, "r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile() and fnmatch.fnmatch(member.name, "Offre_*.json"):
                    raise Exception("incorrect file in archive: {member}")
                file_obj = tar.extractfile(member)
                assert file_obj

                json_file = file_obj.read().decode("utf-8")
                json_obj = json_repair.loads(json_file)
                parcours = ParcoursFormations(**json_obj)  # type: ignore

                yield from process_json(str(member.name), parcours)


REPO = global_config().get_dir_path("external_data", create_if_not_exists=False)
FILES = REPO / "synthesis_v2.json"
assert FILES.exists()

EMBEDDINGS_MODEL = "minilm_multilingual_local"
EMBEDDINGS_MODEL = "camembert_large_local"
EMBEDDINGS_MODEL = "solon_large_local"


@app.command()
def create_embeddings(embeddings: str = EMBEDDINGS_MODEL) -> None:
    vector_factory = EmbeddingsStore.create_from_config("default")
    docs = list(load_objects_from_jsonl(FILES, Document))

    logger.info(f"There are {vector_factory.document_count()} documents in  vector store")

    logger.info(f"add {len(docs)} documents to vector store: {vector_factory.description}")
    # vector_factory.get()
    for doc in docs:
        try:
            print(".", end="", flush=True)
            vector_factory.add_documents([doc])
        except Exception as ex:
            logger.warning(f"cannot add {doc.metadata['source']} - {ex}")
    print("done")


@app.command()
def create_bm25_index(k: int = 20):
    logger.info("create BM25 index")
    docs_for_bm25 = list(load_objects_from_jsonl(FILES, Document))
    docs = docs_for_bm25
    path = Path(global_config().get_str("vector_store.path")) / "bm25"
    fn = get_spacy_preprocess_fn(model="fr_core_news_sm", more_stop_words=STOP_WORDS)  # noqa: F821
    retriever = BM25FastRetriever.from_documents(documents=docs, preprocess_func=fn, k=k, cache_dir=path)
    return retriever


@app.command()
def bm25_index_search(query: str, k: int = 20) -> None:
    retriever = create_bm25_index(k)
    r = retriever.invoke(query)
    print(r)


@app.command()
def bm25_search(query: str, k: int = 10) -> None:
    path = Path(global_config().get_str("vector_store.path")) / "bm25"

    fn = get_spacy_preprocess_fn(model="fr_core_news_sm", more_stop_words=STOP_WORDS)  # noqa: F821
    retriever = BM25FastRetriever.from_cache(preprocess_func=fn, k=k, cache_dir=path)
    retriever.invoke(query)


@app.command()
def save_to_jsonl() -> None:
    loader = offre_formation_loader(REPO / "Offres_2024.tgz")
    processed = list(loader.load())
    store_objects_to_jsonl(processed, FILES)


@app.command()
def find_acronyms():
    acronyms = set()
    candidates = set()

    try:
        import enchant
    except ImportError as ex:
        raise ImportError("enchant package is required. Install with: uv add enchant --group demos") from ex

    french_dict = enchant.Dict("fr")
    english_dict = enchant.Dict("en")

    logger.info("extract abbreviations defintion fom text")

    pairs = schwartz_hearst.extract_abbreviation_definition_pairs(file_path=FILES, most_common_definition=True)
    known_abbrev = {codecs.decode(k, "unicode_escape"): codecs.decode(v, "unicode_escape") for k, v in pairs.items()}

    logger.info("extract possible abbreviations")
    docs = load_objects_from_jsonl(FILES)
    for doc in docs:
        candidates.update(re.findall(REGEXP_ACRONYMS, doc.page_content))
        # print(candidates)
    for word in candidates:
        if not french_dict.check(word) and not english_dict.check(word):
            suggested = [unidecode(w).lower() for w in french_dict.suggest(word)]
            if unidecode(word).lower() not in suggested:
                acronyms.add(word)

    d = {token: known_abbrev.get(token) or "" for token in acronyms}
    df = pd.DataFrame.from_dict(d, orient="index")
    logger.info("save to Excel")
    df.to_excel(REPO / "abbreviations.xlsx", sheet_name="extracted")
    return df


@app.command()
def llm_for_abbrev() -> None:
    df_extract = pd.read_excel(REPO / "abbreviations.xlsx", index_col=0)
    # df_extract = find_acronyms()
    unknown = df_extract[df_extract.iloc[:, 0].isnull()]
    unknown_list = "\n".join(unknown.index.tolist())
    first = unknown.index.to_list()[0]

    system = """
    Vous êtes expert du domaine de l'enseignement supérieur en France.
    Repondez uniquement en Francais.
    Pour chacune des abréviations suivantes, completez par la signification si vous la connaissez.
    Si vous ne savez pas, répondez "?".
    N'ajoutez pas de commentaires et autres information.
    """

    user = """
    ###  ABBREVIATIONS ###
    {abrev}
    ### REPONSE: ###
    - {first_one}: ...
    - ...
    """

    # llm_mistral = get_llm("mistral_large_edenai")
    llm_gpt4 = get_llm("gpt_4o_edenai")

    prompt = def_prompt(system, user)
    chain = prompt | llm_gpt4 | StrOutputParser()

    logger.info("call llm")
    rep = chain.invoke({"abrev": unknown_list, "first_one": first})

    d = {}
    for line in rep.split("\n"):
        print(line)
        k, _, v = line.partition(":")
        d |= {k.strip("- "): v.strip()}

    OUT_FILE = REPO / "abbreviation_llm_2.xlsx"
    logger.info(f"write Exel file : {OUT_FILE}")
    df_llm = pd.DataFrame.from_dict(d, orient="index")
    with pd.ExcelWriter(OUT_FILE) as writer:
        df_extract.to_excel(writer, sheet_name="extracted")
        df_llm.to_excel(writer, sheet_name="llm_openai")


if __name__ == "__main__":
    assert REPO.exists
    app()
