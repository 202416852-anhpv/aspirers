"""
compliance_checker/engine/ — các module xử lý nội bộ mà orchestrator.py điều phối:
agents.py (Agent 1-4 + Nhóm C, gọi LLM), black_box.py (threshold + aggregation, thuần
Python), opencv_modules.py (OpenCV cổ điển), trademark_resolver.py (tra cứu trademark
2 lớp). Không có route/entrypoint nào ở đây — chỉ orchestrator.py mới gọi trực tiếp.
"""
