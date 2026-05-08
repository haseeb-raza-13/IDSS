import { useQuery } from "@tanstack/react-query";
import { listAlerts } from "@/api/alerts";

export function useAlerts(params?: { level?: string; region?: string; days?: number; page?: number }) {
  return useQuery({
    queryKey: ["alerts", params],
    queryFn: () => listAlerts(params),
    staleTime: 60_000,
  });
}
