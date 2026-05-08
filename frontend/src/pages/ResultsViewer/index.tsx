import { useParams } from "react-router-dom";
import { useRunDetail } from "@/hooks/useRunHistory";
import { AlertLevelBadge } from "@/components/common/AlertLevelBadge";

export default function ResultsViewer() {
  const { runId } = useParams<{ runId: string }>();
  const { data: run, isLoading, error } = useRunDetail(runId ?? null);

  if (isLoading) return <div className="text-sm text-gray-400 p-6">Loading results…</div>;
  if (error || !run) return <div className="text-sm text-red-500 p-6">Run not found.</div>;

  return (
    <div className="max-w-5xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">{run.pathogen}</h1>
          <p className="text-sm text-gray-500">{run.study_name} · {run.researcher}</p>
        </div>
        {run.alert?.alert_level && (
          <AlertLevelBadge level={run.alert.alert_level} showScore={run.alert.alert_score} />
        )}
      </div>

      {/* QC Results */}
      {run.qc_results?.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-gray-700 mb-2">QC Results</h2>
          <div className="bg-white rounded-xl border overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  {["Sample", "Contigs", "Total Length", "GC%", "N%", "N50", "Pass"].map((h) => (
                    <th key={h} className="px-4 py-2 text-left text-xs font-medium text-gray-500">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {run.qc_results.map((q: Record<string, unknown>, i: number) => (
                  <tr key={i}>
                    <td className="px-4 py-2 font-mono text-xs text-gray-700">{q.sample_id as string}</td>
                    <td className="px-4 py-2">{q.contig_count as number}</td>
                    <td className="px-4 py-2">{((q.total_length as number) / 1e6).toFixed(2)} Mb</td>
                    <td className="px-4 py-2">{(q.gc_pct as number)?.toFixed(1)}%</td>
                    <td className="px-4 py-2">{(q.n_content_pct as number)?.toFixed(2)}%</td>
                    <td className="px-4 py-2">{q.n50 as number}</td>
                    <td className="px-4 py-2">
                      <span className={`text-xs font-medium ${q.qc_pass ? "text-green-600" : "text-red-500"}`}>
                        {q.qc_pass ? "PASS" : "FLAG"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* AMR Hits */}
      {run.amr_hits?.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-gray-700 mb-2">AMR Gene Hits</h2>
          <div className="bg-white rounded-xl border overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  {["Sample", "Gene", "Drug Class", "Identity"].map((h) => (
                    <th key={h} className="px-4 py-2 text-left text-xs font-medium text-gray-500">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {run.amr_hits.map((h: Record<string, unknown>, i: number) => (
                  <tr key={i}>
                    <td className="px-4 py-2 font-mono text-xs text-gray-600">{h.sid as string}</td>
                    <td className="px-4 py-2 font-medium text-gray-900">{h.gene as string}</td>
                    <td className="px-4 py-2 text-gray-600">{h.drug_class as string}</td>
                    <td className="px-4 py-2">
                      <span className={`text-xs font-mono ${(h.identity as number) >= 0.9 ? "text-green-700" : "text-yellow-700"}`}>
                        {((h.identity as number) * 100).toFixed(1)}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {run.qc_results?.length === 0 && run.amr_hits?.length === 0 && (
        <div className="text-sm text-gray-400">No analysis results stored for this run yet.</div>
      )}
    </div>
  );
}
