import type { PipelineMeta } from "@/api/genomics";

interface Props {
  config: Partial<PipelineMeta>;
  onChange: (c: Partial<PipelineMeta>) => void;
  onBack: () => void;
  onNext: () => void;
}

export default function Step2Config({ config, onChange, onBack, onNext }: Props) {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-base font-medium text-gray-900 mb-1">Analysis Configuration</h2>
        <p className="text-sm text-gray-500">Fine-tune the pipeline parameters.</p>
      </div>

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Reference Genome Accession <span className="text-gray-400 font-normal">(optional)</span>
          </label>
          <input
            type="text"
            placeholder="e.g. NC_000913.3"
            value={config.reference_accession ?? ""}
            onChange={(e) => onChange({ ...config, reference_accession: e.target.value || undefined })}
            className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <p className="text-xs text-gray-400 mt-1">Leave blank to skip SNP detection</p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Identity Threshold: <span className="text-blue-600">{config.identity_threshold}</span>
          </label>
          <input
            type="range"
            min={0.7}
            max={1.0}
            step={0.01}
            value={config.identity_threshold ?? 0.8}
            onChange={(e) => onChange({ ...config, identity_threshold: parseFloat(e.target.value) })}
            className="w-full"
          />
          <div className="flex justify-between text-xs text-gray-400 mt-0.5">
            <span>0.70</span><span>1.00</span>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Tree Method</label>
          <div className="flex gap-3">
            {["nj", "upgma"].map((m) => (
              <label key={m} className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="radio"
                  name="tree_method"
                  value={m}
                  checked={config.tree_method === m}
                  onChange={() => onChange({ ...config, tree_method: m as "nj" | "upgma" })}
                />
                <span className="text-gray-700">{m.toUpperCase()}</span>
              </label>
            ))}
          </div>
        </div>
      </div>

      <div className="flex justify-between">
        <button onClick={onBack} className="text-sm text-gray-600 hover:text-gray-900">← Back</button>
        <button
          onClick={onNext}
          className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700"
        >
          Next →
        </button>
      </div>
    </div>
  );
}
