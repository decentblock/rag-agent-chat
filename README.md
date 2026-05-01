# RAG Application
Backend service for RAG (Retrieval-Augmented Generation) using:

- Flask
- LangChain
- ChromaDB
- OpenAI

---

## 📁 Project Structure

app.py
answer_flow.py
clients.py
config.py
logging_set.py
memory_store,py
rag_flow.py
rag_ingestion.py
README.md
requirements-dev.txt


⚙️ Setup
1. Create Virtual Environment
  In bash
   python -m venv venv
  Activate VE
 venv\Scripts\activate

2. Install Dependencies
 pip install -r requirements-dev.txt

3. Configuration 
  In config .py set all required value
  OPEN_API_KEY,Models name, Log location , default collection name for chroma db
  Flask services host name , flask service port name

4. Run Application
  
   python app.py

 run as http:<host or local host>:<config port or 5000>

5. API EndPoints

  Services check up
  GET /health

  Upload Documents

  POST /upload-document
  file              → PDF or TXT file
  collection_name   → <COLLECTION_NAME>
  module            → <MODULE_NAME>


  CHAT
  POST /chat
  user_id 
  chat_message
