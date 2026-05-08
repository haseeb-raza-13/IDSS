import { Menu, LogOut, User } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import { useAppStore } from "@/store/appStore";

export default function TopBar() {
  const { user, logout } = useAuthStore();
  const { sidebarOpen, setSidebarOpen } = useAppStore();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <header className="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-4 shrink-0">
      <button
        onClick={() => setSidebarOpen(!sidebarOpen)}
        className="p-1.5 rounded hover:bg-gray-100 text-gray-500"
        aria-label="Toggle sidebar"
      >
        <Menu size={18} />
      </button>

      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <User size={15} />
          <span>{user?.name ?? "Researcher"}</span>
        </div>
        <button
          onClick={handleLogout}
          className="p-1.5 rounded hover:bg-gray-100 text-gray-500"
          title="Log out"
        >
          <LogOut size={16} />
        </button>
      </div>
    </header>
  );
}
