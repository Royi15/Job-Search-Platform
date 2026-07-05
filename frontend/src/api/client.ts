import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export const tokens = {
  get access() {
    return localStorage.getItem("access_token");
  },
  get refresh() {
    return localStorage.getItem("refresh_token");
  },
  save(access: string, refresh: string) {
    localStorage.setItem("access_token", access);
    localStorage.setItem("refresh_token", refresh);
  },
  clear() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
  },
};

const api = axios.create({ baseURL: BASE_URL });

api.interceptors.request.use((config) => {
  if (tokens.access) config.headers.Authorization = `Bearer ${tokens.access}`;
  return config;
});

// Endpoints where a 401 means "bad credentials", not "expired session" —
// the silent-refresh logic must never hijack these.
const NO_REFRESH = ["/auth/login", "/auth/register", "/auth/refresh"];

// On 401, try one silent refresh, then replay the original request.
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    const isCredentialCall = NO_REFRESH.some((p) => original?.url?.includes(p));
    if (
      error.response?.status === 401 &&
      !isCredentialCall &&
      !original._retried &&
      tokens.refresh
    ) {
      original._retried = true;
      try {
        const { data } = await axios.post(`${BASE_URL}/auth/refresh`, {
          refresh_token: tokens.refresh,
        });
        tokens.save(data.access_token, data.refresh_token);
        original.headers.Authorization = `Bearer ${data.access_token}`;
        return api(original);
      } catch {
        tokens.clear();
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export default api;
