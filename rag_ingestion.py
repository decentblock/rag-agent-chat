"""Tenant-isolated ingestion and Chroma helpers (metadata-enforced)."""

from __future__ import annotations

import os

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

from chroma_util import chroma_collection_name
from clients import get_embeddings
from config import CHROMA_DB_FILE_PATH
from extensions import db
from models import Collection, Document
from collections_service import find_collection


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
        chunk_overlap=chunk_overlap,
    )

    return text_splitter.split_documents(documents)


def insert_into_chroma(chunks, chroma_physical_name: str) -> int:
    embeddings = get_embeddings()

    vectordb = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=chroma_physical_name,
        persist_directory=CHROMA_DB_FILE_PATH,
    )

    vectordb.persist()
    return len(chunks)


def ingest_document_file(
    file_path: str,
    tenant_id: str,
    collection: Collection,
    document: Document,
    module: str,
) -> dict:
    chunks = load_and_chunk(file_path=file_path, module=module)
    file_name = os.path.basename(file_path)
    for ch in chunks:
        ch.metadata.update(
            {
                "tenant_id": tenant_id,
                "document_id": document.id,
                "collection_id": collection.id,
                "source": file_name,
                "module": module,
            }
        )
    physical = chroma_collection_name(tenant_id, collection.id)
    chunk_count = insert_into_chroma(chunks, physical)
    return {
        "file_name": file_name,
        "collection_id": collection.id,
        "collection_slug": collection.slug,
        "document_id": document.id,
        "chroma_collection": physical,
        "module": module,
        "chunks_inserted": chunk_count,
    }


def list_documents_db(tenant_id: str, collection_slug: str) -> list[dict]:
    coll = find_collection(tenant_id, collection_slug)
    if not coll:
        return []
    q = (
        Document.query.filter(Document.tenant_id == tenant_id)
        .filter(Document.collections.any(Collection.id == coll.id))
        .order_by(Document.created_at.desc())
    )
    return [
        {
            "file_name": d.original_filename,
            "document_id": d.id,
            "module": d.module_tag,
            "created_at": d.created_at.isoformat() + "Z" if d.created_at else None,
        }
        for d in q.all()
    ]


def preview_chunks_db(
    tenant_id: str, collection_slug: str, file_name: str, limit: int = 20
) -> list[dict]:
    coll = find_collection(tenant_id, collection_slug)
    if not coll:
        return []

    doc_row = (
        Document.query.filter_by(tenant_id=tenant_id, original_filename=file_name)
        .filter(Document.collections.any(Collection.id == coll.id))
        .first()
    )

    embeddings = get_embeddings()
    physical = chroma_collection_name(tenant_id, coll.id)
    vectordb = Chroma(
        collection_name=physical,
        embedding_function=embeddings,
        persist_directory=CHROMA_DB_FILE_PATH,
    )

    if doc_row:
        where = {
            "$and": [
                {"tenant_id": tenant_id},
                {"document_id": doc_row.id},
                {"source": file_name},
            ]
        }
    else:
        where = {"$and": [{"tenant_id": tenant_id}, {"source": file_name}]}

    result = vectordb.get(where=where, limit=limit)

    chunks = []
    for doc_text, metadata in zip(result.get("documents", []), result.get("metadatas", [])):
        chunks.append({"text": doc_text, "metadata": metadata})

    return chunks


def delete_document_for_tenant(tenant_id: str, collection_slug: str, file_name: str) -> dict:
    coll = find_collection(tenant_id, collection_slug)
    if not coll:
        raise ValueError("Collection not found for tenant")

    doc_row = (
        Document.query.filter_by(tenant_id=tenant_id, original_filename=file_name)
        .filter(Document.collections.any(Collection.id == coll.id))
        .first()
    )
    if not doc_row:
        raise ValueError("Document not found in collection")

    physical = chroma_collection_name(tenant_id, coll.id)
    embeddings = get_embeddings()
    vectordb = Chroma(
        collection_name=physical,
        embedding_function=embeddings,
        persist_directory=CHROMA_DB_FILE_PATH,
    )
    vectordb._collection.delete(
        where={
            "$and": [
                {"tenant_id": tenant_id},
                {"document_id": doc_row.id},
            ]
        }
    )

    storage_path = doc_row.storage_path
    doc_id = doc_row.id
    db.session.delete(doc_row)
    db.session.commit()

    if storage_path and os.path.isfile(storage_path):
        try:
            os.remove(storage_path)
        except OSError:
            pass

    return {
        "collection_slug": coll.slug,
        "deleted_file": file_name,
        "document_id": doc_id,
    }
