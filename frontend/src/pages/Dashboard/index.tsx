import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Play, Bell, Database, TrendingUp } from "lucide-react";
import { listRuns } from "@/api/history";
import { listAlerts } from "@/api/alerts";
import { AlertLevelBadge } from "@/components/common/AlertLevelBadge";
import { format } from "date-fns";

export default function Dashboard() {
  const { data: runs } = useQuery({ queryKey: ["runs", { page: 1, page_size: 10 }], queryFn: () => listRuns({ page: 1, page_size: 10 }) });
  const { data: alerts } = useQuery({ queryKey: ["alerts", { days: 30 }], queryFn: () => listAlerts({ days: 30 }) });

  const redCount = alerts?.items?.filter((a: { alert_level: string }) => a.alert_level === "RED").length ?? 0;
  const orangeCount = alerts?.items?.filter((a: { alert_level: string }) => a.alert_level === "ORANGE").length ?? 0;

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-900">Dashboard</h1>
        <Link
          to="/pipeline"
          className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700"
        >
          <Play size={14} />
          New Pipeline Run
        </Link>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-3 gap-4">
        <KPICard
          icon={<Database size={18} className="text-blue-500" />}
          label="Total Runs"
          value={runs?.total ?? "—"}
          bg="bg-blue-50"
        />
        <KPICard
          icon={<Bell size={18} className="text-red-500" />}
          label="RED/ORANGE Alerts (30d)"
          value={redCount + orangeCount}
          bg="bg-red-50"
          highlight={redCount + orangeCount > 0}
        />
        <KPICard
          icon={<TrendingUp size={18} className="text-green-500" />}
          label="Recent Alerts"
          value={alerts?.total ?? "—"}
          bg="bg-green-50"
        />
      </div>

      {/* Recent runs */}
      <section>
        <h2 className="text-sm font-semibold text-gray-700 mb-3">Recent Pipeline Runs</h2>
        <div className="bg-white rounded-xl border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                {["Pathogen", "Researcher", "Region", "Samples", "Alert", "Date"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {runs?.items?.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-gray-400 text-sm">
                    No runs yet.{" "}
                    <Link to="/pipeline" className="text-blue-600 hover:underline">
                      Start your first pipeline run.
                    </Link>
                  </td>
                </tr>
              )}
              {runs?.items?.map((run: Record<string, unknown>) => (
                <tr key={run.run_id as string} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900">{run.pathogen as string}</td>
                  <td className="px-4 py-3 text-gray-600">{run.researcher as string}</td>
                  <td className="px-4 py-3 text-gray-600">{(run.region as string) ?? "—"}</td>
                  <td className="px-4 py-3 text-gray-600">{run.sample_count as number}</td>
                  <td className="px-4 py-3">
                    {run.alert_level ? (
                      <AlertLevelBadge level={run.alert_level as string} showScore={run.alert_score as number} />
                    ) : (
                      <span className="text-gray-400 text-xs">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {format(new Date(run.created_at as string), "MMM d, yyyy")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Recent critical alerts */}
      {redCount + orangeCount > 0 && (
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-700">Critical Alerts</h2>
            <Link to="/alerts" className="text-xs text-blue-600 hover:underline">View all →</Link>
          </div>
          <div className="space-y-2">
            {alerts?.items
              ?.filter((a: { alert_level: string }) => ["RED", "ORANGE"].includes(a.alert_level))
              .slice(0, 3)
              .map((a: Record<string, unknown>) => (
                <div key={a.alert_id as number} className="flex items-center gap-3 bg-white border rounded-lg px-4 py-3">
                  <AlertLevelBadge level={a.alert_level as string} showScore={a.alert_score as number} />
                  <span className="text-sm font-medium text-gray-800">{a.pathogen as string}</span>
                  <span className="text-sm text-gray-500">{(a.region as string) ?? "Unknown region"}</span>
                  <span className="ml-auto text-xs text-gray-400">
                    {format(new Date(a.created_at as string), "MMM d")}
                  </span>
                </div>
              ))}
          </div>
        </section>
      )}
    </div>
  );
}

function KPICard({ icon, label, value, bg, highlight }: {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  bg: string;
  highlight?: boolean;
}) {
  return (
    <div className={`${bg} rounded-xl p-4 border ${highlight ? "border-red-200" : "border-transparent"}`}>
      <div className="flex items-center gap-2 mb-2">{icon}</div>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      <p className="text-xs text-gray-600 mt-0.5">{label}</p>
    </div>
  );
}
