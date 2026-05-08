import { Link } from "react-router-dom";
import { Check, X, Loader2, Clock } from "lucide-react";
import { useJobStatus } from "@/hooks/useJobStatus";
import type { JobStep } from "@/api/jobs";

const STEP_LABELS: Record<string, string> = {
  fetch_local: "Cataloging uploaded files",
  qc: "Quality control (GC%, N50, contigs)",
  snp: "SNP detection",
  amr: "AMR gene detection",
  phylo: "Phylogenetic tree construction",
  report: "Generating Word report",
  db_store: "Storing results in database",
};

function StepRow({ step }: { step: JobStep }) {
  const label = STEP_LABELS[step.name] ?? step.name;
  return (
    <div className="flex items-center gap-3 py-2">
      <div className="w-5 h-5 flex items-center justify-center shrink-0">
        {step.status === "done" && <Check size={16} className="text-green-600" />}
        {step.status === "failed" && <X size={16} className="text-red-500" />}
        {step.status === "running" && <Loader2 size={16} className="text-blue-500 animate-spin" />}
        {step.status === "pending" && <Clock size={16} className="text-gray-300" />}
      </div>
      <span
        className={`text-sm ${
          step.status === "done"
            ? "text-gray-700"
            : step.status === "running"
            ? "text-blue-700 font-medium"
            : step.status === "failed"
            ? "text-red-600"
            : "text-gray-400"
        }`}
      >
        {label}
      </span>
      {step.error && <span className="text-xs text-red-500 ml-2">{step.error}</span>}
    </div>
  );
}

interface Props {
  jobId: string;
}

export default function Step4Monitor({ jobId }: Props) {
  const { data: job, isLoading } = useJobStatus(jobId);

  if (isLoading) {
    return <div className="py-8 text-center text-sm text-gray-500">Connecting…</div>;
  }

  if (!job) {
    return <div className="py-8 text-center text-sm text-red-500">Could not load job status.</div>;
  }

  const isDone = job.status === "done";
  const isFailed = job.status === "failed";

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-medium text-gray-900 mb-1">
          {isDone ? "Pipeline Complete" : isFailed ? "Pipeline Failed" : "Pipeline Running…"}
        </h2>
        <p className="text-xs text-gray-400">Job ID: {jobId}</p>
      </div>

      <div className="divide-y divide-gray-100">
        {job.steps.map((step) => (
          <StepRow key={step.name} step={step} />
        ))}
        {job.steps.length === 0 && (
          <div className="py-3 text-sm text-gray-400 flex items-center gap-2">
            <Loader2 size={14} className="animate-spin" />
            Waiting for worker…
          </div>
        )}
      </div>

      {job.error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
          {job.error}
        </div>
      )}

      {isDone && job.run_id && (
        <div className="flex gap-3">
          <Link
            to={`/results/${job.run_id}`}
            className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700"
          >
            View Results →
          </Link>
          <Link
            to="/pipeline"
            className="border px-5 py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-50"
            onClick={() => window.location.reload()}
          >
            New Run
          </Link>
        </div>
      )}
    </div>
  );
}
