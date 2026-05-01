from flask import Flask, jsonify, request

from config import PORT
from logging_setup import logger
from answer_flow import get_answer
import os
from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename

from rag_ingestion import ingest_file, delete_document_from_collection,list_collections,list_documents,preview_chunks


app = Flask(__name__)

### for upload configs####

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"pdf", "txt"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/chat", methods=["POST"])
def chat():
    payload = request.get_json(force=True, silent=True) or {}
    logger.info("Starting chat")
    user_id = str(payload.get("user_id", "default-session")).strip()
    chat_message = str(payload.get("chat_message", "")).strip()
    logger.info(f"User id {user_id} chat mesaage as  {chat_message}")
    if not chat_message:
        return jsonify({"error": "chat_message is required"}), 400

    try:
        answer = get_answer(chat_message, user_id)
        return jsonify({"answer": answer}), 200

    except Exception as exc:
        logger.exception("chat failed")
        return jsonify({"error": str(exc)}), 500
    
@app.route("/upload-document", methods=["POST"])
def upload_document():
    try:
        file = request.files.get("file")
        collection_name = request.form.get("collection_name")
        module = request.form.get("module", "DEFAULT")

        if not file:
            return jsonify({"error": "No file uploaded"}), 400

        if not collection_name:
            return jsonify({"error": "Collection name is required"}), 400

        if not allowed_file(file.filename):
            return jsonify({"error": "Only PDF and TXT files are supported"}), 400

        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

        file.save(file_path)

        result = ingest_file(
            file_path=file_path,
            collection_name=collection_name,
            module=module
        )

        return jsonify({
            "message": "Document uploaded and indexed successfully",
            "result": result
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route("/delete-document", methods=["DELETE"])
def delete_document():
    try:
        data = request.get_json()

        collection_name = data.get("collection_name")
        file_name = data.get("file_name")

        if not collection_name or not file_name:
            return jsonify({"error": "collection_name and file_name are required"}), 400

        result = delete_document_from_collection(
            collection_name=collection_name,
            file_name=file_name
        )

        return jsonify({
            "message": "Document deleted successfully",
            "result": result
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route("/api/collections", methods=["GET"])
def get_collections():
    try:
        return jsonify({
            "collections": list_collections()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/documents", methods=["GET"])
def get_documents():
    try:
        collection_name = request.args.get("collection_name")

        if not collection_name:
            return jsonify({"error": "collection_name is required"}), 400

        return jsonify({
            "documents": list_documents(collection_name)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

@app.route("/api/chunks", methods=["GET"])
def get_chunks():
    try:
        collection_name = request.args.get("collection_name")
        file_name = request.args.get("file_name")

        if not collection_name or not file_name:
            return jsonify({"error": "collection_name and file_name are required"}), 400

        return jsonify({
            "chunks": preview_chunks(collection_name, file_name)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=True)