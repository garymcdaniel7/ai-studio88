"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Brain, Loader2 } from "lucide-react";
import { supabase } from "@/lib/supabase";

/**
 * Login Page — Supabase Auth for multi-tenant access.
 *
 * Supports email/password sign-in and sign-up via Supabase Auth.
 * On success, sets a cookie for the middleware and redirects to the app.
 */

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [successMessage, setSuccessMessage] = useState("");
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirect = searchParams.get("redirect") || "/";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email || !password) {
      setError("Email and password required");
      return;
    }
    if (password.length < 6) {
      setError("Password must be at least 6 characters");
      return;
    }

    setLoading(true);
    setError("");
    setSuccessMessage("");

    try {
      if (mode === "login") {
        const { data, error: authError } = await supabase.auth.signInWithPassword({
          email,
          password,
        });

        if (authError) {
          throw new Error(authError.message);
        }

        if (data.session) {
          // Set cookie for middleware to detect
          document.cookie = `ai_studio_auth=${data.session.access_token}; path=/; max-age=604800; SameSite=Lax`;
          router.push(redirect);
        }
      } else {
        // Sign up
        const { error: authError } = await supabase.auth.signUp({
          email,
          password,
        });

        if (authError) {
          throw new Error(authError.message);
        }

        setSuccessMessage("Account created! Check your email to confirm, then sign in.");
        setMode("login");
      }
    } catch (err) {
      setError((err as Error).message || "Authentication failed");
    } finally {
      setLoading(false);
    }
  }

  // Dev mode: allow bypass for local development without Supabase Auth configured
  function handleDevBypass() {
    document.cookie = "ai_studio_auth=dev_bypass; path=/; max-age=604800; SameSite=Lax";
    localStorage.setItem("ai_studio_session", JSON.stringify({
      email: "dev@localhost",
      logged_in: true,
      dev_mode: true,
    }));
    router.push(redirect);
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

        {/* Success Message */}
        {successMessage && (
          <div className="mb-4 rounded-lg border border-green-500/20 bg-green-500/5 px-4 py-2">
            <p className="text-xs text-green-400">{successMessage}</p>
          </div>
        )}

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
              placeholder="At least 6 characters"
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

        {/* Dev Bypass — only show in development */}
        {process.env.NODE_ENV === "development" && (
          <div className="mt-6 border-t border-white/[0.06] pt-4">
            <button
              onClick={handleDevBypass}
              className="w-full rounded-lg border border-white/[0.08] py-2 text-xs text-gray-500 hover:text-gray-300 hover:bg-white/[0.03] transition-colors"
            >
              Skip login (dev mode only)
            </button>
          </div>
        )}

        {/* Footer */}
        <p className="mt-8 text-center text-[10px] text-gray-600">
          AI Studio — Your AI Creative Operating System
        </p>
      </div>
    </div>
  );
}
