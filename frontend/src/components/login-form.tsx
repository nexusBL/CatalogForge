"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authClient } from "@/lib/auth-client";
import { authErrorMessage } from "@/lib/auth-form";

export function LoginForm({ initialMode = "password" }: { initialMode?: "password" | "otp" }) {
  const router = useRouter();
  const [mode, setMode] = useState<"password" | "otp">(initialMode);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function signInWithUsername(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    const { error: signInError } = await authClient.signIn.username({
      username: username.trim(),
      password,
    });
    setLoading(false);
    if (signInError) {
      setError(authErrorMessage(signInError.message, "Invalid username or password."));
      return;
    }
    router.push("/overview");
    router.refresh();
  }

  async function sendCode() {
    setError(null);
    setLoading(true);
    const { error: sendError } = await authClient.emailOtp.sendVerificationOtp({
      email,
      type: "sign-in",
    });
    setLoading(false);
    if (sendError) {
      setError(sendError.message || "Could not send a sign-in code.");
      return;
    }
    setSent(true);
  }

  async function verify() {
    setError(null);
    setLoading(true);
    const { error: signInError } = await authClient.signIn.emailOtp({
      email,
      otp,
    });
    setLoading(false);
    if (signInError) {
      setError(signInError.message || "That code is invalid or expired.");
      return;
    }
    router.push("/overview");
    router.refresh();
  }

  if (mode === "otp") {
    return (
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (sent) {
            void verify();
          } else {
            void sendCode();
          }
        }}
      >
        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@restaurant.com"
          />
        </div>
        {sent ? (
          <div className="space-y-2">
            <Label htmlFor="otp">One-time code</Label>
            <Input
              id="otp"
              inputMode="numeric"
              required
              value={otp}
              onChange={(event) => setOtp(event.target.value)}
              placeholder="6-digit code"
            />
          </div>
        ) : null}
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        <Button type="submit" className="w-full" disabled={loading}>
          {loading ? "Please wait…" : sent ? "Sign In" : "Send OTP"}
        </Button>
        <Button
          type="button"
          variant="ghost"
          className="w-full"
          onClick={() => {
            setMode("password");
            setSent(false);
            setError(null);
          }}
        >
          Back to username login
        </Button>
      </form>
    );
  }

  return (
    <form className="space-y-4" onSubmit={(event) => void signInWithUsername(event)}>
      <div className="space-y-2">
        <Label htmlFor="username">Username</Label>
        <Input
          id="username"
          autoComplete="username"
          required
          minLength={3}
          maxLength={30}
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          placeholder="Enter username"
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="Enter password"
        />
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      <Button type="submit" className="w-full" disabled={loading}>
        {loading ? "Please wait…" : "Sign In"}
      </Button>
      <button
        type="button"
        className="text-sm text-primary underline-offset-4 hover:underline"
        onClick={() => {
          setMode("otp");
          setError(null);
        }}
      >
        Forgot password?
      </button>
      <div className="relative py-2 text-center text-xs uppercase text-muted-foreground">
        <span className="bg-card px-2">OR</span>
      </div>
      <Button type="button" variant="outline" className="w-full" onClick={() => setMode("otp")}>
        Sign in with Email OTP
      </Button>
      <p className="text-center text-sm text-muted-foreground">
        Don&apos;t have an account?{" "}
        <Link href="/signup" className="text-primary underline-offset-4 hover:underline">
          Create Account
        </Link>
      </p>
    </form>
  );
}
