import { createHash } from "node:crypto";

/** What the API sees as the user: sha256 hex of (AUTH_SECRET + Google subject ID). Never the subject itself. */
export function subjectHash(sub: string): string {
  return createHash("sha256").update((process.env.AUTH_SECRET ?? "") + sub).digest("hex");
}
