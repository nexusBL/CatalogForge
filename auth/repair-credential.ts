import { auth } from "./auth";

const username = (process.argv[2] || "bharathl").trim().toLowerCase();
const password = process.argv[3];

if (!password || password.length < 8) {
  console.error("Usage: npx tsx --env-file=.env repair-credential.ts [username] <password>");
  process.exit(1);
}

const ctx = await auth.$context;
const user = await ctx.adapter.findOne({
  model: "user",
  where: [{ field: "username", value: username }],
});

if (!user) {
  console.error(`User not found: ${username}`);
  process.exit(1);
}

const existing = await ctx.adapter.findOne({
  model: "account",
  where: [
    { field: "userId", value: user.id },
    { field: "providerId", value: "credential" },
  ],
});

const hash = await ctx.password.hash(password);

if (existing) {
  await ctx.internalAdapter.updatePassword(user.id, hash);
  console.log(`Password updated for ${username}`);
} else {
  await ctx.internalAdapter.linkAccount({
    userId: user.id,
    providerId: "credential",
    accountId: user.id,
    password: hash,
  });
  console.log(`Password credential linked for ${username}`);
}
