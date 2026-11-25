import Database from "better-sqlite3";
import { getMigrations } from "better-auth/db/migration";
import { auth } from "./auth";

/**
 * SQLite cannot ALTER TABLE to add a UNIQUE column, which is what
 * `npx auth migrate` / Better Auth compileMigrations() emits for username.
 * This applies the same schema using ADD COLUMN + a unique index, and
 * creates organization tables from the compiled Better Auth SQL.
 */
const { toBeAdded, toBeCreated } = await getMigrations(auth.options);
console.log("Creating tables:", toBeCreated.map((entry) => entry.table));
console.log(
  "Adding fields:",
  toBeAdded.map((entry) => `${entry.table}: ${Object.keys(entry.fields).join(", ")}`),
);

const sqlitePath = process.env.AUTH_SQLITE_PATH;
if (!sqlitePath) {
  throw new Error("AUTH_SQLITE_PATH is required");
}

const db = new Database(sqlitePath);

function tableExists(name: string): boolean {
  const row = db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name=?").get(name) as
    | { name: string }
    | undefined;
  return Boolean(row);
}

function columns(name: string): Set<string> {
  return new Set(
    (db.prepare(`PRAGMA table_info(${name})`).all() as Array<{ name: string }>).map((column) => column.name),
  );
}

function rowCount(name: string): number {
  if (!tableExists(name)) {
    return 0;
  }
  const row = db.prepare(`SELECT count(*) as n FROM ${name}`).get() as { n: number };
  return row.n;
}

db.exec("BEGIN");
try {
  if (tableExists("user")) {
    const userCols = columns("user");
    if (!userCols.has("username")) {
      db.exec("ALTER TABLE user ADD COLUMN username TEXT");
    }
    if (!userCols.has("displayUsername")) {
      db.exec("ALTER TABLE user ADD COLUMN displayUsername TEXT");
    }
    db.exec("CREATE UNIQUE INDEX IF NOT EXISTS user_username_unique ON user (username) WHERE username IS NOT NULL");
  }
  if (tableExists("session")) {
    const sessionCols = columns("session");
    if (!sessionCols.has("activeOrganizationId")) {
      db.exec("ALTER TABLE session ADD COLUMN activeOrganizationId TEXT");
    }
  }

  const orgEmpty = rowCount("organization") === 0 && rowCount("member") === 0 && rowCount("invitation") === 0;
  if (!tableExists("organization") || orgEmpty) {
    db.exec(`
      DROP TABLE IF EXISTS invitation;
      DROP TABLE IF EXISTS member;
      DROP TABLE IF EXISTS organization;
      CREATE TABLE organization (
        id TEXT NOT NULL PRIMARY KEY,
        name TEXT NOT NULL,
        slug TEXT NOT NULL UNIQUE,
        logo TEXT,
        createdAt date NOT NULL,
        metadata TEXT
      );
      CREATE TABLE member (
        id TEXT NOT NULL PRIMARY KEY,
        organizationId TEXT NOT NULL REFERENCES organization (id) ON DELETE CASCADE,
        userId TEXT NOT NULL REFERENCES user (id) ON DELETE CASCADE,
        role TEXT NOT NULL,
        createdAt date NOT NULL
      );
      CREATE TABLE invitation (
        id TEXT NOT NULL PRIMARY KEY,
        organizationId TEXT NOT NULL REFERENCES organization (id) ON DELETE CASCADE,
        email TEXT NOT NULL,
        role TEXT,
        status TEXT NOT NULL,
        expiresAt date NOT NULL,
        createdAt date NOT NULL,
        inviterId TEXT NOT NULL REFERENCES user (id) ON DELETE CASCADE
      );
      CREATE INDEX IF NOT EXISTS member_organizationId_idx ON member (organizationId);
      CREATE INDEX IF NOT EXISTS member_userId_idx ON member (userId);
      CREATE INDEX IF NOT EXISTS invitation_organizationId_idx ON invitation (organizationId);
      CREATE INDEX IF NOT EXISTS invitation_email_idx ON invitation (email);
    `);
  }
  db.exec("COMMIT");
  console.log("Better Auth migration complete.");
} catch (error) {
  db.exec("ROLLBACK");
  throw error;
}
