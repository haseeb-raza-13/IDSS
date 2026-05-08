import { apiClient } from "./client";

export interface PipelineMeta {
  researcher: string;
  study_name: string;
  pathogen: string;
  source_type?: "human" | "animal" | "environment" | "unknown";
  country?: string;
  region?: string;
  facility?: string;
  notes?: string;
  reference_accession?: string;
  identity_threshold?: number;
  tree_method?: "nj" | "upgma";
  kmer_size?: number;
}

export async function startPipeline(files: File[], meta: PipelineMeta): Promise<{ job_id: string }> {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  form.append("metadata", JSON.stringify(meta));
  const res = await apiClient.post("/api/genomics/pipeline/start", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
}

export async function fetchFromNCBI(params: {
  accessions?: string[];
  search_term?: string;
  max_records?: number;
}): Promise<{ job_id: string }> {
  const res = await apiClient.post("/api/genomics/sequences/fetch-ncbi", params);
  return res.data;
}
