import { SessionRedirect } from "@/components/session-redirect";
import { SignupForm } from "@/components/signup-form";
import { ThemeToggle } from "@/components/theme-toggle";

export default function SignupPage() {
  return (
    <div className="flex min-h-[100dvh] items-center justify-center px-4">
      <SessionRedirect />
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>
      <div className="w-full max-w-md space-y-6 rounded-lg border border-border bg-card p-8 shadow-sm">
        <div className="space-y-2">
          <h1 className="text-3xl font-medium">CatalogForge</h1>
          <p className="text-sm text-muted-foreground">Create your account</p>
        </div>
        <SignupForm />
      </div>
    </div>
  );
}
