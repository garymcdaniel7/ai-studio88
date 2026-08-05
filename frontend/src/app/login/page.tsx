"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Brain, Loader2, ArrowRight } from "lucide-react";
import { supabase, isSupabaseConfigured } from "@/lib/supabase";
import { SupabaseUnavailable } from "@/components/supabase-unavailable";
import { isDevBypassAllowed, validateRedirectTarget } from "@/lib/auth-utils";

/**
 * Login Page — Supabase Auth for multi-tenant access.
 *
 * Uses Supabase Auth (signInWithPassword/signUp) which sets secure
 * httpOnly cookies managed by @supabase/ssr. No custom cookies needed.
 *
 * Wrapped in Suspense for Next.js static generation requirements.
 */

export default function LoginPage() {
  return (
    <Suspense fallback={<LoginSkeleton />}>
      <LoginContent />
    </Suspense>
  );
}

function LoginSkeleton() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0a1a]">
      <Loader2 className="h-8 w-8 animate-spin text-purple-500" />
    </div>
  );
}

function LoginContent() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [successMessage, setSuccessMessage] = useState("");
  const router = useRouter();
  const searchParams = useSearchParams();

  // Validate the redirect target (prevents open-redirect attacks)
  const redirect = validateRedirectTarget(searchParams.get("redirect"));

  // If Supabase is not configured, show unavailable state
  if (!isSupabaseConfigured) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#0a0a1a]">
        <SupabaseUnavailable action="sign in" />
      </div>
    );
  }

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
        const { data, error: authError } = await supabase!.auth.signInWithPassword({
          email,
          password,
        });

        if (authError) {
          throw new Error(authError.message);
        }

        if (data.session) {
          // Supabase SSR handles cookie management automatically.
          // No custom cookie needed — middleware validates via getUser().
          router.push(redirect);
          router.refresh(); // Trigger middleware re-evaluation
        }
      } else {
        // Sign up
        const { error: authError } = await supabase!.auth.signUp({
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

        {/* Signup onboarding hint */}
        {mode === "signup" && (
          <div className="mb-4 rounded-lg border border-purple-500/20 bg-purple-500/5 px-4 py-3">
            <p className="text-xs text-purple-300 font-medium mb-1">How it works</p>
            <div className="flex items-center gap-2 text-[11px] text-gray-400">
              <span className="rounded-full bg-purple-600/30 px-2 py-0.5 text-purple-300">1</span>
              Create account
              <ArrowRight className="h-3 w-3 text-gray-600" />
              <span className="rounded-full bg-purple-600/30 px-2 py-0.5 text-purple-300">2</span>
              Connect GPU provider
              <ArrowRight className="h-3 w-3 text-gray-600" />
              <span className="rounded-full bg-purple-600/30 px-2 py-0.5 text-purple-300">3</span>
              Generate
            </div>
            <p className="text-[10px] text-gray-500 mt-2">
              After signup, configure your Vast.ai or RunPod API key in Admin &rarr; API Keys.
              You only pay for GPU time you use — no subscription.
            </p>
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

        {/* Dev Bypass — ONLY in development, NEVER in production */}
        {isDevBypassAllowed && (
          <div className="mt-6 border-t border-white/[0.06] pt-4">
            <p className="text-[10px] text-yellow-500/70 text-center mb-2">
              Development mode only — this button does not exist in production builds.
            </p>
            <button
              onClick={() => router.push(redirect)}
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
