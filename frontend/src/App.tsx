import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import Layout from "@/components/layout/Layout";
import LoginPage from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import PipelineWizard from "@/pages/PipelineWizard";
import ResultsViewer from "@/pages/ResultsViewer";
import AlertCenter from "@/pages/AlertCenter";
import MLStudio from "@/pages/MLStudio";
import PhenotypicsIngest from "@/pages/PhenotypicsIngest";
import ForecastPage from "@/pages/ForecastPage";
import History from "@/pages/History";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <Layout />
            </RequireAuth>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="pipeline" element={<PipelineWizard />} />
          <Route path="results/:runId" element={<ResultsViewer />} />
          <Route path="alerts" element={<AlertCenter />} />
          <Route path="ml" element={<MLStudio />} />
          <Route path="phenotypics" element={<PhenotypicsIngest />} />
          <Route path="forecast" element={<ForecastPage />} />
          <Route path="history" element={<History />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
