import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useJobStatus } from "@/hooks/useJobStatus";
import { apiClient } from "@/api/client";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine } from "recharts";

export default function ForecastPage() {
  const [forecastType, setForecastType] = useState("resistance_rate");
  const [antibiotic, setAntibiotic] = useState("ampicillin");
  const [region, setRegion] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const { data: job } = useJobStatus(jobId);

  const forecastMutation = useMutation({
    mutationFn: async () => {
      const res = await apiClient.post("/api/forecast/", {
        forecast_type: forecastType,
        antibiotic: forecastType === "resistance_rate" ? antibiotic : undefined,
        region: region || undefined,
        forecast_horizon_months: 6,
      });
      return res.data;
    },
    onSuccess: (data) => setJobId(data.job_id),
  });

  const forecastResult = job?.status === "done" ? job.result : null;
  const chartData = forecastResult
    ? [
        ...(forecastResult.historical as Record<string, unknown>[] ?? []).map((p) => ({ ...p, type: "historical" })),
        ...(forecastResult.forecast as Record<string, unknown>[] ?? []).map((p) => ({ ...p, type: "forecast" })),
      ]
    : [];

  return (
    <div className="max-w-3xl space-y-5">
      <h1 className="text-xl font-semibold text-gray-900">Resistance Forecasting</h1>

      <div className="bg-white rounded-xl border p-5 space-y-4">
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="text-xs font-medium text-gray-600 block mb-1">Forecast Type</label>
            <select
              value={forecastType}
              onChange={(e) => setForecastType(e.target.value)}
              className="w-full border rounded px-2 py-1.5 text-sm"
            >
              <option value="resistance_rate">Resistance Rate</option>
              <option value="mdr_rate">MDR Rate</option>
              <option value="gene_frequency">Gene Frequency</option>
            </select>
          </div>
          {forecastType === "resistance_rate" && (
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Antibiotic</label>
              <input
                type="text"
                value={antibiotic}
                onChange={(e) => setAntibiotic(e.target.value)}
                className="w-full border rounded px-2 py-1.5 text-sm"
                placeholder="ampicillin"
              />
            </div>
          )}
          <div>
            <label className="text-xs font-medium text-gray-600 block mb-1">Region (optional)</label>
            <input
              type="text"
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              className="w-full border rounded px-2 py-1.5 text-sm"
              placeholder="All regions"
            />
          </div>
        </div>

        <button
          onClick={() => forecastMutation.mutate()}
          disabled={forecastMutation.isPending || job?.status === "running"}
          className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          {job?.status === "running" ? "Forecasting…" : "Generate Forecast"}
        </button>

        {job?.status === "failed" && (
          <p className="text-sm text-red-500">{job.error}</p>
        )}
      </div>

      {chartData.length > 0 && (
        <div className="bg-white rounded-xl border p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">
            {forecastType === "resistance_rate" ? `${antibiotic} Resistance Rate` : "Forecast"} — 6-month projection
          </h2>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={(v) => `${v}%`} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => [`${v}%`]} />
              <Line
                dataKey="value"
                stroke="#2563eb"
                strokeWidth={2}
                dot={false}
              />
              {forecastResult?.trend_direction && (
                <text x="85%" y="15%" textAnchor="middle" fontSize={12} fill="#6b7280">
                  Trend: {forecastResult.trend_direction as string}
                </text>
              )}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
