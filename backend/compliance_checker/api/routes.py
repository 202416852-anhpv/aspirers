"""
compliance_checker/api/routes.py — 4 route BUP-02 (upload file / import link / batch CSV
/ batch JSON), tách khỏi backend/main.py (main.py giờ chỉ include_router(router) ở đây,
không tự định nghĩa handler nữa). Toàn bộ THÂN HÀM giữ NGUYÊN 100% so với trước khi tách
file — chỉ đổi @app.xxx("/api/compliance/...") -> @router.xxx("/...") nhờ APIRouter(prefix=
"/api/compliance"), 2 cách viết cho ra ĐÚNG cùng 1 URL cuối cùng, KHÔNG đổi hành vi API.

Xem docs.md mục 1-4 để biết route nào dùng khi nào.
"""

import os
import tempfile
import uuid

from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from compliance_checker.schemas import ComplianceCheckRequest, ComplianceBatchRequest, DesignComplianceResult, BatchReport
from compliance_checker.orchestrator import process_one_design, process_batch
from compliance_checker.ingestion.csv_batch import parse_csv_rows, parse_xlsx_rows, batch_row_to_csv_dict, write_batch_csv, decode_csv_bytes

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
    max_concurrency: int = Form(default=5),
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
    """Bản JSON body (thay vì multipart) của batch-csv — cho FE/giám khảo tự paste nội dung
    CSV dạng text thẳng vào JSON, không cần dựng multipart form."""
    try:
        rows = parse_csv_rows(req.csv_content)
        if not rows:
            raise HTTPException(status_code=422, detail="csv_content rỗng hoặc không đọc được dòng nào.")
        return await process_batch(
            rows, platform=req.platform, target_country=req.target_country or "US", max_concurrency=req.max_concurrency
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
