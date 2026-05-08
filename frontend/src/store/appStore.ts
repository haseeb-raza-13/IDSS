import { create } from "zustand";

interface AppState {
  activeJobId: string | null;
  setActiveJobId: (id: string | null) => void;
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  googleConnected: boolean;
  setGoogleConnected: (v: boolean) => void;
}

export const useAppStore = create<AppState>((set) => ({
  activeJobId: null,
  setActiveJobId: (id) => set({ activeJobId: id }),
  sidebarOpen: true,
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  googleConnected: false,
  setGoogleConnected: (v) => set({ googleConnected: v }),
}));
