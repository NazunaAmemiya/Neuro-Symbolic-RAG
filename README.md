# DACN_HK261

'''text
DACN_HK261/
│
├── core/                       # Các module lõi dùng chung (Nơi tạo ra sự kế thừa)
│   ├── __init__.py
│   ├── config.py               # Quản lý biến môi trường, kết nối DBs
│   ├── data_ingestion.py       # Code đọc file và chunking cố định
│   ├── data_loader.py          # Code lấy dữ liệu từ hugging face
│   ├── embeddings.py           # Khởi tạo mô hình nhúng BGE-M3
│   ├── llm_service.py          # Class giao tiếp với Ollama chạy Qwen 7B
│   ├── vector_db.py            # Tương tác với Chroma hoặc Qdrant
│   ├── graph_db.py             # Tương tác với Neo4j (Sẽ dùng ở Baseline 2, 3)
│   └── tracing.py              # Cấu hình Phoenix/Langfuse/Langsmith
│
├── baselines/                  # Nơi lắp ráp 3 pipeline độc lập (Nơi tách biệt để đánh giá)
│   ├── __init__.py
│   ├── baseline_1_vector.py    # Pipeline RAG Truyền thống (Vector DB + LLM)
│   ├── baseline_2_graph.py     # Pipeline Graph-Enhanced RAG (Thêm GraphDB)
│   └── baseline_3_neuro.py     # Neuro-Symbolic RAG (Thêm Symbolic Verification)
│
├── symbolic_logic/             # Thư mục dành riêng cho Baseline 3
│   ├── __init__.py
│   ├── rules.py                # Định nghĩa các luật logic, ràng buộc cứng
│   └── verifier.py             # Thuật toán kiểm tra reasoning path trên đồ thị
│
├── evaluation/                 # Công cụ đo lường các cấu hình RAG
│   ├── __init__.py
│   ├── metrics.py              # Code tính 5 tiêu chí
│   └── compare_baselines.py    # Script chạy 3 baseline cùng lúc để ra bảng so sánh
│
├── app/                        # Giao diện người dùng và API (Làm ở giai đoạn sau)
│   ├── api_server.py           # REST API Backend
│   └── frontend/               # React Code
│
├── .env                        # Chứa các thông số bảo mật (API keys, DB passwords)
├── Dockerfile                  
├── docker-compose.yml          # File khởi tạo hàng loạt Neo4j, Qdrant/Chroma, SeaweedF
├── requirements.txt            # Danh sách thư viện (LangChain, neo4j, qdrant-client...)
└── README.md                   # Hướng dẫn setup và chạy dự án
