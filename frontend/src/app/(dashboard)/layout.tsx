import { AuthGate } from "@/components/auth-gate";
import { OrganizationGate } from "@/components/organization-gate";
import { SideNav } from "@/components/nav";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthGate>
      <OrganizationGate>
        <div className="flex min-h-[100dvh]">
          <SideNav />
          <div className="flex-grow overflow-auto bg-background">{children}</div>
        </div>
      </OrganizationGate>
    </AuthGate>
  );
}
