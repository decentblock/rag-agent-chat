"""Tenant-isolated ingestion and Chroma helpers (metadata-enforced)."""

from __future__ import annotations

import json
import os
from datetime import datetime

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

from chroma_util import chroma_collection_name
from clients import get_embeddings
from config import CHROMA_DB_FILE_PATH, EMEDDING_MODEL
from extensions import db
from logging_setup import logger
from models import Collection, Document
from collections_service import find_collection
from services.kb_debug import record_kb_audit


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
    *,
    actor_user_id: str | None = None,
) -> dict:
    chunks = load_and_chunk(file_path=file_path, module=module)
    file_name = os.path.basename(file_path)
    if not chunks:
        logger.warning(
            "kb_ingest_no_chunks tenant=%s document=%s file=%s (empty PDF text layer or blank TXT)",
            tenant_id,
            document.id,
            file_name,
        )
        document.indexed_chunk_count = 0
        document.indexed_at = datetime.utcnow()
        document.ingest_detail_json = json.dumps(
            {
                "warning": "no_chunks_extracted",
                "chroma_collection": chroma_collection_name(tenant_id, collection.id),
                "chroma_persist_dir": CHROMA_DB_FILE_PATH,
                "embedding_model": EMEDDING_MODEL,
                "original_filename": file_name,
            }
        )
        record_kb_audit(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            event_type="ingest_skipped_empty",
            message=f"No extractable text for {file_name}",
            document_id=document.id,
            collection_id=collection.id,
            payload={"reason": "zero_chunks_after_split"},
        )
        return {
            "file_name": file_name,
            "collection_id": collection.id,
            "collection_slug": collection.slug,
            "document_id": document.id,
            "chroma_collection": chroma_collection_name(tenant_id, collection.id),
            "module": module,
            "chunks_inserted": 0,
            "indexed_chunk_count": 0,
            "embedding_model": EMEDDING_MODEL,
            "warning": "no_chunks_extracted",
        }

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

    detail = {
        "chroma_collection": physical,
        "chroma_persist_dir": CHROMA_DB_FILE_PATH,
        "embedding_model": EMEDDING_MODEL,
        "chunks_inserted": chunk_count,
        "original_filename": file_name,
        "module": module,
    }
    document.indexed_chunk_count = chunk_count
    document.indexed_at = datetime.utcnow()
    document.ingest_detail_json = json.dumps(detail)

    logger.info(
        "kb_ingest_ok tenant=%s document=%s collection=%s chunks=%s chroma=%s model=%s",
        tenant_id,
        document.id,
        collection.id,
        chunk_count,
        physical,
        EMEDDING_MODEL,
    )
    record_kb_audit(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        event_type="ingest_complete",
        message=f"Indexed {chunk_count} chunks for {file_name}",
        document_id=document.id,
        collection_id=collection.id,
        payload={
            "chroma_collection": physical,
            "chunks": chunk_count,
            "module": module,
            "embedding_model": EMEDDING_MODEL,
        },
    )

    return {
        "file_name": file_name,
        "collection_id": collection.id,
        "collection_slug": collection.slug,
        "document_id": document.id,
        "chroma_collection": physical,
        "module": module,
        "chunks_inserted": chunk_count,
        "indexed_chunk_count": chunk_count,
        "embedding_model": EMEDDING_MODEL,
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
            "indexed_chunk_count": int(d.indexed_chunk_count or 0),
            "indexed_at": d.indexed_at.isoformat() + "Z" if getattr(d, "indexed_at", None) else None,
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
