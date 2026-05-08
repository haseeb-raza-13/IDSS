import { apiClient } from "./client";

export async function listRuns(params?: { page?: number; page_size?: number; pathogen?: string; region?: string }) {
  const res = await apiClient.get("/api/history/runs", { params });
  return res.data;
}

export async function getRunDetail(runId: string) {
  const res = await apiClient.get(`/api/history/runs/${runId}`);
  return res.data;
}

export async function getAMRTrend(params?: { gene?: string; region?: string; days?: number }) {
  const res = await apiClient.get("/api/history/amr-trend", { params });
  return res.data;
}

export async function getResistanceRates(params?: { antibiotic?: string; region?: string; pathogen?: string }) {
  const res = await apiClient.get("/api/history/resistance-rate", { params });
  return res.data;
}

export async function getOutbreakCheck(params?: { days?: number; min_samples?: number }) {
  const res = await apiClient.get("/api/history/outbreak-check", { params });
  return res.data;
}
