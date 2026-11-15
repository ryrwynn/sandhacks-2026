// Typed browser client for the advisor route, for night-web's page. The route is /advisor/chat (not /api).
// For a streaming chat UI use useChat with `new DefaultChatTransport({ api: ADVISOR_CHAT_PATH })`.
export const ADVISOR_CHAT_PATH = "/advisor/chat";

export type AdvisorAnswer = {
  answer: string;
  steps: number;            // model steps used, at most 4
  ungrounded: string[];     // figures in the answer that no tool result supports (should be empty)
  cached: boolean;
};

export async function askAdvisor(text: string, signal?: AbortSignal): Promise<AdvisorAnswer> {
  const res = await fetch(ADVISOR_CHAT_PATH, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ text }),
    signal,
  });
  if (!res.ok) throw new Error(`The advisor answered ${res.status}`);
  return (await res.json()) as AdvisorAnswer;
}
