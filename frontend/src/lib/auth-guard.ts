export function isAuthenticatedSession(session: unknown): boolean {
  if (!session || typeof session !== "object") {
    return false;
  }
  const user = (session as { user?: { id?: string } }).user;
  return Boolean(user?.id);
}
