"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Brain, Loader2 } from "lucide-react";

/**
 * Login Page — clean authentication for multi-tenant access.
 *
 * Uses Supabase Auth SDK when connected.
 * For now: simple email/password form that stores session locally.
 * When Supabase Auth is wired: replaces with createClientComponentClient().
 */

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"login" | "signup">("login");
  const router = useRouter();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email || !password) {
      setError("Email and password required");
      return;
    }

    setLoading(true);
    setError("");

    try {
      // TODO: Replace with Supabase Auth when ready
      // const { data, error } = await supabase.auth.signInWithPassword({ email, password })
      
      // For now: simple validation + redirect
      if (password.length < 6) {
        throw new Error("Password must be at least 6 characters");
      }

      // Store session indicator
      localStorage.setItem("ai_studio_session", JSON.stringify({
        email,
        logged_in: true,
        logged_in_at: new Date().toISOString(),
      }));

      // Redirect to home
      router.push("/");
    } catch (err) {
      setError((err as Error).message || "Authentication failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0a1a] px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-purple-600">
            <Brain className="h-6 w-6 text-white" />
          </div>
          <span className="text-2xl font-bold text-white">AI STUDIO</span>
        </div>

        {/* Title */}
        <h1 className="text-xl font-bold text-white text-center mb-1">
          {mode === "login" ? "Welcome back" : "Create your account"}
        </h1>
        <p className="text-sm text-gray-500 text-center mb-6">
          {mode === "login"
            ? "Sign in to your AI Creative Operating System"
            : "Start creating with AI Studio"}
        </p>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1.5">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm text-white placeholder:text-gray-600 outline-none focus:border-purple-500/50"
              autoFocus
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1.5">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm text-white placeholder:text-gray-600 outline-none focus:border-purple-500/50"
            />
          </div>

          {error && (
            <div className="rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-2">
              <p className="text-xs text-red-400">{error}</p>
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-purple-600 py-3 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50 flex items-center justify-center gap-2 transition-colors"
          >
            {loading && <Loader2 className="h-4 w-4 animate-spin" />}
            {mode === "login" ? "Sign In" : "Create Account"}
          </button>
        </form>

        {/* Toggle */}
        <p className="mt-6 text-center text-xs text-gray-500">
          {mode === "login" ? (
            <>
              Don&apos;t have an account?{" "}
              <button onClick={() => setMode("signup")} className="text-purple-400 hover:text-purple-300">
                Sign up
              </button>
            </>
          ) : (
            <>
              Already have an account?{" "}
              <button onClick={() => setMode("login")} className="text-purple-400 hover:text-purple-300">
                Sign in
              </button>
            </>
          )}
        </p>

        {/* Footer */}
        <p className="mt-8 text-center text-[10px] text-gray-600">
          AI Studio — Your AI Creative Operating System
        </p>
      </div>
    </div>
  );
}
