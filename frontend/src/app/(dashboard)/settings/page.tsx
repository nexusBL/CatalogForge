"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Container from "@/components/container";
import { DashboardShell } from "@/components/dashboard-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authClient } from "@/lib/auth-client";
import {
  DEFAULT_NOTIFICATIONS,
  loadNotificationPrefs,
  saveNotificationPrefs,
  type NotificationPrefs,
} from "@/lib/account-profile";

type PasswordClient = typeof authClient & {
  changePassword?: (args: {
    currentPassword: string;
    newPassword: string;
    revokeOtherSessions?: boolean;
  }) => Promise<{ error?: { message?: string } | null }>;
};

export default function SettingsPage() {
  const router = useRouter();
  const { data: session } = authClient.useSession();
  const user = session?.user as { id?: string; email?: string | null } | undefined;
  const [prefs, setPrefs] = useState<NotificationPrefs>(DEFAULT_NOTIFICATIONS);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordMessage, setPasswordMessage] = useState("");

  useEffect(() => {
    setPrefs(loadNotificationPrefs(user?.id));
  }, [user?.id]);

  async function signOut() {
    await authClient.signOut();
    router.replace("/");
  }

  async function onChangePassword(event: React.FormEvent) {
    event.preventDefault();
    const client = authClient as PasswordClient;
    if (!client.changePassword) {
      setPasswordMessage("Password changes are not enabled for this sign-in method yet.");
      return;
    }
    const result = await client.changePassword({
      currentPassword,
      newPassword,
      revokeOtherSessions: true,
    });
    setPasswordMessage(result.error?.message || "Password updated.");
    if (!result.error) {
      setCurrentPassword("");
      setNewPassword("");
    }
  }

  function onSaveNotifications() {
    saveNotificationPrefs(user?.id, prefs);
  }

  return (
    <DashboardShell title="Settings">
      <Container className="space-y-8 py-6">
        <p className="text-sm text-muted-foreground">Signed in as {user?.email || "your account"}</p>

        <section className="space-y-3">
          <h2 className="text-lg font-medium">Change password</h2>
          <form className="max-w-md space-y-3" onSubmit={(event) => void onChangePassword(event)}>
            <div className="space-y-2">
              <Label htmlFor="current-password">Current password</Label>
              <Input
                id="current-password"
                type="password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-password">New password</Label>
              <Input
                id="new-password"
                type="password"
                minLength={8}
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
              />
            </div>
            <Button type="submit" variant="outline">
              Update password
            </Button>
            {passwordMessage ? <p className="text-sm text-muted-foreground">{passwordMessage}</p> : null}
          </form>
        </section>

        <section className="space-y-3">
          <h2 className="text-lg font-medium">Notification preferences</h2>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={prefs.catalogueReady}
              onChange={(event) => setPrefs((current) => ({ ...current, catalogueReady: event.target.checked }))}
            />
            Catalogue ready
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={prefs.extractionFailed}
              onChange={(event) => setPrefs((current) => ({ ...current, extractionFailed: event.target.checked }))}
            />
            Extraction failed
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={prefs.productUpdates}
              onChange={(event) => setPrefs((current) => ({ ...current, productUpdates: event.target.checked }))}
            />
            Product updates
          </label>
          <Button type="button" variant="outline" onClick={onSaveNotifications}>
            Save notifications
          </Button>
        </section>

        <section className="space-y-3">
          <h2 className="text-lg font-medium">Account settings</h2>
          <p className="max-w-xl text-sm text-muted-foreground">
            Profile details are stored on this device and tied to your signed-in account. Use Profile to update personal
            and business information.
          </p>
          <Button type="button" variant="outline" onClick={() => router.push("/profile")}>
            Open profile
          </Button>
        </section>

        <section className="space-y-3">
          <h2 className="text-lg font-medium">Logout</h2>
          <Button variant="outline" onClick={() => void signOut()}>
            Logout
          </Button>
        </section>
      </Container>
    </DashboardShell>
  );
}
