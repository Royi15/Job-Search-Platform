import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import Landing from "./pages/Landing";
import AuthPage from "./pages/AuthPage";
import AppLayout from "./pages/AppLayout";
import Welcome from "./pages/Welcome";
import Board from "./features/board/Board";
import AlertsFeed from "./features/alerts/AlertsFeed";
import Preferences from "./features/preferences/Preferences";
import Resumes from "./features/resumes/Resumes";
import Tailor from "./features/ai/Tailor";
import CoverLetter from "./features/ai/CoverLetter";
import Settings from "./features/settings/Settings";
import Trivisum from "./features/trivisum/Trivisum";

// Lazy: pulls in CodeMirror + language packages (~700KB) only when someone
// actually opens the interview simulator, not on every page load.
const Interview = lazy(() => import("./features/interview/Interview"));
// Lazy: pulls in KaTeX (math rendering) only when someone opens the
// notebook generator, not on every page load.
const Notebooks = lazy(() => import("./features/notebooks/Notebooks"));

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="page-loader">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<AuthPage mode="login" />} />
          <Route path="/register" element={<AuthPage mode="register" />} />
          <Route
            path="/app"
            element={
              <RequireAuth>
                <Outlet />
              </RequireAuth>
            }
          >
            <Route index element={<Welcome />} />

            <Route path="job" element={<AppLayout hub="job" />}>
              <Route index element={<Board />} />
              <Route path="alerts" element={<AlertsFeed />} />
              <Route path="preferences" element={<Preferences />} />
              <Route path="resumes" element={<Resumes />} />
              <Route path="tailor" element={<Tailor />} />
              <Route path="cover-letter" element={<CoverLetter />} />
              <Route
                path="interview"
                element={
                  <Suspense fallback={<div className="page-loader">Loading…</div>}>
                    <Interview />
                  </Suspense>
                }
              />
              <Route path="settings" element={<Settings />} />
            </Route>

            <Route path="study" element={<AppLayout hub="study" />}>
              <Route
                index
                element={
                  <Suspense fallback={<div className="page-loader">Loading…</div>}>
                    <Notebooks />
                  </Suspense>
                }
              />
              <Route path="trivisum" element={<Trivisum />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
