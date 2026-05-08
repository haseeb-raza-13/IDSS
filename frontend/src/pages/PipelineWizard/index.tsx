import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, ChevronRight } from "lucide-react";
import { startPipeline, type PipelineMeta } from "@/api/genomics";
import { useAppStore } from "@/store/appStore";
import Step1Source from "./Step1Source";
import Step2Config from "./Step2Config";
import Step3Meta from "./Step3Meta";
import Step4Monitor from "./Step4Monitor";

const STEPS = ["Source Files", "Configuration", "Run Details", "Monitor"];

export default function PipelineWizard() {
  const [step, setStep] = useState(0);
  const [files, setFiles] = useState<File[]>([]);
  const [config, setConfig] = useState<Partial<PipelineMeta>>({
    identity_threshold: 0.8,
    tree_method: "nj",
    kmer_size: 21,
  });
  const [meta, setMeta] = useState<Partial<PipelineMeta>>({
    source_type: "unknown",
  });
  const [jobId, setJobId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const setActiveJobId = useAppStore((s) => s.setActiveJobId);

  async function handleSubmit() {
    setSubmitting(true);
    setSubmitError("");
    try {
      const full: PipelineMeta = {
        researcher: meta.researcher ?? "",
        study_name: meta.study_name ?? "",
        pathogen: meta.pathogen ?? "",
        ...(meta as PipelineMeta),
        ...(config as PipelineMeta),
      };
      const { job_id } = await startPipeline(files, full);
      setJobId(job_id);
      setActiveJobId(job_id);
      setStep(3);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to start pipeline";
      setSubmitError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-xl font-semibold text-gray-900">New Pipeline Run</h1>

      {/* Step indicator */}
      <div className="flex items-center gap-0">
        {STEPS.map((label, i) => (
          <div key={i} className="flex items-center">
            <div
              className={`flex items-center justify-center w-7 h-7 rounded-full text-xs font-medium ${
                i < step
                  ? "bg-blue-600 text-white"
                  : i === step
                  ? "bg-blue-100 text-blue-700 ring-2 ring-blue-600"
                  : "bg-gray-100 text-gray-500"
              }`}
            >
              {i < step ? <Check size={13} /> : i + 1}
            </div>
            <span className={`ml-2 text-xs ${i === step ? "font-medium text-gray-900" : "text-gray-500"}`}>
              {label}
            </span>
            {i < STEPS.length - 1 && <ChevronRight size={14} className="mx-3 text-gray-300" />}
          </div>
        ))}
      </div>

      {/* Step content */}
      <div className="bg-white rounded-xl border p-6">
        {step === 0 && (
          <Step1Source
            files={files}
            onFilesChange={setFiles}
            onNext={() => setStep(1)}
          />
        )}
        {step === 1 && (
          <Step2Config
            config={config}
            onChange={setConfig}
            onBack={() => setStep(0)}
            onNext={() => setStep(2)}
          />
        )}
        {step === 2 && (
          <Step3Meta
            meta={meta}
            onChange={setMeta}
            onBack={() => setStep(1)}
            onSubmit={handleSubmit}
            submitting={submitting}
            error={submitError}
          />
        )}
        {step === 3 && jobId && (
          <Step4Monitor jobId={jobId} />
        )}
      </div>
    </div>
  );
}
