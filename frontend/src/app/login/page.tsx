"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Brain, Loader2, ArrowRight } from "lucide-react";
import { isSupabaseConfigured } from "@/lib/supabase";
import { signInWithGoogle, signInWithEmail, signUpWithEmail } from "@/lib/auth";
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
  const [googleLoading, setGoogleLoading] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [successMessage, setSuccessMessage] = useState("");
  const router = useRouter();
  const searchParams = useSearchParams();

  // Validate the redirect target (prevents open-redirect attacks)
  const redirect = validateRedirectTarget(searchParams.get("redirect"));

  // Check for error from OAuth callback
  const callbackError = searchParams.get("error");

  // If Supabase is not configured, show unavailable state
  if (!isSupabaseConfigured) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#0a0a1a]">
        <SupabaseUnavailable action="sign in" />
      </div>
    );
  }

  async function handleGoogleSignIn() {
    setGoogleLoading(true);
    setError("");

    const result = await signInWithGoogle(redirect);

    if (!result.success) {
      setError(result.error || "Failed to initiate Google sign-in");
      setGoogleLoading(false);
      return;
    }

    // Redirect to Google OAuth consent screen
    if (result.redirectUrl) {
      window.location.href = result.redirectUrl;
    }
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
        const result = await signInWithEmail(email, password);

        if (!result.success) {
          throw new Error(result.error);
        }

        // Supabase SSR handles cookie management automatically.
        // No custom cookie needed — middleware validates via getUser().
        router.push(redirect);
        router.refresh(); // Trigger middleware re-evaluation
      } else {
        const result = await signUpWithEmail(email, password);

        if (!result.success) {
          throw new Error(result.error);
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

        {/* OAuth Error from Callback */}
        {callbackError && !error && (
          <div className="mb-4 rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-2">
            <p className="text-xs text-red-400">{callbackError}</p>
          </div>
        )}

        {/* Continue with Google */}
        <button
          type="button"
          onClick={handleGoogleSignIn}
          disabled={googleLoading || loading}
          className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] py-3 text-sm font-medium text-white hover:bg-white/[0.06] disabled:opacity-50 flex items-center justify-center gap-3 transition-colors mb-4"
          aria-label="Continue with Google"
        >
          {googleLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <svg className="h-4 w-4" viewBox="0 0 24 24" aria-hidden="true">
              <path
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                fill="#4285F4"
              />
              <path
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                fill="#34A853"
              />
              <path
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                fill="#FBBC05"
              />
              <path
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                fill="#EA4335"
              />
            </svg>
          )}
          Continue with Google
        </button>

        {/* Divider */}
        <div className="relative mb-4">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-white/[0.06]" />
          </div>
          <div className="relative flex justify-center text-xs">
            <span className="bg-[#0a0a1a] px-3 text-gray-500">or</span>
          </div>
        </div>

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
