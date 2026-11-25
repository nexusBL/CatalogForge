"use client";

import { ExitIcon, GearIcon, PersonIcon } from "@radix-ui/react-icons";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { authClient } from "@/lib/auth-client";
import { loadAccountProfile } from "@/lib/account-profile";
import { cn } from "@/lib/utils";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export function profileLabel(user: { name?: string | null; username?: string | null; email?: string | null } | null | undefined): string {
  return user?.name?.trim() || user?.username?.trim() || user?.email?.trim() || "Account";
}

export function profileInitials(label: string): string {
  const parts = label.split(/[\s@._-]+/).filter(Boolean);
  if (!parts.length) {
    return "U";
  }
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase() || "").join("");
}

export function ProfileMenu({ collapsed = false }: { collapsed?: boolean }) {
  const router = useRouter();
  const { data: session } = authClient.useSession();
  const user = session?.user as { id?: string; name?: string | null; username?: string | null; email?: string | null; image?: string | null } | undefined;
  const [storedName, setStoredName] = useState("");
  const [storedPhoto, setStoredPhoto] = useState("");
  const label = storedName || profileLabel(user);
  const initials = profileInitials(label);
  const photo = storedPhoto || user?.image || "";

  useEffect(() => {
    const stored = loadAccountProfile(user?.id);
    setStoredName(stored.fullName.trim());
    setStoredPhoto(stored.photoDataUrl);
  }, [user?.id]);

  async function signOut() {
    await authClient.signOut();
    router.replace("/");
  }

  const trigger = (
    <button
      type="button"
      className={cn(
        "flex w-full items-center rounded-md px-2 py-1.5 text-left hover:bg-selected",
        collapsed ? "justify-center" : "gap-2",
      )}
      aria-label="Account menu"
    >
      {photo ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={photo} alt="" className="h-7 w-7 rounded-full object-cover" />
      ) : (
        <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-selected text-xs font-medium">
          {initials}
        </span>
      )}
      {collapsed ? <PersonIcon className="sr-only" /> : (
        <span className="min-w-0 truncate text-sm">{label}</span>
      )}
    </button>
  );

  return (
    <DropdownMenu>
      <Tooltip delayDuration={200}>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>{trigger}</DropdownMenuTrigger>
        </TooltipTrigger>
        {collapsed ? <TooltipContent side="right">{label}</TooltipContent> : null}
      </Tooltip>
      <DropdownMenuContent side="top" align={collapsed ? "center" : "start"} className="w-48">
        <DropdownMenuItem asChild>
          <Link href="/profile" className="flex items-center gap-2">
            <PersonIcon /> Profile
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/settings" className="flex items-center gap-2">
            <GearIcon /> Settings
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => void signOut()} className="flex items-center gap-2">
          <ExitIcon /> Logout
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
