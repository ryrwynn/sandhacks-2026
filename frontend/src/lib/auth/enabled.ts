/** Sign-in is on only when a Google client ID and AUTH_SECRET are both set. Read at runtime, server side only. */
export const googleId = () => process.env.GOOGLE_CLIENT_ID || process.env.AUTH_GOOGLE_ID || "";
export const googleSecret = () => process.env.GOOGLE_CLIENT_SECRET || process.env.AUTH_GOOGLE_SECRET || "";
export const authEnabled = () => !!googleId() && !!process.env.AUTH_SECRET;
