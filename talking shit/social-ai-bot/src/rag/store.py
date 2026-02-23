"""RAG store using Chroma and LangChain."""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

from langchain_community.document_loaders import DirectoryLoader, TextLoader, PyPDFLoader
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document


def _get_embeddings(model: str = "text-embedding-3-small"):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required for embeddings.")
    return OpenAIEmbeddings(model=model, openai_api_key=api_key)


class RAGStore:
    def __init__(
        self,
        persist_directory: str = "./data/chroma",
        collection_name: str = "bot_knowledge",
        embedding_model: str = "text-embedding-3-small",
    ):
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.embeddings = _get_embeddings(embedding_model)
        self._vector_store = None

    def _get_vector_store(self):
        if self._vector_store is None:
            self._vector_store = Chroma(
                collection_name=self.collection_name,
                embedding_function=self.embeddings,
                persist_directory=self.persist_directory,
            )
        return self._vector_store

    def add_documents(self, documents: list[Document], text_splitter: RecursiveCharacterTextSplitter | None = None):
        if not documents:
            return
        splitter = text_splitter or RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=200,
        )
        splits = splitter.split_documents(documents)
        store = self._get_vector_store()
        store.add_documents(splits)

    def add_texts(self, texts: list[str], metadatas: list[dict] | None = None):
        docs = [
            Document(page_content=t, metadata=metadatas[i] if metadatas and i < len(metadatas) else {})
            for i, t in enumerate(texts)
        ]
        self.add_documents(docs)

    def ingest_directory(self, path: str | Path):
        path = Path(path)
        if not path.is_dir():
            raise FileNotFoundError(f"Directory not found: {path}")
        documents = []
        for ext, loader_cls in [("**/*.txt", TextLoader), ("**/*.md", TextLoader), ("**/*.pdf", PyPDFLoader)]:
            for f in path.glob(ext):
                if f.is_file():
                    try:
                        documents.extend(loader_cls(str(f)).load())
                    except Exception as e:
                        logger.warning("Skipping %s: %s", f, e)
        self.add_documents(documents)

    def retrieve(self, query: str, top_k: int = 4) -> str:
        store = self._get_vector_store()
        results = store.similarity_search(query, k=top_k)
        if not results:
            return ""
        return "\n\n".join(doc.page_content for doc in results)
