import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import { googleId, googleSecret } from "./enabled";

/**
 * Auth.js with basePath "/auth" (the next-auth default is "/api/auth", which Caddy sends to FastAPI),
 * JWT sessions, and Google only. Nothing but the Google subject ID is kept: the profile, the token and
 * the session are stripped of email, name and picture.
 * Built lazily, so with sign-in off nothing here runs.
 */
function make() {
  return NextAuth({
    basePath: "/auth",
    trustHost: true,
    session: { strategy: "jwt" },
    providers: [
      Google({
        clientId: googleId(),
        clientSecret: googleSecret(),
        profile: (p) => ({ id: p.sub }),
      }),
    ],
    callbacks: {
      jwt: ({ token }) => ({ sub: token.sub }),
      session: ({ session }) => ({ expires: session.expires, user: {} }) as typeof session,
    },
  });
}

let instance: ReturnType<typeof make> | null = null;
export const getAuth = () => (instance ??= make());
