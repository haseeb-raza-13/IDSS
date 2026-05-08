import { apiClient } from "./client";

export async function listAlerts(params?: { level?: string; region?: string; days?: number; page?: number; page_size?: number }) {
  const res = await apiClient.get("/api/alerts/", { params });
  return res.data;
}

export async function scoreAlert(runId: string): Promise<{ job_id: string }> {
  const res = await apiClient.post("/api/alerts/score", { run_id: runId });
  return res.data;
}
