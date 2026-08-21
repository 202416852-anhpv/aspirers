// components/result/ImageOverlay.tsx — THAY THẾ hoàn toàn renderDetectedFaces() +
// renderPositioningOverlay() của bản vanilla JS cũ (2 hàm đó đọc field ĐÃ BỊ XOÁ khỏi backend:
// face_base64 và text_regions — xem báo cáo UX). Nguồn dữ liệu DUY NHẤT giờ là flagged_regions
// (Python xây dựng thật, KHÔNG phải LLM tự đoán toạ độ — xem schemas.py::FlaggedRegion).
//
// previewUrl: ảnh gốc lấy từ CLIENT (object URL của file vừa chọn, hoặc chính link đã dán) —
// backend KHÔNG trả ảnh về, tránh phình payload (giữ đúng tư duy bản cũ). Không có previewUrl
// (PDF/PSD không preview được bằng <img>, hoặc batch row dùng file_path không phải URL) ->
// không render gì, verdict/evidence vẫn hiện đầy đủ ở các component khác.

import { useState } from "react";
import type { FlaggedRegion } from "../../api/types";

export interface ImageOverlayProps {
  previewUrl: string | null;
  flaggedRegions: FlaggedRegion[];
}

export function ImageOverlay({ previewUrl, flaggedRegions }: ImageOverlayProps) {
  const [imgFailed, setImgFailed] = useState(false);

  if (!previewUrl || imgFailed || flaggedRegions.length === 0) return null;

  const pct = (v: number) => `${(v * 100).toFixed(2)}%`;

  return (
    <div>
      <div className="section-title">Vùng đáng nghi (toạ độ thật)</div>
      <div className="image-overlay-wrap">
        <img src={previewUrl} className="preview-img" onError={() => setImgFailed(true)} alt="Design preview" />
        {flaggedRegions.map((region, i) => (
          <div
            key={i}
            className={`bbox-box bbox-${region.kind}`}
            style={{
              left: pct(region.bbox_norm[0]),
              top: pct(region.bbox_norm[1]),
              width: pct(region.bbox_norm[2] - region.bbox_norm[0]),
              height: pct(region.bbox_norm[3] - region.bbox_norm[1]),
            }}
            title={region.detail}
          >
            <span className="bbox-label">{region.label}</span>
          </div>
        ))}
      </div>
      <p className="empty-note">
        Khung xanh dương: text nghi trademark (database + Agent 2 tự đánh giá). Khung tím: khuôn mặt Agent 2 nhận diện được. Bấm/hover để xem lý do.
      </p>
    </div>
  );
}
