// hooks/useCheckDesign.ts — useMutation cho 1 lượt check-1-design. Gộp 2 cách gửi (file vs url)
// thành 1 hook duy nhất vì UI (Composer) chỉ cần biết "gửi đi" chứ không cần tách 2 mutation.
import { useMutation } from "@tanstack/react-query";
import { checkDesignByFile, checkDesignByUrl } from "../api/client";
import type { DesignComplianceResult } from "../api/types";

export interface CheckDesignInput {
  file?: File;
  url?: string;
  platform?: string;
  target_country: string;
  niche_hint?: string;
}

export function useCheckDesign() {
  return useMutation<DesignComplianceResult, Error, CheckDesignInput>({
    mutationFn: async (input) => {
      if (input.file) {
        return checkDesignByFile({
          file: input.file,
          platform: input.platform,
          target_country: input.target_country,
          niche_hint: input.niche_hint,
        });
      }
      if (input.url) {
        return checkDesignByUrl({
          url: input.url,
          platform: input.platform,
          target_country: input.target_country,
          niche_hint: input.niche_hint,
        });
      }
      throw new Error("Cần đúng 1 trong 2: file hoặc url");
    },
  });
}
