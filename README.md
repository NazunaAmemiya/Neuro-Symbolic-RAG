# Legal GraphRAG

## Tổng quan

Dự án xây dựng hệ thống Legal GraphRAG cho văn bản pháp luật Việt Nam. Giai đoạn hiện tại
tập trung vào việc chuẩn hóa dữ liệu nguồn, chuyển đổi tài liệu Office sang biểu diễn có
thể kiểm tra, và chia nội dung thành các chunk phục vụ cho bước truy xuất sau này.

Quy trình dữ liệu hiện có:

```text
Tài liệu Office trên Hugging Face
  → trích xuất và chuẩn hóa
  → Markdown và bằng chứng kiểm tra trên máy local
  → chunk pháp lý, phụ lục và biểu mẫu trên máy local
```

Kho dữ liệu nguồn chấp nhận `.doc`, `.docx` và `.xlsx`. Các tệp Markdown, conversion,
chunk, báo cáo kiểm tra và dữ liệu runtime đều được sinh lại trên từng máy và không được
đưa lên GitHub.

## Phạm vi hiện tại

- Đồng bộ corpus Office từ Hugging Face.
- Chuyển `.doc` cũ sang `.docx` bằng Microsoft Word và kiểm tra chỉ số cấu trúc trước/sau.
- Trích xuất đoạn văn, bảng, ảnh, công thức, footnote và attachment.
- Giữ cấu trúc sheet, merged range, công thức, cached value và data validation của XLSX.
- Sinh Markdown theo đúng cây thư mục nguồn, sử dụng đường dẫn tương đối.
- Chia văn bản luật theo Điều/Khoản/Điểm và chia phụ lục, biểu mẫu theo cửa sổ nội dung.
- Kiểm tra coverage của nguồn, Markdown, bảng, công thức, workbook và chunks.

Embedding, Qdrant, Neo4j, API và giao diện chưa nằm trong phạm vi triển khai hiện tại.

## Yêu cầu hệ thống

- Windows và PowerShell.
- Microsoft Word, dùng cho quá trình chuyển đổi `.doc → .docx`.
- Git.
- Python 3.11.
- `uv` để quản lý môi trường và dependency.

Pipeline sẽ dừng nếu máy không có Microsoft Word; hệ thống không tự động chuyển sang một
converter khác vì kết quả có thể khác giữa các máy.

## Cấu trúc thư mục

```text
backend/app/core/          cấu hình ứng dụng
backend/app/ingestion/     trích xuất, chuẩn hóa, parser và chunker
backend/tests/             unit test cho ingestion và chunking
scripts/                   lệnh đồng bộ, ingest, audit và sinh chunks
docs/                      tài liệu kiến trúc và thiết kế ingestion

data/source_packages/      corpus Office tải từ Hugging Face
data/derived/conversions/  DOCX chuyển đổi từ DOC và báo cáo conversion
data/derived/markdown/     Markdown và media đã trích xuất
data/derived/chunks/       chunks, hierarchy và manifest
data/artifacts/            block JSON, báo cáo extraction và validation queue
data/runtime/              dữ liệu database và container trong tương lai
```

Toàn bộ nội dung dưới `data/` được sinh trên local và đã được cấu hình ignore, ngoại trừ
các tệp `.gitkeep` dùng để giữ cấu trúc thư mục.

## Review-ready data

### 1. Clone repository

```powershell
git clone https://github.com/NazunaAmemiya/Neuro-Symbolic-RAG.git
Set-Location Neuro-Symbolic-RAG
git pull --ff-only
```

### 2. Cấu hình môi trường

```powershell
Copy-Item .env.example .env
notepad .env
```

Khai báo dataset Hugging Face trong `.env`. Chỉ điền `HF_TOKEN` khi dataset yêu cầu xác
thực và không commit token vào repository.

```dotenv
HF_REPO_ID=AmemiyaNazuna/Bidding_Law
HF_TOKEN=
```

Cài dependency bằng Python 3.11:

```powershell
uv sync --python 3.11 --extra dev
```

### 3. Đồng bộ và chuẩn bị dữ liệu

```powershell
uv run python scripts/sync_source_documents.py
uv run python scripts/ingest_documents.py
```

Hai lệnh trên tạo đầy đủ dữ liệu cần thiết để kiểm tra:

```text
data/source_packages/       tài liệu Office gốc từ Hugging Face
data/derived/conversions/   DOCX chuyển đổi và *.conversion.json
data/derived/markdown/      Markdown và media đi kèm
data/artifacts/             blocks.jsonl, report.json và validation_summary.json
```

Mỗi file `.doc` được chuyển sang một DOCX có tên dựa trên SHA-256 của nguồn. Đường dẫn
conversion tương ứng được ghi tại `metadata.converted_docx` trong `report.json`.

### 4. Chạy kiểm tra tự động

```powershell
uv run python scripts/audit_hf_coverage.py
uv run python scripts/audit_markdown_fidelity.py
uv run python scripts/audit_xlsx_fidelity.py
uv run python scripts/audit_formulas.py
uv run pytest
```

Các báo cáo audit được lưu dưới `data/derived/`. Kết quả đạt yêu cầu kỹ thuật có nghĩa là
đường dẫn nguồn, hash, block, bảng, media và công thức đã được bảo toàn theo phạm vi của
từng audit; kết quả này không thay thế bước kiểm tra trực quan hoặc xác minh nội dung pháp
lý.

### 5. Mở dữ liệu để kiểm tra

```powershell
explorer data\source_packages
explorer data\derived\conversions
explorer data\derived\markdown
explorer data\artifacts

Get-ChildItem data\derived\conversions -Recurse -Filter *.conversion.json
Get-Content data\artifacts\validation_summary.json
```

Nội dung cần đối chiếu gồm:

- `.doc` gốc và `.docx` sau chuyển đổi;
- tài liệu Office gốc và Markdown tương ứng;
- bảng có merged cell hoặc bảng lồng nhau;
- công thức OMML, công thức dạng ảnh và biểu thức trong XLSX;
- phụ lục, biểu mẫu và attachment nhúng;
- cảnh báo được ghi trong `report.json` và `validation_summary.json`.

Không chạy `curate_formula_reviews.py` trước khi đối chiếu công thức. Script này tái tạo
các bản phiên âm đã có theo hash nguồn, không phải bằng chứng cho một lần kiểm tra độc lập.

## Sinh dữ liệu sau khi review

Sau khi hoàn tất đối chiếu công thức với tài liệu Office gốc, tạo review registry, sinh lại
artifacts đã xác nhận và tiến hành chunking:

```powershell
uv run python scripts/curate_formula_reviews.py
uv run python scripts/ingest_documents.py --formula-reviews data/derived/formula_reviews.json
uv run python scripts/audit_formulas.py --formula-reviews data/derived/formula_reviews.json
uv run python scripts/generate_chunks.py --formula-reviews data/derived/formula_reviews.json
uv run python scripts/audit_chunks.py
uv run pytest
```

`audit_chunks.py` phải trả về `failed_documents: 0` trước khi chuyển sang embedding hoặc
indexing. Báo cáo kiểm tra nằm tại `data/derived/chunk_audit.json`.

## Nguyên tắc xử lý dữ liệu

### Nguồn và định danh

Hugging Face chỉ lưu tài liệu Office gốc. Mỗi nguồn được định danh bằng đường dẫn tương
đối và hash nội dung, vì vậy các file trùng tên trong những thư mục khác nhau không ghi đè
lên nhau. Mỗi phụ lục hoặc biểu mẫu được liên kết với văn bản chính thông qua `package_id`
và `parent_document_id`.

### DOC và DOCX

Microsoft Word thực hiện conversion `.doc → .docx`. Báo cáo `*.conversion.json` lưu số
trang, đoạn, bảng, shape, field, footnote và các chỉ số cấu trúc khác trước và sau khi lưu.
Conversion chỉ được chấp nhận khi các chỉ số bắt buộc không thay đổi.

### Công thức

Công thức OMML được giữ cùng source locator và bản LaTeX ứng viên. Công thức dạng ảnh giữ
nguyên byte gốc; WMF/EMF có thêm PNG preview trên Windows. OCR công thức chỉ là tùy chọn:

```powershell
uv sync --python 3.11 --extra dev --extra formula-ocr
uv run python scripts/ingest_documents.py --formula-ocr pix2tex
```

Kết quả OCR không được dùng làm dữ liệu xác nhận nếu chưa đối chiếu với tài liệu gốc.
Review công thức được ràng buộc bằng SHA-256 của nguồn và nội dung công thức; review cũ
không được áp dụng nếu tài liệu hoặc media thay đổi.

### Bảng và workbook

Bảng DOCX giữ tọa độ ô, row span, column span và bảng lồng nhau. XLSX giữ tên sheet, tọa
độ ô, công thức, cached value, merged range, data validation, hàng/cột ẩn và media đóng
gói. Không coi cached value là kết luận pháp lý có thẩm quyền.

### Chunking

Văn bản pháp luật được phân tích theo cây Điều/Khoản/Điểm. Phụ lục, biểu mẫu Word và
workbook dùng content window nhưng vẫn giữ liên kết về văn bản cha. Bảng và công thức được
tạo thành chunk độc lập, kèm locator, cấu trúc, asset và trạng thái review.

Chunk audit yêu cầu mỗi source block xuất hiện đúng một lần, không có block lạ, không mất
asset, và không thay đổi metadata của bảng hoặc công thức. Những bảng có hình thức giống
header hoặc boilerplate vẫn được giữ lại cho đến khi có quy tắc phân loại được kiểm chứng.

## Quy tắc lưu trữ

```text
GitHub                 source code, test, cấu hình mẫu và tài liệu hướng dẫn
Hugging Face           tài liệu Office gốc
data/source_packages/  snapshot nguồn trên local
data/derived/          conversion, Markdown, audit và chunks trên local
data/artifacts/        bằng chứng extraction và validation trên local
data/runtime/          volume database và container trên local
```

Không commit corpus, Markdown, chunks, database, index hoặc container volume. Khi bổ sung
Qdrant, Neo4j, SQLite hoặc object storage, repository chỉ lưu source/configuration dùng để
khởi tạo lại; trạng thái runtime tiếp tục nằm dưới `data/runtime/`.
