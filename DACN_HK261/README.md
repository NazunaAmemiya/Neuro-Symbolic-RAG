# DACN_HK261

## Project Structure

```text
DACN_HK261/
├── core/                       # Shared core modules
│   ├── __init__.py
│   ├── config.py               # Environment variables and database configuration
│   ├── data_ingestion.py       # Document loading and fixed-size chunking
│   ├── embeddings.py           # BGE-M3 embedding model initialization
│   ├── llm_service.py          # Interface for Qwen 7B running through Ollama
│   ├── vector_db.py            # Vector database integration (Chroma or Qdrant)
│   ├── graph_db.py             # Neo4j integration for Baselines 2 and 3
│   └── tracing.py              # Tracing and observability configuration
│
├── baselines/                  # Three independent RAG pipelines
│   ├── __init__.py
│   ├── baseline_1_vector.py    # Baseline 1: Traditional Vector RAG
│   ├── baseline_2_graph.py     # Baseline 2: Graph-Enhanced RAG
│   └── baseline_3_neuro.py     # Baseline 3: Neuro-Symbolic RAG
│
├── symbolic_logic/             # Symbolic reasoning components for Baseline 3
│   ├── __init__.py
│   ├── rules.py                # Logical rules and hard constraints
│   └── verifier.py             # Reasoning-path verification on the knowledge graph
│
├── evaluation/                 # Evaluation and comparison of RAG baselines
│   ├── __init__.py
│   ├── metrics.py              # Implementation of five evaluation metrics
│   └── compare_baselines.py    # Run and compare all three baselines
│
├── app/                        # User interface and API (planned)
│   ├── backend/
│   │   ├── api_server.py       # REST API backend  
│   └── frontend/               # React frontend
│
├── .env                        # Environment variables and credentials (local only)
├── docker-compose.yml          # Configuration for Neo4j, Qdrant/Chroma, and SeaweedFS
├── requirements.txt             # Python dependencies
└── README.md                   # Project documentation
