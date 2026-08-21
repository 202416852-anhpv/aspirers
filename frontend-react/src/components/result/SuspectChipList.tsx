// components/result/SuspectChipList.tsx — chip tên logo/nhân vật/celeb nghi ngờ, kèm badge
// ✅/❌ từ verifications (Agent 2 xác nhận CÓ/KHÔNG). TUYỆT ĐỐI không hiện số/% (đúng quy tắc
// đã chốt) — chỉ ✅ (present=true) / ❌ (present=false) / không badge (present=undefined, vd
// Agent 2 lỗi hoặc tên không khớp — coi là trung lập, không kết luận gì).

import type { VerificationItem } from "../../api/types";

export interface SuspectChipListProps {
  items: { name: string; confidence: string }[]; // đã chuẩn hoá brand_name/name -> name ở ResultCard
  category: "logo" | "character" | "celebrity";
  verifications: VerificationItem[];
}

function buildVerificationMap(verifications: VerificationItem[]): Map<string, boolean> {
  const map = new Map<string, boolean>();
  for (const v of verifications) {
    map.set(`${v.category}:${v.name.trim().toLowerCase()}`, v.present);
  }
  return map;
}

export function SuspectChipList({ items, category, verifications }: SuspectChipListProps) {
  if (items.length === 0) return <span className="empty-note">Không phát hiện</span>;

  const verificationMap = buildVerificationMap(verifications);

  return (
    <div className="chip-list">
      {items.map((item, i) => {
        const present = verificationMap.get(`${category}:${item.name.trim().toLowerCase()}`);
        return (
          <span key={i} className="chip">
            {item.name}
            {present === true && (
              <span className="verify-badge verify-yes" title="Agent 2 xác nhận có trong ảnh">
                {" "}
                ✅
              </span>
            )}
            {present === false && (
              <span className="verify-badge verify-no" title="Agent 2 kiểm tra lại: không thấy trong ảnh">
                {" "}
                ❌
              </span>
            )}
          </span>
        );
      })}
    </div>
  );
}
