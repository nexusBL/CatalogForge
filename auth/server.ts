import express from "express";
import { toNodeHandler } from "better-auth/node";
import { auth } from "./auth";

const app = express();
const port = Number(process.env.AUTH_PORT || "3005");

app.all("/api/auth/*", toNodeHandler(auth));
app.use(express.json());

app.listen(port, () => {
  console.log(`CatalogForge Better Auth listening on ${port}`);
});
