import { useState } from "react";
import { Link } from "react-router-dom";
import { useRunHistory } from "@/hooks/useRunHistory";
import { AlertLevelBadge } from "@/components/common/AlertLevelBadge";
import { format } from "date-fns";

export default function History() {
  const [page, setPage] = useState(1);
  const { data, isLoading } = useRunHistory({ page, page_size: 20 });

  return (
    <div className="max-w-5xl space-y-4">
      <h1 className="text-xl font-semibold text-gray-900">Run History</h1>

      <div className="bg-white rounded-xl border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              {["Pathogen", "Researcher", "Study", "Region", "Samples", "Alert", "Date", ""].map((h) => (
                <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {isLoading && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-gray-400 text-sm">Loading…</td>
              </tr>
            )}
            {!isLoading && data?.items?.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-gray-400 text-sm">No runs yet.</td>
              </tr>
            )}
            {data?.items?.map((run: Record<string, unknown>) => (
              <tr key={run.run_id as string} className="hover:bg-gray-50">
                <td className="px-4 py-3 font-medium text-gray-900">{run.pathogen as string}</td>
                <td className="px-4 py-3 text-gray-600">{run.researcher as string}</td>
                <td className="px-4 py-3 text-gray-600 max-w-32 truncate">{run.study_name as string}</td>
                <td className="px-4 py-3 text-gray-500">{(run.region as string) ?? "—"}</td>
                <td className="px-4 py-3 text-gray-500">{run.sample_count as number}</td>
                <td className="px-4 py-3">
                  {run.alert_level ? (
                    <AlertLevelBadge level={run.alert_level as string} showScore={run.alert_score as number} />
                  ) : "—"}
                </td>
                <td className="px-4 py-3 text-gray-400 text-xs">
                  {format(new Date(run.created_at as string), "MMM d, yyyy")}
                </td>
                <td className="px-4 py-3">
                  <Link
                    to={`/results/${run.run_id}`}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    View →
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {data && data.pages > 1 && (
        <div className="flex justify-center gap-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-1.5 text-sm border rounded hover:bg-gray-50 disabled:opacity-50"
          >
            ←
          </button>
          <span className="px-3 py-1.5 text-sm text-gray-600">
            Page {page} of {data.pages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
            disabled={page === data.pages}
            className="px-3 py-1.5 text-sm border rounded hover:bg-gray-50 disabled:opacity-50"
          >
            →
          </button>
        </div>
      )}
    </div>
  );
}
