type Level = "RED" | "ORANGE" | "YELLOW" | "GREEN";

const CONFIG: Record<Level, string> = {
  RED: "bg-red-100 text-red-800 border border-red-300",
  ORANGE: "bg-orange-100 text-orange-800 border border-orange-300",
  YELLOW: "bg-yellow-100 text-yellow-800 border border-yellow-300",
  GREEN: "bg-green-100 text-green-800 border border-green-300",
};

interface Props {
  level: string;
  showScore?: number;
}

export function AlertLevelBadge({ level, showScore }: Props) {
  const cls = CONFIG[level as Level] ?? "bg-gray-100 text-gray-700";
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-xs font-semibold ${cls}`}>
      {level}
      {showScore !== undefined && <span className="opacity-75">· {showScore}</span>}
    </span>
  );
}
