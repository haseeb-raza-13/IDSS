import { apiClient } from "./client";

export interface JobStep {
  name: string;
  status: "pending" | "running" | "done" | "failed";
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}

export interface JobStatus {
  job_id: string;
  type: string;
  status: "pending" | "running" | "done" | "failed";
  steps: JobStep[];
  run_id: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const res = await apiClient.get(`/api/jobs/${jobId}`);
  return res.data;
}

export async function cancelJob(jobId: string): Promise<void> {
  await apiClient.delete(`/api/jobs/${jobId}`);
}
