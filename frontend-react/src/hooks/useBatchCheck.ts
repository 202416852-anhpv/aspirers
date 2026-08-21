// hooks/useBatchCheck.ts — useMutation cho batch. Gộp 2 cách gửi (upload file vs batch_file_url)
// thành 1 hook, tương tự useCheckDesign.
import { useMutation } from "@tanstack/react-query";
import { runBatchByFile, runBatchByUrl } from "../api/client";
import type { BatchReport } from "../api/types";

export interface BatchCheckInput {
  file?: File; // .csv hoặc .xlsx
  batch_file_url?: string; // Google Sheets/Drive/Dropbox/URL trực tiếp
  platform?: string;
  target_country: string;
  max_concurrency?: number;
}

export function useBatchCheck() {
  return useMutation<BatchReport, Error, BatchCheckInput>({
    mutationFn: async (input) => {
      if (input.file) {
        return runBatchByFile({
          file: input.file,
          platform: input.platform,
          target_country: input.target_country,
          max_concurrency: input.max_concurrency,
        });
      }
      if (input.batch_file_url) {
        return runBatchByUrl({
          batch_file_url: input.batch_file_url,
          platform: input.platform,
          target_country: input.target_country,
          max_concurrency: input.max_concurrency,
        });
      }
      throw new Error("Cần đúng 1 trong 2: file hoặc batch_file_url");
    },
  });
}
