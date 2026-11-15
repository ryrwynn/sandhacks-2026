import { connection } from "next/server";

/**
 * Mapbox public token (pk...), read at request time so a Docker image built without .env still works.
 * Returns null when missing or not a public token: pages then show a ranked list instead of a map.
 * Call only after (or instead of) awaiting connection(), inside a Suspense boundary.
 */
export async function mapboxToken(): Promise<string | null> {
  await connection();
  const t = process.env.MAP_BOX_API_KEY;
  return t && t.startsWith("pk.") ? t : null;
}
