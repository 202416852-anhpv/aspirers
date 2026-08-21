"""
compliance_checker/ingestion/ — chuẩn hoá MỌI loại input (upload/link/CSV/XLSX batch) về
1 shape chung mà phần còn lại của hệ thống tiêu thụ được: file_loader.py (hội tụ PNG/JPG/
PSD/PDF về 1 ảnh PIL, entrypoint chính), pdf_processor.py (nhánh PDF riêng), link_normalizer.py
(URL -> bytes thô), csv_batch.py (parser batch, row-level fault isolation).
"""
