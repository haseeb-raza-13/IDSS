import { apiClient } from "./client";

export async function listModels() {
  const res = await apiClient.get("/api/ml/models");
  return res.data;
}

export async function trainModel(params: {
  model_type: "random_forest" | "xgboost" | "ann";
  target_variable: string;
  feature_set: "genomic" | "phenotypic" | "combined";
  pathogen?: string;
  region?: string;
  k_folds?: number;
}): Promise<{ job_id: string }> {
  const res = await apiClient.post("/api/ml/train", params);
  return res.data;
}

export async function predictWithModel(modelId: string, runId: string) {
  const res = await apiClient.post("/api/ml/predict", null, {
    params: { model_id: modelId, run_id: runId },
  });
  return res.data;
}
