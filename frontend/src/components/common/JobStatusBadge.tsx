type Status = "pending" | "running" | "done" | "failed";

const CONFIG: Record<Status, { label: string; className: string }> = {
  pending: { label: "Pending", className: "bg-gray-100 text-gray-600" },
  running: { label: "Running", className: "bg-blue-100 text-blue-700 animate-pulse" },
  done: { label: "Done", className: "bg-green-100 text-green-700" },
  failed: { label: "Failed", className: "bg-red-100 text-red-700" },
};

interface Props {
  status: Status;
}

export function JobStatusBadge({ status }: Props) {
  const { label, className } = CONFIG[status] ?? CONFIG.pending;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${className}`}>
      {label}
    </span>
  );
}
