import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthState {
  token: string | null;
  refreshToken: string | null;
  user: { email: string; name: string } | null;
  setTokens: (access: string, refresh: string, user: { email: string; name: string }) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      refreshToken: null,
      user: null,
      setTokens: (access, refresh, user) =>
        set({ token: access, refreshToken: refresh, user }),
      logout: () => set({ token: null, refreshToken: null, user: null }),
    }),
    { name: "idss-auth" }
  )
);
