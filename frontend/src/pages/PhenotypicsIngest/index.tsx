import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { FileDropzone } from "@/components/common/FileDropzone";
import { JobStatusBadge } from "@/components/common/JobStatusBadge";
import { useJobStatus } from "@/hooks/useJobStatus";
import { apiClient } from "@/api/client";

const CSV_ACCEPT = {
  "text/csv": [".csv"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
};

export default function PhenotypicsIngest() {
  const [files, setFiles] = useState<File[]>([]);
  const [region, setRegion] = useState("");
  const [facility, setFacility] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const { data: job } = useJobStatus(jobId);

  const ingestMutation = useMutation({
    mutationFn: async () => {
      const form = new FormData();
      form.append("file", files[0]);
      if (region) form.append("region", region);
      if (facility) form.append("facility", facility);
      const res = await apiClient.post("/api/phenotypics/ingest", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      return res.data;
    },
    onSuccess: (data) => setJobId(data.job_id),
  });

  return (
    <div className="max-w-2xl space-y-5">
      <h1 className="text-xl font-semibold text-gray-900">Phenotypics — AST Ingest</h1>
      <p className="text-sm text-gray-500">
        Upload an AST (Antimicrobial Susceptibility Testing) CSV or Excel file from your LIMS.
        Required columns: sample_id, pathogen_name, antibiotic, interpretation (S/I/R).
      </p>

      <div className="bg-white rounded-xl border p-5 space-y-4">
        <FileDropzone
          accept={CSV_ACCEPT}
          multiple={false}
          files={files}
          onFilesChange={setFiles}
          label="Drop CSV/Excel AST file here"
        />

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs font-medium text-gray-600 block mb-1">Region</label>
            <input
              type="text"
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              className="w-full border rounded px-2 py-1.5 text-sm"
              placeholder="Punjab"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 block mb-1">Facility</label>
            <input
              type="text"
              value={facility}
              onChange={(e) => setFacility(e.target.value)}
              className="w-full border rounded px-2 py-1.5 text-sm"
              placeholder="UAF Teaching Hospital"
            />
          </div>
        </div>

        <button
          onClick={() => ingestMutation.mutate()}
          disabled={files.length === 0 || ingestMutation.isPending}
          className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          {ingestMutation.isPending ? "Uploading…" : "Ingest AST Data"}
        </button>

        {jobId && job && (
          <div className="flex items-center gap-2 text-sm">
            <JobStatusBadge status={job.status} />
            {job.status === "done" && (
              <span className="text-green-700">
                Ingested successfully. MDR classifications computed.
              </span>
            )}
            {job.status === "failed" && (
              <span className="text-red-600">{job.error}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
