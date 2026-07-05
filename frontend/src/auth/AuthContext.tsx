import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import api, { tokens } from "../api/client";
import type { Me } from "../api/types";

interface AuthState {
  user: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => void;
  refreshMe: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshMe = useCallback(async () => {
    const { data } = await api.get<Me>("/auth/me");
    setUser(data);
  }, []);

  useEffect(() => {
    if (!tokens.access) {
      setLoading(false);
      return;
    }
    refreshMe()
      .catch(() => tokens.clear())
      .finally(() => setLoading(false));
  }, [refreshMe]);

  const login = useCallback(
    async (email: string, password: string) => {
      const { data } = await api.post("/auth/login", { email, password });
      tokens.save(data.access_token, data.refresh_token);
      await refreshMe();
    },
    [refreshMe]
  );

  const register = useCallback(
    async (email: string, password: string, fullName: string) => {
      const { data } = await api.post("/auth/register", {
        email,
        password,
        full_name: fullName || null,
      });
      tokens.save(data.access_token, data.refresh_token);
      await refreshMe();
    },
    [refreshMe]
  );

  const logout = useCallback(() => {
    tokens.clear();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refreshMe }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
