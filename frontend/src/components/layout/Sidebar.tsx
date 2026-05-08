import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Play,
  Bell,
  Brain,
  FlaskConical,
  TrendingUp,
  History,
  Database,
} from "lucide-react";
import { useAppStore } from "@/store/appStore";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/pipeline", label: "Run Pipeline", icon: Play },
  { to: "/alerts", label: "Alert Center", icon: Bell },
  { to: "/phenotypics", label: "Phenotypics", icon: FlaskConical },
  { to: "/ml", label: "ML Studio", icon: Brain },
  { to: "/forecast", label: "Forecasting", icon: TrendingUp },
  { to: "/history", label: "History", icon: History },
];

export default function Sidebar() {
  const open = useAppStore((s) => s.sidebarOpen);

  if (!open) return null;

  return (
    <aside
      className="fixed left-0 top-0 h-full bg-white border-r border-gray-200 flex flex-col z-10"
      style={{ width: "var(--sidebar-width)" }}
    >
      <div className="flex items-center gap-2 px-4 py-4 border-b border-gray-200">
        <Database className="text-blue-600" size={22} />
        <span className="font-semibold text-gray-800 text-sm">IDSS</span>
      </div>

      <nav className="flex-1 py-3 overflow-y-auto">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                isActive
                  ? "bg-blue-50 text-blue-700 font-medium border-r-2 border-blue-600"
                  : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
              }`
            }
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="px-4 py-3 border-t border-gray-200">
        <p className="text-xs text-gray-400">AMR Surveillance v0.1</p>
      </div>
    </aside>
  );
}
