import { useQuery } from "@tanstack/react-query";
import { listRuns, getRunDetail } from "@/api/history";

export function useRunHistory(params?: { page?: number; page_size?: number; pathogen?: string; region?: string }) {
  return useQuery({
    queryKey: ["runs", params],
    queryFn: () => listRuns(params),
  });
}

export function useRunDetail(runId: string | null) {
  return useQuery({
    queryKey: ["run", runId],
    queryFn: () => getRunDetail(runId!),
    enabled: !!runId,
  });
}
