import { TopNav } from "@/components/nav";

export function DashboardShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <>
      <TopNav title={title} />
      <main>{children}</main>
    </>
  );
}
