// components/composer/SettingsBar.tsx — thay thế settings MODAL của bản cũ (từng có bug kẹt
// UI, xem báo cáo UX). platform/target_country là field CHO MỖI REQUEST (ComplianceCheckRequest
// / ComplianceBatchRequest đều có) nên hiện THƯỜNG TRỰC ở đây, không giấu trong overlay riêng.

export interface SettingsValue {
  backendUrl: string;
  platform: string; // "" = không chọn
  targetCountry: string;
}

export interface SettingsBarProps {
  value: SettingsValue;
  onChange: (value: SettingsValue) => void;
  onCheckHealth: () => void;
}

const PLATFORMS = [
  { value: "", label: "(không chọn)" },
  { value: "etsy", label: "Etsy" },
  { value: "amazon", label: "Amazon Merch" },
  { value: "tiktok", label: "TikTok Shop" },
  { value: "shopify", label: "Shopify" },
];

export function SettingsBar({ value, onChange, onCheckHealth }: SettingsBarProps) {
  return (
    <div className="settings-bar">
      <select
        value={value.platform}
        onChange={(e) => onChange({ ...value, platform: e.target.value })}
        title="Platform bán — dùng để đánh giá riêng 'platform bạn chọn có phù hợp không' (selected_platform_suitable)"
      >
        {PLATFORMS.map((p) => (
          <option key={p.value} value={p.value}>
            {p.label}
          </option>
        ))}
      </select>

      <input
        type="text"
        value={value.targetCountry}
        onChange={(e) => onChange({ ...value, targetCountry: e.target.value })}
        placeholder="Target country (vd: US)"
        title="target_country — quốc gia áp dụng policy/trend"
      />

      <input
        type="text"
        value={value.backendUrl}
        onChange={(e) => onChange({ ...value, backendUrl: e.target.value })}
        placeholder="Backend URL"
        title="Backend URL — mặc định http://localhost:8000"
      />

      <button type="button" onClick={onCheckHealth}>
        Kiểm tra kết nối
      </button>
    </div>
  );
}
