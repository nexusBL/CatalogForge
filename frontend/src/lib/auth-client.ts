import { emailOTPClient, organizationClient, usernameClient } from "better-auth/client/plugins";
import { createAuthClient } from "better-auth/react";

export const authClient = createAuthClient({
  // Same origin as the Next.js /api/auth proxy so the session cookie stays on the app host.
  fetchOptions: {
    credentials: "include",
  },
  plugins: [usernameClient(), emailOTPClient(), organizationClient()],
});
