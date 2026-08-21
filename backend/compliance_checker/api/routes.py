"""
compliance_checker/api/routes.py — 4 route BUP-02 (upload file / import link / batch CSV
/ batch JSON), tách khỏi backend/main.py (main.py giờ chỉ include_router(router) ở đây,
không tự định nghĩa handler nữa). Toàn bộ THÂN HÀM giữ NGUYÊN 100% so với trước khi tách
file — chỉ đổi @app.xxx("/api/compliance/...") -> @router.xxx("/...") nhờ APIRouter(prefix=
"/api/compliance"), 2 cách viết cho ra ĐÚNG cùng 1 URL cuối cùng, KHÔNG đổi hành vi API.

Xem docs.md mục 1-4 để biết route nào dùng khi nào.
"""

import json
import os
import tempfile
import uuid

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse

from compliance_checker.schemas import ComplianceCheckRequest, ComplianceBatchRequest, DesignComplianceResult, BatchReport
from compliance_checker.orchestrator import process_one_design, process_batch, process_batch_streaming
from compliance_checker.ingestion.csv_batch import parse_csv_rows, parse_xlsx_rows, parse_batch_bytes, batch_row_to_csv_dict, write_batch_csv, decode_csv_bytes
from compliance_checker.ingestion.link_normalizer import normalize_url_to_bytes

router = APIRouter(prefix="/api/compliance")


@router.post("/check", response_model=DesignComplianceResult)
async def compliance_check(req: ComplianceCheckRequest):
    """
    Cách nhập 'base64/link': FE gửi image_base64 (upload đã encode sẵn) HOẶC url (Google
    Drive/Dropbox/S3/direct image URL) — đúng 1 trong 2, hoặc file_path cho test nội bộ
    (vd compliance_checker/test_pdf_images_link/). Validate tối thiểu ở đây, phần còn lại
    (đúng định dạng, link sống hay không...) để orchestrator/file_loader tự báo lỗi rõ ràng.
    """
    if not (req.image_base64 or req.file_path or req.url):
        raise HTTPException(status_code=422, detail="Cần ít nhất 1 trong 3: image_base64, file_path, url")
    try:
        return await process_one_design(
            image_base64=req.image_base64,
            file_path=req.file_path,
            url=req.url,
            platform=req.platform,
            target_country=req.target_country or "US",
            niche_hint=req.niche_hint,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check-upload", response_model=DesignComplianceResult)
async def compliance_check_upload(
    file: UploadFile = File(...),
    platform: str = Form(default=None),
    target_country: str = Form(default="US"),
    niche_hint: str = Form(default=None),
):
    """
    Cách nhập 'upload file' đúng nghĩa (multipart) — bắt buộc PNG/JPG theo brief, bonus
    PDF/PSD cũng đi qua route này (file_loader.py tự phân nhánh theo phần mở rộng).
    """
    ext = os.path.splitext(file.filename or "")[1].lower() or ".png"
    tmp_path = os.path.join(tempfile.gettempdir(), f"compliance_upload_{uuid.uuid4().hex}{ext}")
    try:
        raw_bytes = await file.read()
        with open(tmp_path, "wb") as f:
            f.write(raw_bytes)
        return await process_one_design(
            file_path=tmp_path, platform=platform, target_country=target_country or "US", niche_hint=niche_hint
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


@router.post("/batch-csv")
async def compliance_batch_csv(
    file: UploadFile = File(...),
    platform: str = Form(default=None),
    target_country: str = Form(default="US"),
    max_concurrency: int = Form(default=1),  # (2026-08-22) mặc định đổi 5->1, xem orchestrator.process_batch
):
    """
    Cách nhập 'import CSV/XLSX' — batch xử lý hàng loạt qua file upload trực tiếp. Hỗ trợ CẢ
    2 định dạng, tự nhận theo phần mở rộng file: .xlsx (đọc bằng openpyxl — vd file mẫu THẬT
    của BGK `design_samples_template.xlsx`, có cột `expected_*` để tự so verdict — xem
    csv_batch.py/orchestrator.process_batch) hoặc .csv/mặc định (encoding utf-8-sig để đọc
    đúng file Excel xuất ra có BOM). Row-level fault isolation: 1 dòng lỗi KHÔNG làm sập cả
    batch (đảm bảo trong orchestrator.process_batch). Trả về JSON đầy đủ (BatchReport-shape,
    kèm `verdict_accuracy`/`graded_count` nếu input có cột expected_verdict) KÈM 'csv_export'
    (text CSV báo cáo tổng hợp, FE tự cho user tải xuống) — backend hoàn toàn stateless.
    """
    try:
        raw_bytes = await file.read()
        filename = (file.filename or "").lower()
        if filename.endswith(".xlsx"):
            rows = parse_xlsx_rows(raw_bytes)
        else:
            rows = parse_csv_rows(decode_csv_bytes(raw_bytes))
        if not rows:
            raise HTTPException(status_code=422, detail="File rỗng hoặc không đọc được dòng nào (kiểm tra đúng định dạng .csv/.xlsx và có header đúng cột).")
        batch_result = await process_batch(
            rows, platform=platform, target_country=target_country or "US", max_concurrency=max_concurrency
        )
        csv_rows = [batch_row_to_csv_dict(r) for r in batch_result["rows"]]
        batch_result["csv_export"] = write_batch_csv(csv_rows)
        return batch_result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-json", response_model=BatchReport)
async def compliance_batch_json(req: ComplianceBatchRequest):
    """
    Bản JSON body (thay vì multipart) của batch-csv — cho FE/giám khảo tự paste nội dung CSV
    dạng text thẳng vào JSON, không cần dựng multipart form.

    (2026-08-21) Đúng 1 trong 2: `csv_content` (text thô, hành vi CŨ không đổi) HOẶC
    `batch_file_url` (MỚI) — link tới file batch (Google Drive file tĩnh .xlsx/.csv, Google
    Sheets link "edit", Dropbox, hoặc URL trực tiếp) — backend tự tải bằng
    normalize_url_to_bytes() (link_normalizer.py, tự rewrite Drive/Sheets/Dropbox đúng dạng
    tải trực tiếp) rồi tự sniff xlsx/csv qua magic bytes (parse_batch_bytes, csv_batch.py) vì
    link không luôn có đuôi file rõ ràng để dựa vào.
    """
    try:
        if req.batch_file_url:
            raw_bytes = await normalize_url_to_bytes(req.batch_file_url)
            rows = parse_batch_bytes(raw_bytes)
        elif req.csv_content:
            rows = parse_csv_rows(req.csv_content)
        else:
            raise HTTPException(status_code=422, detail="Cần đúng 1 trong 2: csv_content hoặc batch_file_url")
        if not rows:
            raise HTTPException(status_code=422, detail="Nguồn batch rỗng hoặc không đọc được dòng nào (kiểm tra đúng định dạng/quyền truy cập link).")
        return await process_batch(
            rows, platform=req.platform, target_country=req.target_country or "US", max_concurrency=req.max_concurrency
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _batch_ndjson_generator(rows: list[dict], platform: "str | None", target_country: str, max_concurrency: int):
    """
    (2026-08-22, MỚI) Bọc process_batch_streaming() (orchestrator.py) thành text NDJSON thật —
    mỗi item yield ra là 1 dòng JSON kết thúc bằng "\n". Item cuối cùng ("summary" trong dict)
    được BỔ SUNG csv_export ở ĐÂY (không phải orchestrator.py) — build từ chính các row đã
    stream qua (tự tích luỹ trong closure `clean_rows`), giữ đúng ranh giới trách nhiệm cũ:
    orchestrator.py không cần biết gì về csv_batch.py/định dạng CSV xuất ra.
    """
    clean_rows: list[dict] = []
    async for item in process_batch_streaming(rows, platform=platform, target_country=target_country, max_concurrency=max_concurrency):
        if "summary" in item:
            summary = item["summary"]
            if "error" not in summary:  # lỗi hạ tầng ngoài dự kiến (xem orchestrator.py) -> khỏi build CSV, csv_rows có thể thiếu
                csv_rows = [batch_row_to_csv_dict(r) for r in clean_rows]
                summary["csv_export"] = write_batch_csv(csv_rows)
            yield json.dumps({"summary": summary}, ensure_ascii=False) + "\n"
        else:
            clean_rows.append(item)
            yield json.dumps(item, ensure_ascii=False) + "\n"


@router.post("/batch-csv-stream")
async def compliance_batch_csv_stream(
    file: UploadFile = File(...),
    platform: str = Form(default=None),
    target_country: str = Form(default="US"),
    max_concurrency: int = Form(default=1),
):
    """
    (2026-08-22, MỚI) Biến thể STREAMING (NDJSON) của /batch-csv — mỗi dòng trả về NGAY khi xử
    lý xong thay vì đợi TOÀN BỘ batch rồi mới gộp 1 JSON khổng lồ cuối cùng. Lý do: batch nhiều
    dòng nặng (7-16 phút cho 10 dòng thật) dễ vượt idle-read-timeout của gateway/proxy phía
    trước Render (Cloudflare, ~100s không có traffic mới) — "Failed to fetch" xuất hiện đúng lúc
    ~1 phút, xác nhận thật qua test trực tiếp (xem docs.md). Route /batch-csv GỐC GIỮ NGUYÊN
    KHÔNG ĐỔI (vẫn cần cho nơi nào cần 1 response JSON chuẩn, vd script chấm điểm tự động gọi
    trực tiếp) — đây là route THÊM MỚI, FE dùng route này.

    Response: Content-Type text/x-ndjson — mỗi dòng (kết thúc bằng \\n) là 1 JSON object:
      - {"row_index":0,"input_ref":...,"status":"OK","result":{...}} — 1 dòng/design, theo
        đúng thứ tự HOÀN THÀNH (không nhất thiết theo row_index nếu max_concurrency > 1).
      - Dòng CUỐI CÙNG: {"summary": {"total":...,"safe_count":...,...,"csv_export":"..."}}
    """
    try:
        raw_bytes = await file.read()
        filename = (file.filename or "").lower()
        if filename.endswith(".xlsx"):
            rows = parse_xlsx_rows(raw_bytes)
        else:
            rows = parse_csv_rows(decode_csv_bytes(raw_bytes))
        if not rows:
            raise HTTPException(status_code=422, detail="File rỗng hoặc không đọc được dòng nào (kiểm tra đúng định dạng .csv/.xlsx và có header đúng cột).")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return StreamingResponse(
        _batch_ndjson_generator(rows, platform, target_country or "US", max_concurrency),
        media_type="application/x-ndjson",
    )


@router.post("/batch-json-stream")
async def compliance_batch_json_stream(req: ComplianceBatchRequest):
    """(2026-08-22, MỚI) Bản JSON body của /batch-csv-stream — cùng cơ chế csv_content/
    batch_file_url như /batch-json, chỉ khác trả về NDJSON streaming thay vì 1 JSON cuối cùng.
    Xem docstring /batch-csv-stream để biết lý do + shape response."""
    try:
        if req.batch_file_url:
            raw_bytes = await normalize_url_to_bytes(req.batch_file_url)
            rows = parse_batch_bytes(raw_bytes)
        elif req.csv_content:
            rows = parse_csv_rows(req.csv_content)
        else:
            raise HTTPException(status_code=422, detail="Cần đúng 1 trong 2: csv_content hoặc batch_file_url")
        if not rows:
            raise HTTPException(status_code=422, detail="Nguồn batch rỗng hoặc không đọc được dòng nào (kiểm tra đúng định dạng/quyền truy cập link).")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return StreamingResponse(
        _batch_ndjson_generator(rows, req.platform, req.target_country or "US", req.max_concurrency),
        media_type="application/x-ndjson",
    )
