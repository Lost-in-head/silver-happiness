"""Tests for src/rag/store.py"""

import pytest
import src.rag.store  # must import before patching submodule attributes
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from langchain_core.documents import Document


@pytest.fixture(autouse=True)
def mock_embeddings():
    """Prevent downloading embedding models in tests."""
    with patch("src.rag.store.HuggingFaceEmbeddings") as MockEmb:
        MockEmb.return_value = MagicMock()
        yield MockEmb


@pytest.fixture(autouse=True)
def mock_chroma():
    """Prevent Chroma from touching the filesystem in tests."""
    with patch("src.rag.store.Chroma") as MockChroma:
        mock_instance = MagicMock()
        mock_instance.similarity_search.return_value = []
        MockChroma.return_value = mock_instance
        yield MockChroma


@pytest.fixture
def store():
    from src.rag.store import RAGStore
    return RAGStore(
        persist_directory="/tmp/test_chroma",
        collection_name="test",
        embedding_model="all-MiniLM-L6-v2",
        top_k=3,
    )


class TestRAGStoreInit:
    def test_embedding_model_is_loaded(self, mock_embeddings):
        from src.rag.store import RAGStore
        RAGStore(embedding_model="all-MiniLM-L6-v2")
        mock_embeddings.assert_called_once_with(model_name="all-MiniLM-L6-v2")

    def test_default_top_k(self):
        from src.rag.store import RAGStore
        s = RAGStore()
        assert s.top_k == 4

    def test_custom_top_k(self):
        from src.rag.store import RAGStore
        s = RAGStore(top_k=8)
        assert s.top_k == 8

    def test_vector_store_is_lazy(self, mock_chroma):
        from src.rag.store import RAGStore
        s = RAGStore()
        mock_chroma.assert_not_called()
        # Access triggers creation
        s._get_vector_store()
        mock_chroma.assert_called_once()


class TestAddDocuments:
    def test_empty_documents_is_noop(self, store, mock_chroma):
        store.add_documents([])
        mock_chroma.return_value.add_documents.assert_not_called()

    def test_documents_are_split_and_added(self, store):
        docs = [Document(page_content="Hello world " * 50)]
        store.add_documents(docs)
        store._get_vector_store().add_documents.assert_called_once()

    def test_multiple_documents_added(self, store):
        docs = [
            Document(page_content="Doc one content."),
            Document(page_content="Doc two content."),
        ]
        store.add_documents(docs)
        store._get_vector_store().add_documents.assert_called_once()

    def test_custom_splitter_is_used(self, store):
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        custom_splitter = MagicMock(spec=RecursiveCharacterTextSplitter)
        custom_splitter.split_documents.return_value = [
            Document(page_content="chunk 1")
        ]
        docs = [Document(page_content="Some text")]
        store.add_documents(docs, text_splitter=custom_splitter)
        custom_splitter.split_documents.assert_called_once_with(docs)


class TestAddTexts:
    def test_texts_converted_to_documents(self, store):
        with patch.object(store, "add_documents") as mock_add:
            store.add_texts(["text one", "text two"])
            mock_add.assert_called_once()
            docs = mock_add.call_args[0][0]
            assert len(docs) == 2
            assert docs[0].page_content == "text one"
            assert docs[1].page_content == "text two"

    def test_metadatas_applied_to_documents(self, store):
        with patch.object(store, "add_documents") as mock_add:
            store.add_texts(
                ["text"],
                metadatas=[{"source": "test.txt"}],
            )
            docs = mock_add.call_args[0][0]
            assert docs[0].metadata["source"] == "test.txt"

    def test_missing_metadata_defaults_to_empty_dict(self, store):
        with patch.object(store, "add_documents") as mock_add:
            store.add_texts(["text one", "text two"], metadatas=[{"source": "a"}])
            docs = mock_add.call_args[0][0]
            assert docs[1].metadata == {}


class TestIngestDirectory:
    def test_raises_on_missing_directory(self, store):
        with pytest.raises(FileNotFoundError, match="Directory not found"):
            store.ingest_directory("/nonexistent/path/abc")

    def test_warns_on_empty_directory(self, store, tmp_path, caplog):
        import logging
        with caplog.at_level(logging.WARNING, logger="src.rag.store"):
            store.ingest_directory(tmp_path)
        assert "No documents found" in caplog.text

    def test_loads_txt_files(self, store, tmp_path):
        (tmp_path / "note.txt").write_text("This is a note.")
        with patch.object(store, "add_documents") as mock_add:
            with patch("src.rag.store.TextLoader") as MockLoader:
                MockLoader.return_value.load.return_value = [
                    Document(page_content="This is a note.")
                ]
                store.ingest_directory(tmp_path)
                mock_add.assert_called_once()

    def test_loads_md_files(self, store, tmp_path):
        (tmp_path / "readme.md").write_text("# Title\nContent here.")
        with patch.object(store, "add_documents") as mock_add:
            with patch("src.rag.store.TextLoader") as MockLoader:
                MockLoader.return_value.load.return_value = [
                    Document(page_content="Content.")
                ]
                store.ingest_directory(tmp_path)
                mock_add.assert_called_once()

    def test_skips_unreadable_files_with_warning(self, store, tmp_path, caplog):
        import logging
        (tmp_path / "bad.txt").write_text("content")
        with patch("src.rag.store.TextLoader") as MockLoader:
            MockLoader.return_value.load.side_effect = IOError("permission denied")
            with caplog.at_level(logging.WARNING, logger="src.rag.store"):
                store.ingest_directory(tmp_path)
        assert "Skipping" in caplog.text


class TestRetrieve:
    def test_returns_empty_string_when_no_results(self, store):
        store._get_vector_store().similarity_search.return_value = []
        result = store.retrieve("query")
        assert result == ""

    def test_returns_joined_content(self, store):
        store._get_vector_store().similarity_search.return_value = [
            Document(page_content="chunk one"),
            Document(page_content="chunk two"),
        ]
        result = store.retrieve("query")
        assert "chunk one" in result
        assert "chunk two" in result

    def test_uses_instance_top_k_by_default(self, store):
        store.retrieve("query")
        store._get_vector_store().similarity_search.assert_called_with("query", k=3)

    def test_override_top_k_in_call(self, store):
        store.retrieve("query", top_k=10)
        store._get_vector_store().similarity_search.assert_called_with("query", k=10)

    def test_chunks_separated_by_double_newline(self, store):
        store._get_vector_store().similarity_search.return_value = [
            Document(page_content="A"),
            Document(page_content="B"),
        ]
        result = store.retrieve("q")
        assert result == "A\n\nB"
