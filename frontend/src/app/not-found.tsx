import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex min-h-[100dvh] items-center justify-center px-4">
      <div className="w-full max-w-md space-y-4 rounded-lg border border-border bg-card p-8 text-center shadow-sm">
        <h1 className="text-xl font-medium">Page not found</h1>
        <p className="text-sm text-muted-foreground">This page does not exist.</p>
        <Button asChild>
          <Link href="/">Back to sign in</Link>
        </Button>
      </div>
    </div>
  );
}
