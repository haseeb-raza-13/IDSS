import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import { login, register } from "@/api/auth";

export default function LoginPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { setTokens } = useAuthStore();
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (mode === "login") {
        const data = await login(email, password);
        setTokens(data.access_token, data.refresh_token, { email, name: email });
        navigate("/");
      } else {
        await register(email, password, name);
        const data = await login(email, password);
        setTokens(data.access_token, data.refresh_token, { email, name });
        navigate("/");
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      if (mode === "register") {
        setError(typeof detail === "string" ? detail : "Registration failed. Try a different email.");
      } else {
        setError("Invalid email or password");
      }
    } finally {
      setLoading(false);
    }
  }

  function switchMode(next: "login" | "register") {
    setMode(next);
    setError("");
    setEmail("");
    setPassword("");
    setName("");
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="bg-white rounded-xl shadow-sm border p-8 w-full max-w-sm">
        <div className="text-center mb-6">
          <h1 className="text-xl font-bold text-gray-900">IDSS</h1>
          <p className="text-sm text-gray-500 mt-1">Integrated Disease Surveillance System</p>
        </div>

        <div className="flex rounded-lg border mb-6 overflow-hidden">
          <button
            type="button"
            onClick={() => switchMode("login")}
            className={`flex-1 py-2 text-sm font-medium transition-colors ${
              mode === "login" ? "bg-blue-600 text-white" : "text-gray-600 hover:bg-gray-50"
            }`}
          >
            Sign in
          </button>
          <button
            type="button"
            onClick={() => switchMode("register")}
            className={`flex-1 py-2 text-sm font-medium transition-colors ${
              mode === "register" ? "bg-blue-600 text-white" : "text-gray-600 hover:bg-gray-50"
            }`}
          >
            Register
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {mode === "register" && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Full name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                required
              />
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              minLength={8}
              required
            />
            {mode === "register" && (
              <p className="text-xs text-gray-400 mt-1">Minimum 8 characters</p>
            )}
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-60"
          >
            {loading
              ? mode === "login" ? "Signing in…" : "Creating account…"
              : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>
      </div>
    </div>
  );
}
