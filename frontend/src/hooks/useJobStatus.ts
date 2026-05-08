import { useQuery } from "@tanstack/react-query";
import { getJobStatus, type JobStatus } from "@/api/jobs";

const TERMINAL_STATUSES = new Set(["done", "failed"]);

export function useJobStatus(jobId: string | null) {
  return useQuery<JobStatus>({
    queryKey: ["job", jobId],
    queryFn: () => getJobStatus(jobId!),
    enabled: !!jobId,
    staleTime: 0,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return 3000;
      return TERMINAL_STATUSES.has(data.status) ? false : 3000;
    },
  });
}
