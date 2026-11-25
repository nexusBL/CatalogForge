"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authClient } from "@/lib/auth-client";
import { authErrorMessage, validateSignupPasswords, validateUsername } from "@/lib/auth-form";

export function SignupForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [usernameStatus, setUsernameStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const value = username.trim();
    const localError = validateUsername(value);
    if (!value) {
      setUsernameStatus(null);
      return;
    }
    if (localError) {
      setUsernameStatus(localError);
      return;
    }
    const timer = window.setTimeout(() => {
      void authClient.isUsernameAvailable({ username: value }).then(({ data, error: checkError }) => {
        if (checkError) {
          setUsernameStatus(null);
          return;
        }
        setUsernameStatus(data?.available ? "Username is available." : "That username is already taken. Please try another.");
      });
    }, 500);
    return () => window.clearTimeout(timer);
  }, [username]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const usernameError = validateUsername(username);
    if (usernameError) {
      setError(usernameError);
      return;
    }
    const passwordError = validateSignupPasswords(password, confirmPassword);
    if (passwordError) {
      setError(passwordError);
      return;
    }
    setLoading(true);
    const { error: signUpError } = await authClient.signUp.email({
      name: name.trim(),
      email: email.trim(),
      username: username.trim(),
      password,
    });
    setLoading(false);
    if (signUpError) {
      setError(authErrorMessage(signUpError.message, "Could not create the account."));
      return;
    }
    router.push("/overview");
    router.refresh();
  }

  return (
    <form className="space-y-4" onSubmit={(event) => void onSubmit(event)}>
      <div className="space-y-2">
        <Label htmlFor="name">Name</Label>
        <Input
          id="name"
          required
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Your name"
        />
      </div>
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
          placeholder="choose username"
        />
        {usernameStatus ? (
          <p
            className={
              usernameStatus.includes("available") ? "text-sm text-muted-foreground" : "text-sm text-destructive"
            }
          >
            {usernameStatus}
          </p>
        ) : null}
      </div>
      <div className="space-y-2">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="********"
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="confirm_password">Confirm Password</Label>
        <Input
          id="confirm_password"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          value={confirmPassword}
          onChange={(event) => setConfirmPassword(event.target.value)}
          placeholder="********"
        />
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      <Button type="submit" className="w-full" disabled={loading}>
        {loading ? "Please wait…" : "Create Account"}
      </Button>
      <p className="text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link href="/" className="text-primary underline-offset-4 hover:underline">
          Sign In
        </Link>
      </p>
    </form>
  );
}
