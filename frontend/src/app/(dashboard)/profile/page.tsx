"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Container from "@/components/container";
import { DashboardShell } from "@/components/dashboard-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authClient } from "@/lib/auth-client";
import { changePasswordErrorMessage, validateChangePassword } from "@/lib/auth-form";
import { profileLabel } from "@/components/nav/side-nav/components/profile-menu";
import { cn } from "@/lib/utils";
import {
  EMPTY_PROFILE,
  loadAccountProfile,
  profileHeadline,
  saveAccountProfile,
  type AccountProfile,
} from "@/lib/account-profile";

type PasswordClient = typeof authClient & {
  changePassword?: (args: {
    currentPassword: string;
    newPassword: string;
    revokeOtherSessions?: boolean;
  }) => Promise<{ error?: { message?: string } | null }>;
};

export default function ProfilePage() {
  const router = useRouter();
  const { data: session } = authClient.useSession();
  const user = session?.user as
    | { id?: string; name?: string | null; username?: string | null; email?: string | null; image?: string | null }
    | undefined;
  const [profile, setProfile] = useState<AccountProfile>(() => ({
    ...EMPTY_PROFILE,
    fullName: profileLabel(user),
    email: user?.email?.trim() || "",
    photoDataUrl: user?.image || "",
  }));
  const [editing, setEditing] = useState(false);
  const [saved, setSaved] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState("");
  const [passwordSuccess, setPasswordSuccess] = useState(false);

  useEffect(() => {
    const stored = loadAccountProfile(user?.id);
    setProfile({
      ...stored,
      fullName: stored.fullName || profileLabel(user),
      email: stored.email || user?.email?.trim() || "",
      photoDataUrl: stored.photoDataUrl || user?.image || "",
    });
  }, [user?.id, user?.email, user?.image, user?.name, user?.username]);

  const headline = useMemo(() => profileHeadline(profile), [profile]);

  function update<K extends keyof AccountProfile>(key: K, value: AccountProfile[K]) {
    setProfile((current) => ({ ...current, [key]: value }));
    setSaved(false);
  }

  function onPhoto(file: File | undefined) {
    if (!file) {
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const result = typeof reader.result === "string" ? reader.result : "";
      if (result.length > 350_000) {
        window.alert("Please choose a smaller photo (under ~250KB).");
        return;
      }
      update("photoDataUrl", result);
    };
    reader.readAsDataURL(file);
  }

  function onSave(event: React.FormEvent) {
    event.preventDefault();
    saveAccountProfile(user?.id, profile);
    setEditing(false);
    setSaved(true);
  }

  async function onChangePassword(event: React.FormEvent) {
    event.preventDefault();
    if (passwordBusy) {
      return;
    }
    const validationError = validateChangePassword(currentPassword, newPassword, confirmPassword);
    if (validationError) {
      setPasswordSuccess(false);
      setPasswordMessage(validationError);
      return;
    }
    const client = authClient as PasswordClient;
    if (!client.changePassword) {
      setPasswordSuccess(false);
      setPasswordMessage("Password changes are not enabled for this sign-in method yet.");
      return;
    }
    setPasswordBusy(true);
    setPasswordMessage("");
    setPasswordSuccess(false);
    try {
      const result = await client.changePassword({
        currentPassword,
        newPassword,
        revokeOtherSessions: true,
      });
      if (result.error) {
        setPasswordSuccess(false);
        setPasswordMessage(changePasswordErrorMessage(result.error.message, "Could not change password."));
        return;
      }
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPasswordSuccess(true);
      setPasswordMessage("Password updated.");
    } catch {
      setPasswordSuccess(false);
      setPasswordMessage("Could not change password. Please try again.");
    } finally {
      setPasswordBusy(false);
    }
  }

  return (
    <DashboardShell title="Profile">
      <Container className="space-y-6 py-6">
        <Card>
          <CardContent className="flex flex-col gap-4 p-6 phone:flex-row phone:items-start">
            {profile.photoDataUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={profile.photoDataUrl} alt="" className="h-20 w-20 rounded-2xl object-cover" />
            ) : (
              <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-selected text-lg font-medium">
                {(profile.fullName || "U").slice(0, 2).toUpperCase()}
              </div>
            )}
            <div className="min-w-0 space-y-1 text-sm">
              <p className="text-xl font-medium">{profile.fullName || "Your name"}</p>
              {headline ? <p className="text-muted-foreground">{headline}</p> : null}
              {profile.email ? <p>📧 {profile.email}</p> : null}
              {profile.phone ? <p>📱 {profile.phone}</p> : null}
              {profile.city ? <p>📍 {profile.city}</p> : null}
            </div>
          </CardContent>
        </Card>

        <div className="flex flex-wrap gap-2">
          <Button type="button" onClick={() => setEditing((value) => !value)}>
            {editing ? "Close editor" : "Edit Profile"}
          </Button>
          <Button type="button" variant="outline" onClick={() => router.push("/settings")}>
            Account settings
          </Button>
        </div>
        {saved ? <p className="text-sm text-muted-foreground">Profile saved on this device.</p> : null}

        <section className="space-y-3">
          <h2 className="text-lg font-medium">Change password</h2>
          <form className="max-w-md space-y-3" onSubmit={(event) => void onChangePassword(event)}>
            <div className="space-y-2">
              <Label htmlFor="profile-current-password">Current password</Label>
              <Input
                id="profile-current-password"
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                disabled={passwordBusy}
                onChange={(event) => {
                  setCurrentPassword(event.target.value);
                  setPasswordMessage("");
                  setPasswordSuccess(false);
                }}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="profile-new-password">New password</Label>
              <Input
                id="profile-new-password"
                type="password"
                autoComplete="new-password"
                minLength={8}
                value={newPassword}
                disabled={passwordBusy}
                onChange={(event) => {
                  setNewPassword(event.target.value);
                  setPasswordMessage("");
                  setPasswordSuccess(false);
                }}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="profile-confirm-password">Confirm new password</Label>
              <Input
                id="profile-confirm-password"
                type="password"
                autoComplete="new-password"
                minLength={8}
                value={confirmPassword}
                disabled={passwordBusy}
                onChange={(event) => {
                  setConfirmPassword(event.target.value);
                  setPasswordMessage("");
                  setPasswordSuccess(false);
                }}
              />
            </div>
            <Button type="submit" variant="outline" disabled={passwordBusy}>
              {passwordBusy ? "Changing password…" : "Change password"}
            </Button>
            {passwordMessage ? (
              <p
                className={cn(
                  "text-sm",
                  passwordSuccess ? "text-muted-foreground" : "text-destructive",
                )}
                role={passwordSuccess ? "status" : "alert"}
              >
                {passwordMessage}
              </p>
            ) : null}
          </form>
        </section>

        {editing ? (
          <form className="space-y-8" onSubmit={onSave}>
            <section className="space-y-4">
              <h2 className="text-lg font-medium">Personal</h2>
              <Field label="Profile photo / company logo">
                <Input type="file" accept="image/*" onChange={(event) => onPhoto(event.target.files?.[0])} />
              </Field>
              <Field label="Full name">
                <Input value={profile.fullName} onChange={(event) => update("fullName", event.target.value)} />
              </Field>
              <Field label="Email">
                <Input type="email" value={profile.email} onChange={(event) => update("email", event.target.value)} />
              </Field>
              <Field label="Phone number">
                <Input value={profile.phone} onChange={(event) => update("phone", event.target.value)} />
              </Field>
              <Field label="WhatsApp number (optional)">
                <Input value={profile.whatsapp} onChange={(event) => update("whatsapp", event.target.value)} />
              </Field>
              <Field label="Location / City">
                <Input value={profile.city} onChange={(event) => update("city", event.target.value)} />
              </Field>
              <Field label="Bio / About">
                <textarea
                  className="min-h-24 w-full rounded-md border border-border bg-input px-3 py-2 text-sm"
                  value={profile.bio}
                  onChange={(event) => update("bio", event.target.value)}
                />
              </Field>
              <Field label="LinkedIn (optional)">
                <Input value={profile.linkedin} onChange={(event) => update("linkedin", event.target.value)} />
              </Field>
              <Field label="Instagram (optional)">
                <Input value={profile.instagram} onChange={(event) => update("instagram", event.target.value)} />
              </Field>
            </section>
            <section className="space-y-4">
              <h2 className="text-lg font-medium">Business</h2>
              <Field label="Business / Company name">
                <Input value={profile.companyName} onChange={(event) => update("companyName", event.target.value)} />
              </Field>
              <Field label="Role / Designation">
                <Input
                  placeholder="Founder, Owner, Manager"
                  value={profile.role}
                  onChange={(event) => update("role", event.target.value)}
                />
              </Field>
              <Field label="Business address (optional)">
                <textarea
                  className="min-h-20 w-full rounded-md border border-border bg-input px-3 py-2 text-sm"
                  value={profile.businessAddress}
                  onChange={(event) => update("businessAddress", event.target.value)}
                />
              </Field>
              <Field label="Website (optional)">
                <Input value={profile.website} onChange={(event) => update("website", event.target.value)} />
              </Field>
              <Field label="Business description">
                <textarea
                  className="min-h-24 w-full rounded-md border border-border bg-input px-3 py-2 text-sm"
                  value={profile.businessDescription}
                  onChange={(event) => update("businessDescription", event.target.value)}
                />
              </Field>
              <Field label="GSTIN / business registration (optional)">
                <Input value={profile.gstin} onChange={(event) => update("gstin", event.target.value)} />
              </Field>
            </section>
            <Button type="submit">Save profile</Button>
          </form>
        ) : null}
      </Container>
    </DashboardShell>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      {children}
    </div>
  );
}
