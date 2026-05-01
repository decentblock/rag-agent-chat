import chromadb
from config import CHROMA_DB_FILE_PATH
from clients import get_embeddings
from langchain_community.vectorstores import Chroma
import os
from langchain_community.document_loaders import TextLoader, PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter



def get_chroma_client():
    return chromadb.PersistentClient(path=CHROMA_DB_FILE_PATH)


def list_collections():
    client = get_chroma_client()
    collections = client.list_collections()
    return [c.name for c in collections]


def list_documents(collection_name: str):
    embeddings = get_embeddings()

    vectordb = Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=CHROMA_DB_FILE_PATH
    )

    result = vectordb.get()

    documents = {}

    for metadata in result.get("metadatas", []):
        if not metadata:
            continue

        source = metadata.get("source", "unknown")
        module = metadata.get("module", "DEFAULT")

        documents[source] = {
            "file_name": source,
            "module": module
        }

    return list(documents.values())


def preview_chunks(collection_name: str, file_name: str, limit: int = 5):
    embeddings = get_embeddings()

    vectordb = Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=CHROMA_DB_FILE_PATH
    )

    result = vectordb.get(
        where={"source": file_name},
        limit=limit
    )

    chunks = []

    for doc, metadata in zip(result.get("documents", []), result.get("metadatas", [])):
        chunks.append({
            "text": doc,
            "metadata": metadata
        })

    return chunks


def load_and_chunk(file_path: str, module: str, chunk_size: int = 1000, chunk_overlap: int = 200):
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"The file {file_path} does not exist")

    if file_path.lower().endswith(".txt"):
        loader = TextLoader(file_path, encoding="utf-8")
    elif file_path.lower().endswith(".pdf"):
        loader = PyPDFLoader(file_path)
    else:
        raise ValueError("Unsupported file type. Only txt and pdf are supported.")

    documents = loader.load()
    file_name = os.path.basename(file_path)

    for doc in documents:
        doc.metadata["module"] = module
        doc.metadata["source"] = file_name

    text_splitter = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n", " ", ""],
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap
    )

    return text_splitter.split_documents(documents)


def insert_into_chroma(chunks, collection_name: str):
    embeddings = get_embeddings()

    vectordb = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=collection_name,
        persist_directory=CHROMA_DB_FILE_PATH
    )

    vectordb.persist()
    return len(chunks)


def ingest_file(file_path: str, collection_name: str, module: str):
    chunks = load_and_chunk(
        file_path=file_path,
        module=module,
        chunk_size=1000,
        chunk_overlap=200
    )

    chunk_count = insert_into_chroma(
        chunks=chunks,
        collection_name=collection_name
    )

    return {
        "file_name": os.path.basename(file_path),
        "collection_name": collection_name,
        "module": module,
        "chunks_inserted": chunk_count
    }


def delete_document_from_collection(collection_name: str, file_name: str):
    embeddings = get_embeddings()

    vectordb = Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=CHROMA_DB_FILE_PATH
    )

    vectordb._collection.delete(where={"source": file_name})

    return {
        "collection_name": collection_name,
        "deleted_file": file_name
    }