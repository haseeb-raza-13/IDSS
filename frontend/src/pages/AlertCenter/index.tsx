import { useState } from "react";
import { useAlerts } from "@/hooks/useAlerts";
import { AlertLevelBadge } from "@/components/common/AlertLevelBadge";
import { format } from "date-fns";

const LEVELS = ["ALL", "RED", "ORANGE", "YELLOW", "GREEN"];

const CARD_BG: Record<string, string> = {
  RED: "border-red-300 bg-red-50",
  ORANGE: "border-orange-300 bg-orange-50",
  YELLOW: "border-yellow-200 bg-yellow-50",
  GREEN: "border-green-200 bg-green-50",
};

export default function AlertCenter() {
  const [levelFilter, setLevelFilter] = useState("ALL");
  const { data, isLoading } = useAlerts({
    level: levelFilter === "ALL" ? undefined : levelFilter,
    days: 90,
  });

  return (
    <div className="max-w-4xl space-y-5">
      <h1 className="text-xl font-semibold text-gray-900">Alert Center</h1>

      {/* Level filter */}
      <div className="flex gap-2">
        {LEVELS.map((l) => (
          <button
            key={l}
            onClick={() => setLevelFilter(l)}
            className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
              levelFilter === l
                ? "bg-gray-900 text-white border-gray-900"
                : "bg-white text-gray-600 border-gray-300 hover:border-gray-400"
            }`}
          >
            {l}
          </button>
        ))}
      </div>

      {isLoading && <div className="text-sm text-gray-400">Loading alerts…</div>}

      <div className="space-y-3">
        {data?.items?.length === 0 && (
          <div className="text-center py-12 text-gray-400 text-sm">No alerts found for the selected filter.</div>
        )}
        {data?.items?.map((a: Record<string, unknown>) => (
          <div
            key={a.alert_id as number}
            className={`border rounded-xl p-4 ${CARD_BG[a.alert_level as string] ?? "bg-white border-gray-200"}`}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <AlertLevelBadge level={a.alert_level as string} showScore={a.alert_score as number} />
                <div>
                  <p className="text-sm font-semibold text-gray-900">{a.pathogen as string}</p>
                  <p className="text-xs text-gray-600">{(a.region as string) ?? "Unknown region"} · {a.researcher as string}</p>
                </div>
              </div>
              <span className="text-xs text-gray-500 shrink-0">
                {format(new Date(a.created_at as string), "MMM d, yyyy")}
              </span>
            </div>

            {a.triggers && (
              <div className="mt-3">
                <p className="text-xs font-medium text-gray-600 mb-1">Triggers:</p>
                <ul className="space-y-0.5">
                  {(JSON.parse(a.triggers as string) as string[]).map((t, i) => (
                    <li key={i} className="text-xs text-gray-700 flex items-start gap-1.5">
                      <span className="mt-0.5 shrink-0">•</span> {t}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
