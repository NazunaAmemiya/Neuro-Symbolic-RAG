Tôi muốn xây dựng một dự án Legal GraphRAG mới. Hãy làm việc như một kỹ sư phần mềm cẩn thận: luôn kiểm tra cấu trúc project hiện có trước khi sửa, không hard-code theo từng test lỗi, ưu tiên thiết kế tổng quát để sau này có thể thêm văn bản mới mà không phải sửa logic lõi.

## 1. Bối cảnh bài toán

Corpus ban đầu gồm 31 văn bản pháp luật Việt Nam, tất cả đều ở định dạng `.docx`.

Mục tiêu là xây dựng một hệ thống hỏi đáp pháp luật có thể:

- Truy xuất đúng căn cứ ở cấp Điều, Khoản, Điểm.
- Hiển thị câu trả lời có trích dẫn đến chunk nguồn.
- Dùng Qdrant cho tìm kiếm vector kết hợp tìm kiếm từ khóa.
- Dùng Neo4j để lưu cấu trúc pháp lý và các quan hệ liên văn bản như bãi bỏ, thay thế, sửa đổi, viện dẫn.
- Có tracing để debug toàn bộ luồng.
- Có API-first để test thủ công qua Swagger/OpenAPI.
- Có frontend chatbot React tách biệt với backend.
- Có Docker Compose để khởi động đồng bộ các dịch vụ.
- Có Git/GitHub workflow rõ ràng.

Đây là corpus pháp luật Việt Nam. Chỉ cần hỗ trợ câu hỏi tiếng Việt và tiếng Anh. Văn bản nguồn luôn là tiếng Việt.

Không dùng Docling vì đầu vào là DOCX. Hãy dùng thư viện phù hợp như `python-docx`; chỉ cân nhắc `mammoth` hoặc công cụ khác nếu cần giữ cấu trúc tốt hơn.

## 2. Nguyên tắc kiến trúc bắt buộc

- Không dùng regex để hard-code các mẫu câu hỏi cụ thể.
- Không thêm `if/else` chỉ để chữa một test bị sai. Mỗi lỗi phải được truy về nguyên nhân kiến trúc hoặc dữ liệu.
- Không để LLM tự quyết toàn bộ tính đúng đắn pháp lý. LLM chỉ diễn đạt dựa trên evidence đã được kiểm tra.
- Không coi similarity score cao là căn cứ pháp lý.
- Không để bước lọc evidence xóa sạch candidate pool. Nếu retrieval đã có candidate, việc selector chọn rỗng phải được xem là selection failure và cần fail-open có trace.
- Không dùng Qdrant để lưu lịch sử chat chính. Lưu session, message, state và summary trong SQLite hoặc Redis; Qdrant chỉ phục vụ truy xuất ngữ nghĩa khi thật sự cần.
- Không nạp toàn bộ Điều hoặc toàn bộ văn bản vào context một cách vô điều kiện.
- Bảo toàn cấu trúc pháp luật: câu hỏi liệt kê đầy đủ phải có khả năng lấy đủ các điểm/khoản cùng scope; câu hỏi nhiều ý phải không làm evidence của ý này xóa evidence của ý khác.
- Tách rõ dữ liệu phục vụ embedding và dữ liệu hiển thị:
  - `display_text`: body sạch để hiển thị/citation.
  - `embedding_text`: body kèm preamble cần thiết của Điều/Khoản cha để chunk cấp Điểm không bị mất nghĩa khi embedding.
- Mọi chunk phải có ID ổn định, tái tạo được sau ingest.

## 3. Stack mong muốn

Backend:

- Python 3.11+
- FastAPI
- Pydantic Settings
- SQLAlchemy hoặc sqlite3 có repository layer rõ ràng
- Uvicorn
- pytest
- Ruff hoặc tương đương để lint/format

Dữ liệu và retrieval:

- Qdrant
- Neo4j
- SQLite cho session/history/state
- SeaweedFS hoặc MinIO cho file DOCX gốc và artifact ingest
- Qdrant native BM25/sparse search kết hợp dense vector search
- Reciprocal Rank Fusion để gộp dense và BM25

Mô hình local:

- Ollama chạy thường trực
- Embedding: Jina embeddings multilingual phù hợp tiếng Việt/Anh
- LLM generation: Qwen 2.5 3B Instruct hoặc model local tương đương
- Không mặc định thêm cross-encoder reranker nếu VRAM hạn chế. Nếu cần rerank, thiết kế sao cho có thể bật/tắt bằng config.

Quan sát và vận hành:

- Langfuse self-host để tracing
- Docker Compose
- GitHub Actions tối thiểu chạy lint và test
- `.env.example`, `.gitignore`, README đầy đủ

Frontend:

- React + TypeScript + Vite
- Gọi API backend, không render HTML chatbot từ FastAPI
- Hỗ trợ SSE cho trạng thái xử lý và streaming câu trả lời
- Có session sidebar, tạo/xóa/đổi tên/ghim hội thoại
- Vùng sidebar và vùng chat phải scroll độc lập

## 4. Cấu trúc thư mục mong muốn

Hãy tạo hoặc điều chỉnh cấu trúc gần như sau:

project-root/
  backend/
    app/
      api/
      core/
      db/
      models/
      schemas/
      services/
      repositories/
      ingestion/
      retrieval/
      graph/
      generation/
      tracing/
      tests/
    alembic/                  # nếu dùng SQLAlchemy migration
    requirements.txt hoặc pyproject.toml
  frontend/
    src/
      api/
      components/
      hooks/
      pages/
      types/
    package.json
  data/
    source_docs/              # chỉ dùng local development, không commit DOCX nhạy cảm
    evaluation/
  scripts/
    ingest_documents.py
    rebuild_qdrant.py
    rebuild_neo4j.py
    evaluate_retrieval.py
    smoke_test.py
  docker/
  docs/
    architecture.md
    ingestion.md
    api.md
    evaluation.md
    tracing.md
  docker-compose.yml
  .env.example
  .gitignore
  README.md
  PLAN.md

Không tạo file thừa hoặc script tạm rồi để lại trong repository.

## 5. Thiết kế dữ liệu và ingest DOCX

Hãy thiết kế ingest pipeline cho 31 DOCX theo các bước:

1. Lưu file DOCX gốc vào object storage.
2. Trích xuất nội dung từ DOCX.
3. Chuẩn hóa khoảng trắng, header/footer lặp, mục lục và ký tự không cần thiết.
4. Nhận diện cấu trúc:
   - Văn bản
   - Phần
   - Chương
   - Mục
   - Điều
   - Khoản
   - Điểm
5. Sinh document metadata:
   - document_id
   - doc_number
   - doc_name
   - issue_date
   - effective_date
   - legal_status
   - source_file
6. Sinh chunk cấp pháp lý phù hợp:
   - Điều không có Khoản
   - Khoản
   - Điểm
7. Mỗi chunk cần tối thiểu:
   - chunk_id
   - document_id
   - document number/name
   - legal status
   - chapter/article/clause/point labels
   - display_text
   - embedding_text
   - parent IDs
   - source location
8. Tạo artifact trung gian có thể audit:
   - raw extraction
   - normalized text
   - parsed hierarchy
   - chunks JSON
   - relation candidates
9. Ingest phải idempotent: chạy lại không sinh duplicate.
10. Có validation cho:
   - chunk ID trùng
   - node mồ côi
   - chunk thiếu metadata quan trọng
   - số lượng chunk bất thường
   - quan hệ không có evidence
   - DOCX không parse được

Không được giả định mọi DOCX có format giống hệt nhau. Hãy thiết kế parser theo cấu trúc, có cấu hình và báo cáo các đoạn không nhận diện được.

## 6. Thiết kế Qdrant và hybrid retrieval

Dùng ít nhất hai collection hoặc hai nhóm dữ liệu logic:

1. `legal_chunks`
   - Dense vector từ `embedding_text`
   - Sparse/BM25 từ nội dung tiếng Việt
   - Payload đầy đủ metadata pháp lý

2. `document_profiles`
   - Mỗi văn bản một profile ngắn: số hiệu, tên, phạm vi điều chỉnh, mục lục cấp cao, thuật ngữ chính
   - Dùng để chọn văn bản phù hợp trước khi truy xuất chunk chi tiết

Luồng retrieval đề xuất:

User question
  → kiểm tra loại lượt hội thoại
  → chuẩn hóa câu hỏi thành truy vấn pháp lý độc lập nếu là follow-up
  → document routing bằng profile văn bản
  → dense search + BM25 search
  → RRF fusion
  → giữ fully-ranked pool
  → graph expansion có kiểm soát
  → evidence allocation
  → generation
  → citation/answer validation

Yêu cầu quan trọng:

- Câu hỏi tiếng Việt: dense và BM25 đều dùng truy vấn tiếng Việt.
- Câu hỏi tiếng Anh: dense có thể dùng câu hỏi gốc; BM25 dùng bản tiếng Việt được chuẩn hóa.
- Không cần hỗ trợ các ngôn ngữ khác ở giai đoạn đầu.
- Không dịch chunk nguồn sang tiếng Anh.
- Citation luôn trỏ đến chunk tiếng Việt gốc.
- Khi user nhắc rõ một văn bản không có trong corpus, không được rơi sang nearest-neighbour của văn bản khác. Trả trạng thái “văn bản chưa có trong corpus”.
- Không để default top-k là một con số ngẫu nhiên. Đặt config rõ ràng, ví dụ retrieval pool 16 hoặc 20 trước allocation; giải thích trong README vì sao.

## 7. Thiết kế Neo4j

Graph schema tối thiểu:

- `Document`
- `Part`
- `Chapter`
- `Section`
- `Article`
- `Clause`
- `Point`

Containment relations:

- `CONTAINS`

Legal relations có type:

- `BAI_BO`
- `THAY_THE`
- `SUA_DOI_BO_SUNG`
- `VIEN_DAN`

Mỗi legal relation phải có:

- source node
- target node
- relation type
- evidence_chunk_id
- source document ID
- extraction method
- reviewed flag hoặc confidence phù hợp

Không coi một relation là đúng chỉ vì regex phát hiện từ “bãi bỏ” hay “thay thế”. Relation phải có chunk chứng minh và được audit trước khi dùng trong câu trả lời.

Graph expansion phải lazy:

- Qdrant result là anchor.
- Neo4j ban đầu chỉ trả structural descriptor: parent, sibling count, relation type, evidence chunk ID, estimated size.
- Chỉ materialize text khi evidence allocator xác định cần thiết.
- Không tự đưa toàn bộ Điều lớn vào context.

## 8. Evidence allocation và context management

Thiết kế EvidencePackBuilder/EvidenceAllocator thành module độc lập, không phải prompt.

Evidence cần được phân nhóm:

- Căn cứ trực tiếp cho câu trả lời.
- Căn cứ về quan hệ pháp lý, ví dụ bãi bỏ/thay thế.
- Bối cảnh cấu trúc cần thiết, ví dụ preamble của Khoản cha.
- Căn cứ bổ trợ.

Quy tắc:

- Câu hỏi một ý: ưu tiên provision trực tiếp.
- Câu hỏi “liệt kê toàn bộ”: lấy complete scope phù hợp, ví dụ đủ các Điểm a/b/c hoặc Khoản 1–4.
- Câu hỏi nhiều ý: bảo toàn evidence cho từng ý; complete scope của ý A không được xóa provision trực tiếp của ý B.
- Chỉ loại evidence trùng lặp khi có quan hệ bao hàm cấu trúc rõ ràng.
- Không loại toàn bộ primary evidence chỉ vì có complete scope.
- Nếu một scope quá lớn, chia ở ranh giới Khoản/Điểm, không dùng LLM tóm tắt nội dung luật làm evidence.
- Tính budget từ:
  - context window của model
  - system prompt
  - session state/summary cần thiết
  - evidence
  - answer reserve
  - safety margin
- Trace rõ evidence nào được chọn, evidence nào bị bỏ và lý do.

## 9. Generation và validation

Generation:

- LLM chỉ được trả lời từ evidence đã cấp.
- Prompt phải yêu cầu:
  - trả lời đúng ngôn ngữ user yêu cầu, trong phạm vi Việt/Anh;
  - văn phong trang trọng vừa phải;
  - không suy diễn khi evidence không đủ;
  - gắn citation ID cho từng nhận định pháp lý;
  - không bịa điều/khoản/văn bản.
- Session có thể lưu presentation preference như ngôn ngữ hoặc mức độ diễn đạt.
- Presentation preference không được biến chatbot thành bot trả lời mọi chủ đề ngoài pháp luật.
- Các lượt xã giao như “hello” không được truy xuất database.
- Các yêu cầu ngoài phạm vi pháp luật phải được từ chối lịch sự, không gọi retrieval.

Validation:

- Citation validator kiểm tra citation ID có thuộc evidence pack hay không.
- Answer validator đối chiếu:
  - user question
  - answer draft
  - evidence pack
- Validator không được tự thêm evidence mới.
- Nếu evidence chưa đủ, trả lời rõ “chưa đủ căn cứ trong corpus để kết luận”.
- Validation không được trở thành nhiều lớp rule chồng lên nhau. Thiết kế contract dữ liệu rõ giữa retrieval, evidence allocation, generation và validation.

## 10. Session memory

Không dùng vector search làm cơ chế history mặc định.

Dùng SQLite hoặc Redis để lưu:

Bảng sessions:
- session_id
- title
- pinned
- created_at
- updated_at
- presentation_language
- presentation_style
- state_json
- topic_summary

Bảng messages:
- message_id
- session_id
- role
- content
- created_at
- status
- retrieval_trace_id

Bảng turns, nếu cần:
- turn_id
- session_id
- user_message_id
- assistant_message_id
- topic label
- summary snapshot

Yêu cầu:

- Lưu user và assistant theo transaction sau khi câu trả lời hoàn tất để tránh history nửa lượt nếu request bị hủy hoặc server dừng.
- Dùng topic/state tracking và summary có chọn lọc, không gửi toàn bộ lịch sử vào LLM mỗi lượt.
- Follow-up gần dùng state và vài lượt gần nhất.
- Follow-up xa dùng topic summary, không cần embedding toàn bộ history.
- Session mới chỉ được persist khi user gửi message đầu tiên, tránh session rác khi bấm “tạo chat mới” rồi reload.
- Khi xóa session, xóa session/state/message/turn liên quan theo transaction; không xóa dữ liệu pháp luật trong Qdrant hoặc Neo4j.

## 11. API-first

Thiết kế API REST rõ ràng, toàn bộ logic có thể test qua Swagger.

Tối thiểu:

- `GET /health`
- `POST /v1/sessions`
- `GET /v1/sessions`
- `GET /v1/sessions/{session_id}`
- `PATCH /v1/sessions/{session_id}`
- `DELETE /v1/sessions/{session_id}`
- `GET /v1/sessions/{session_id}/messages`
- `POST /v1/sessions/{session_id}/messages`
- `POST /v1/sessions/{session_id}/messages/stream`
- `POST /v1/sessions/{session_id}/messages/cancel`
- `POST /v1/sessions/{session_id}/retrieval/debug`

Phân biệt rõ:

- `/messages`: trả JSON hoàn chỉnh sau khi xử lý xong.
- `/messages/stream`: SSE, gửi event thật theo tiến trình:
  - `status`
  - `retrieval_started`
  - `retrieval_completed`
  - `evidence_selected`
  - `generation_started`
  - `answer_delta`
  - `completed`
  - `cancelled`
  - `error`

Không chỉ trả một event cuối rồi gọi đó là streaming.

Không tạo route HTML “legacy”. Frontend React được phục vụ độc lập; FastAPI chủ yếu trả API/Swagger.

## 12. Frontend

Thiết kế UI chatbot React:

- Sidebar session độc lập với vùng chat.
- Sidebar và chat scroll riêng.
- Tạo/xóa/đổi tên/ghim session.
- Xác nhận xóa bằng modal giữa màn hình.
- Tin nhắn assistant hiển thị citation có thể mở evidence nguồn.
- Có khu vực retrieval debug chỉ dành cho kiểm thử.
- Ô nhập tự mở rộng tối đa khoảng 7–8 dòng.
- Có nút dừng khi SSE đang trả lời.
- Nếu dừng giữa chừng:
  - không lưu assistant answer dở dang như một câu trả lời hoàn chỉnh;
  - message user vẫn có thể giữ;
  - cho phép gửi lại hoặc chỉnh sửa message user.
- UI status phải phản ánh đúng stage thực tế; không hiển thị cố định “Đang tra cứu căn cứ” cho lời chào.

## 13. Langfuse tracing

Dùng Langfuse self-host qua Docker Compose.

Trace tối thiểu phải có:

- session ID
- turn ID
- user message
- normalized query
- language/presentation preference
- document routing result
- dense retrieval result
- BM25 result
- RRF result
- graph expansion descriptor
- evidence allocation result
- selected/omitted evidence IDs
- token/context budget
- generation input/output
- citation validation result
- answer validation result
- latency từng stage
- lỗi kỹ thuật nếu có

Không ghi API key hoặc secret vào trace.

Có config để tắt tracing mà pipeline vẫn hoạt động.

## 14. Docker và môi trường

Tạo `docker-compose.yml` cho:

- qdrant
- neo4j
- seaweedfs hoặc minio
- langfuse và dependency của Langfuse
- backend
- frontend

Ollama có thể chạy ngoài Docker nếu cần GPU/Windows host, nhưng phải được cấu hình qua biến môi trường:

- `OLLAMA_BASE_URL`
- `GENERATION_MODEL`
- `EMBEDDING_MODEL`

Tạo:

- `.env.example`
- health check cho service chính
- volume named cho dữ liệu Qdrant, Neo4j, Langfuse và object storage
- network nội bộ
- README hướng dẫn chạy từ máy mới

Không hard-code password, URI, collection name hoặc model name trong source code. Dùng Pydantic Settings.

## 15. Git và GitHub

Khởi tạo repository Git nếu chưa có.

Tạo `.gitignore` cho:

- `.env`
- `.venv`
- `node_modules`
- database local
- Qdrant/Neo4j volumes
- Langfuse data
- file DOCX nguồn nếu không được phép commit
- cache model
- artifact tạm
- log
- test coverage
- IDE files

Cấu trúc branch:

- `main`: ổn định
- `develop`: tích hợp
- `feature/...`: từng tính năng

Tạo GitHub Actions tối thiểu:

- backend lint
- backend tests
- frontend build/lint
- không chạy integration test cần GPU hoặc Ollama trong CI mặc định

Tạo README gồm:

- mục tiêu hệ thống
- kiến trúc
- sơ đồ luồng
- yêu cầu máy
- cấu hình `.env`
- cách chạy Docker
- cách chạy Ollama
- cách ingest 31 DOCX
- cách rebuild Qdrant/Neo4j an toàn
- cách chạy test
- cách dùng Swagger
- cách xem Langfuse

## 16. Kiểm thử và đánh giá

Tạo evaluation dataset riêng, không lấy câu hỏi LLM sinh ra làm ground truth tuyệt đối.

Mỗi test nên có:

- question
- expected document IDs
- expected chunk IDs hoặc phạm vi cấu trúc
- expected legal relation nếu có
- expected answer language
- expected behavior: answer / insufficient evidence / explicit unknown document

Đo tối thiểu:

- Hit@K
- MRR
- evidence coverage
- relation hit
- citation validity
- answer groundedness
- latency từng stage

So sánh tối thiểu ba cấu hình:

1. Dense/vector RAG cơ bản.
2. Hybrid RAG có Qdrant BM25 + dense retrieval.
3. Graph-enhanced hoặc Neuro-Symbolic RAG có Neo4j, typed relation và evidence validation.

## 17. Cách làm việc

Trước khi code:

1. Kiểm tra toàn bộ repository.
2. Báo cáo ngắn:
   - hiện có gì;
   - thiếu gì;
   - rủi ro chính;
   - kế hoạch chia task.
3. Đề xuất thứ tự thực hiện nhỏ, có thể kiểm tra sau mỗi task.
4. Không tự ý rebuild/xóa dữ liệu Qdrant hoặc Neo4j khi chưa xác nhận rõ target và backup.
5. Sau mỗi task:
   - chạy test phù hợp;
   - báo file đã thay đổi;
   - nêu cách test bằng tay;
   - chỉ chuyển task tiếp theo khi task hiện tại không còn dở dang.