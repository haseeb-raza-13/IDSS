import type { PipelineMeta } from "@/api/genomics";

interface Props {
  meta: Partial<PipelineMeta>;
  onChange: (m: Partial<PipelineMeta>) => void;
  onBack: () => void;
  onSubmit: () => void;
  submitting: boolean;
  error: string;
}

export default function Step3Meta({ meta, onChange, onBack, onSubmit, submitting, error }: Props) {
  function field(key: keyof PipelineMeta, label: string, required = false, placeholder = "") {
    return (
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {label} {required && <span className="text-red-500">*</span>}
        </label>
        <input
          type="text"
          placeholder={placeholder}
          value={(meta[key] as string) ?? ""}
          onChange={(e) => onChange({ ...meta, [key]: e.target.value })}
          className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          required={required}
        />
      </div>
    );
  }

  const canSubmit =
    !submitting &&
    meta.researcher &&
    meta.study_name &&
    meta.pathogen;

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-base font-medium text-gray-900 mb-1">Run Details</h2>
        <p className="text-sm text-gray-500">This metadata is stored with the run for tracking and reporting.</p>
      </div>

      <div className="space-y-3">
        {field("researcher", "Researcher Name", true, "Dr. Jane Smith")}
        {field("study_name", "Study Name", true, "AMR Surveillance Q2 2026")}
        {field("pathogen", "Pathogen", true, "E. coli")}

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Source Type</label>
          <select
            value={meta.source_type ?? "unknown"}
            onChange={(e) => onChange({ ...meta, source_type: e.target.value as PipelineMeta["source_type"] })}
            className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {["human", "animal", "environment", "unknown"].map((t) => (
              <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
            ))}
          </select>
        </div>

        {field("region", "Region / Province")}
        {field("facility", "Facility / Hospital")}
        {field("country", "Country")}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex justify-between">
        <button onClick={onBack} className="text-sm text-gray-600 hover:text-gray-900">← Back</button>
        <button
          onClick={onSubmit}
          disabled={!canSubmit}
          className="bg-blue-600 text-white px-6 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          {submitting ? "Starting…" : "Start Pipeline"}
        </button>
      </div>
    </div>
  );
}
