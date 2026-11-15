/** Sign-in is on only when SIGN_IN_ENABLED=1 and a Google client ID and AUTH_SECRET are set. Read at runtime,
 *  server side only. Switched off for the demo (2026-11-15) until Google sign-in is fixed: set SIGN_IN_ENABLED=1 to
 *  turn it back on. Off, /auth/session answers {"enabled": false} and no account button renders. */
export const googleId = () => process.env.GOOGLE_CLIENT_ID || process.env.AUTH_GOOGLE_ID || "";
export const googleSecret = () => process.env.GOOGLE_CLIENT_SECRET || process.env.AUTH_GOOGLE_SECRET || "";
export const authEnabled = () =>
  process.env.SIGN_IN_ENABLED === "1" && !!googleId() && !!process.env.AUTH_SECRET;
