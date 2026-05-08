import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMLModels } from "@/hooks/useMLModels";
import { trainModel } from "@/api/ml";
import { useAppStore } from "@/store/appStore";
import { JobStatusBadge } from "@/components/common/JobStatusBadge";
import { useJobStatus } from "@/hooks/useJobStatus";
import { format } from "date-fns";

export default function MLStudio() {
  const { data: models, isLoading } = useMLModels();
  const [modelType, setModelType] = useState<"random_forest" | "xgboost" | "ann">("random_forest");
  const [targetVariable, setTargetVariable] = useState("mdr_class");
  const [featureSet, setFeatureSet] = useState<"genomic" | "phenotypic" | "combined">("genomic");
  const [trainJobId, setTrainJobId] = useState<string | null>(null);
  const setActiveJobId = useAppStore((s) => s.setActiveJobId);
  const queryClient = useQueryClient();

  const { data: trainJob } = useJobStatus(trainJobId);

  const trainMutation = useMutation({
    mutationFn: () => trainModel({ model_type: modelType, target_variable: targetVariable, feature_set: featureSet }),
    onSuccess: (data) => {
      setTrainJobId(data.job_id);
      setActiveJobId(data.job_id);
    },
  });

  // Refresh models when training completes
  if (trainJob?.status === "done" && trainJobId) {
    queryClient.invalidateQueries({ queryKey: ["ml-models"] });
  }

  return (
    <div className="max-w-5xl space-y-6">
      <h1 className="text-xl font-semibold text-gray-900">ML Studio</h1>

      <div className="grid grid-cols-5 gap-6">
        {/* Train form */}
        <div className="col-span-2 bg-white rounded-xl border p-5 space-y-4 h-fit">
          <h2 className="text-sm font-semibold text-gray-700">Train New Model</h2>

          <div>
            <label className="text-xs font-medium text-gray-600 block mb-1">Model Type</label>
            <select
              value={modelType}
              onChange={(e) => setModelType(e.target.value as typeof modelType)}
              className="w-full border rounded px-2 py-1.5 text-sm"
            >
              <option value="random_forest">Random Forest</option>
              <option value="xgboost">XGBoost</option>
              <option value="ann">Neural Network (ANN)</option>
            </select>
          </div>

          <div>
            <label className="text-xs font-medium text-gray-600 block mb-1">Target Variable</label>
            <select
              value={targetVariable}
              onChange={(e) => setTargetVariable(e.target.value)}
              className="w-full border rounded px-2 py-1.5 text-sm"
            >
              <option value="mdr_class">MDR Class (MDR/XDR/PDR)</option>
              <option value="outbreak_risk">Outbreak Risk</option>
              <option value="amr_phenotype_ampicillin">Resistance: Ampicillin</option>
              <option value="amr_phenotype_ciprofloxacin">Resistance: Ciprofloxacin</option>
              <option value="amr_phenotype_meropenem">Resistance: Meropenem</option>
            </select>
          </div>

          <div>
            <label className="text-xs font-medium text-gray-600 block mb-1">Feature Set</label>
            <select
              value={featureSet}
              onChange={(e) => setFeatureSet(e.target.value as typeof featureSet)}
              className="w-full border rounded px-2 py-1.5 text-sm"
            >
              <option value="genomic">Genomic only</option>
              <option value="phenotypic">Phenotypic only</option>
              <option value="combined">Combined</option>
            </select>
          </div>

          <button
            onClick={() => trainMutation.mutate()}
            disabled={trainMutation.isPending || trainJob?.status === "running"}
            className="w-full bg-blue-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            {trainMutation.isPending || trainJob?.status === "running" ? "Training…" : "Start Training"}
          </button>

          {trainJobId && trainJob && (
            <div className="mt-2 flex items-center gap-2 text-xs text-gray-500">
              <JobStatusBadge status={trainJob.status} />
              <span>Job {trainJobId.slice(0, 8)}</span>
            </div>
          )}
        </div>

        {/* Model registry */}
        <div className="col-span-3">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">Model Registry</h2>
          {isLoading && <div className="text-sm text-gray-400">Loading models…</div>}
          <div className="space-y-2">
            {models?.length === 0 && (
              <div className="text-sm text-gray-400 py-4 text-center">No models trained yet.</div>
            )}
            {models?.map((m: Record<string, unknown>) => (
              <div key={m.model_id as string} className="bg-white border rounded-xl p-4">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-900">{m.target_variable as string}</p>
                    <p className="text-xs text-gray-500">{m.model_type as string} · {m.feature_set as string} features</p>
                  </div>
                  <div className="text-right text-xs text-gray-500">
                    {m.created_at && format(new Date(m.created_at as string), "MMM d, yyyy")}
                  </div>
                </div>
                <div className="flex gap-4 mt-2">
                  {m.accuracy != null && (
                    <Metric label="Accuracy" value={`${((m.accuracy as number) * 100).toFixed(1)}%`} />
                  )}
                  {m.auc_roc != null && (
                    <Metric label="AUC-ROC" value={(m.auc_roc as number).toFixed(3)} />
                  )}
                  {m.f1_score != null && (
                    <Metric label="F1" value={(m.f1_score as number).toFixed(3)} />
                  )}
                  <Metric label="Samples" value={String(m.sample_count)} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-gray-400">{label}</p>
      <p className="text-sm font-semibold text-gray-800">{value}</p>
    </div>
  );
}
