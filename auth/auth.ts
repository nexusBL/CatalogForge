import { APIError, betterAuth } from "better-auth";
import { createAuthMiddleware } from "better-auth/api";
import { emailOTP, organization, username } from "better-auth/plugins";
import Database from "better-sqlite3";
import nodemailer from "nodemailer";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const authDir = findAuthDir();
loadEnvFile(path.join(authDir, ".env"));
const sqlitePath = process.env.AUTH_SQLITE_PATH || path.join(authDir, "data", "better-auth.sqlite");
fs.mkdirSync(path.dirname(sqlitePath), { recursive: true });

function findAuthDir(): string {
  const starts = [process.cwd(), path.join(process.cwd(), "auth")];
  try {
    starts.unshift(path.dirname(fileURLToPath(import.meta.url)));
  } catch {
    // import.meta.url is unavailable in some CLI loaders
  }
  for (const start of starts) {
    let dir = path.resolve(start);
    for (let i = 0; i < 12; i++) {
      const packageFile = path.join(dir, "package.json");
      if (fs.existsSync(packageFile)) {
        try {
          const pkg = JSON.parse(fs.readFileSync(packageFile, "utf8")) as { name?: string };
          if (pkg.name === "catalogforge-auth") {
            return dir;
          }
        } catch {
          // keep walking
        }
      }
      const parent = path.dirname(dir);
      if (parent === dir) {
        break;
      }
      dir = parent;
    }
  }
  return process.cwd();
}

function loadEnvFile(filePath: string): void {
  if (!fs.existsSync(filePath)) {
    return;
  }
  const text = fs.readFileSync(filePath, "utf8").replace(/^\uFEFF/, "");
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) {
      continue;
    }
    const assignment = line.startsWith("export ") ? line.slice(7).trim() : line;
    const eq = assignment.indexOf("=");
    if (eq <= 0) {
      continue;
    }
    const key = assignment.slice(0, eq).trim();
    let value = assignment.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    if (!process.env[key]) {
      process.env[key] = value;
    }
  }
}

function requireSecret(): string {
  const secret = process.env.BETTER_AUTH_SECRET;
  if (!secret || secret.length < 32) {
    throw new Error("BETTER_AUTH_SECRET must be set to at least 32 characters");
  }
  return secret;
}

function sendOtpEmail(email: string, otp: string, type: string): void {
  const host = process.env.SMTP_HOST;
  if (host) {
    const transporter = nodemailer.createTransport({
      host,
      port: Number(process.env.SMTP_PORT || "587"),
      secure: process.env.SMTP_SECURE === "true",
      auth:
        process.env.SMTP_USER && process.env.SMTP_PASSWORD
          ? { user: process.env.SMTP_USER, pass: process.env.SMTP_PASSWORD }
          : undefined,
    });
    void transporter
      .sendMail({
        from: process.env.SMTP_FROM || process.env.SMTP_USER,
        to: email,
        subject: "Hecto Baba sign-in code",
        text: `Your Hecto Baba ${type} code is ${otp}`,
      })
      .catch((error) => {
        console.error("Failed to send OTP email", error);
      });
    return;
  }
  if (process.env.AUTH_OTP_LOG === "true") {
    console.info(`[auth] OTP for ${email} type=${type}: ${otp}`);
    return;
  }
  throw new Error("Email delivery is not configured. Set SMTP_HOST or AUTH_OTP_LOG=true for local development.");
}

export const auth = betterAuth({
  secret: requireSecret(),
  baseURL: process.env.BETTER_AUTH_URL || "http://localhost:3001",
  trustedOrigins: (process.env.BETTER_AUTH_TRUSTED_ORIGINS || "http://localhost:8000,http://localhost:3005,http://localhost:3001,http://localhost:3000")
    .split(",")
    .map((origin) => origin.trim())
    .filter(Boolean),
  database: new Database(sqlitePath),
  emailAndPassword: {
    enabled: true,
  },
  advanced: {
    defaultCookieAttributes: {
      path: "/",
      sameSite: "lax",
      httpOnly: true,
    },
  },
  hooks: {
    before: createAuthMiddleware(async (ctx) => {
      if (ctx.path !== "/sign-up/email") {
        return;
      }
      const body = ctx.body as { username?: unknown } | undefined;
      if (typeof body?.username !== "string" || !body.username.trim()) {
        throw new APIError("BAD_REQUEST", { message: "Username is required" });
      }
    }),
  },
  plugins: [
    username({
      minUsernameLength: 3,
      maxUsernameLength: 30,
    }),
    emailOTP({
      async sendVerificationOTP({ email, otp, type }) {
        sendOtpEmail(email, otp, type);
      },
    }),
    organization(),
  ],
});
