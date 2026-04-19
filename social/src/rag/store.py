"""RAG store: Chroma vector DB with local HuggingFace embeddings. No API key required."""

import logging
from pathlib import Path

from langchain_community.document_loaders import TextLoader, PyPDFLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# Default model: small, fast, no API key, ~80MB download on first use.
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"


def _get_embeddings(model: str = DEFAULT_EMBEDDING_MODEL) -> HuggingFaceEmbeddings:
    """Load a local sentence-transformers embedding model. Downloads on first use."""
    logger.debug("Loading embedding model: %s", model)
    return HuggingFaceEmbeddings(model_name=model)


class RAGStore:
    def __init__(
        self,
        persist_directory: str = "./data/chroma",
        collection_name: str = "bot_knowledge",
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        top_k: int = 4,
    ):
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.top_k = top_k
        self.embeddings = _get_embeddings(embedding_model)
        self._vector_store: Chroma | None = None

    def _get_vector_store(self) -> Chroma:
        if self._vector_store is None:
            self._vector_store = Chroma(
                collection_name=self.collection_name,
                embedding_function=self.embeddings,
                persist_directory=self.persist_directory,
            )
        return self._vector_store

    def add_documents(
        self,
        documents: list[Document],
        text_splitter: RecursiveCharacterTextSplitter | None = None,
    ):
        if not documents:
            logger.debug("add_documents called with empty list — nothing to do.")
            return
        splitter = text_splitter or RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=200,
        )
        splits = splitter.split_documents(documents)
        self._get_vector_store().add_documents(splits)
        logger.info("Added %d chunks from %d documents.", len(splits), len(documents))

    def add_texts(self, texts: list[str], metadatas: list[dict] | None = None):
        """Convenience wrapper: add raw strings as documents."""
        docs = [
            Document(
                page_content=t,
                metadata=metadatas[i] if metadatas and i < len(metadatas) else {},
            )
            for i, t in enumerate(texts)
        ]
        self.add_documents(docs)

    def ingest_directory(self, path: str | Path):
        """Load all .txt, .md, and .pdf files from a directory (recursive)."""
        path = Path(path)
        if not path.is_dir():
            raise FileNotFoundError(f"Directory not found: {path}")

        documents: list[Document] = []
        loaders = {
            "**/*.txt": TextLoader,
            "**/*.md": TextLoader,
            "**/*.pdf": PyPDFLoader,
        }
        for pattern, loader_cls in loaders.items():
            for f in path.glob(pattern):
                if f.is_file():
                    try:
                        documents.extend(loader_cls(str(f)).load())
                        logger.debug("Loaded: %s", f)
                    except Exception as e:
                        logger.warning("Skipping %s: %s", f, e)

        if not documents:
            logger.warning("No documents found in %s", path)
            return

        self.add_documents(documents)
        logger.info("Ingested %d documents from %s", len(documents), path)

    def retrieve(self, query: str, top_k: int | None = None) -> str:
        """Return the top_k most relevant chunks as a single string."""
        k = top_k if top_k is not None else self.top_k
        results = self._get_vector_store().similarity_search(query, k=k)
        if not results:
            return ""
        return "\n\n".join(doc.page_content for doc in results)
