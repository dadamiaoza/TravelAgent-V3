import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useTripStore } from "@/stores/tripStore";
import type { ItineraryDelta, Trip, TripChatWriteMode } from "@/lib/types";

interface ChatMessage {
  id: string;
  role: "user" | "ai";
  content: string;
  suggestions?: ItineraryDelta[];
}

const ACTION_LABELS: Record<string, string> = {
  add: "新增地点",
  update: "修改地点",
  delete: "删除地点",
  move: "移动地点",
  reorder: "调整顺序",
};

function deltaSummary(delta: ItineraryDelta): string {
  const action = ACTION_LABELS[delta.action] ?? delta.action;
  const target = delta.target;
  const payload = delta.payload;
  if (delta.action === "add") {
    return `${action}：${payload?.poi_name ?? "新地点"} → Day${target?.day_index ?? "?"} 第${target?.seq ?? "?"}位`;
  }
  if (delta.action === "delete") {
    return `${action}：${payload?.poi_name ?? "该地点"}（Day${target?.day_index ?? "?"}）`;
  }
  if (delta.action === "reorder") {
    return `${action}：Day${target?.day_index ?? "?"} 共 ${payload?.item_ids?.length ?? 0} 个节点`;
  }
  if (delta.action === "update") {
    return `${action}：${payload?.poi_name ?? "地点"} 的时间/备注`;
  }
  return action;
}

function deltaImpact(delta: ItineraryDelta): string {
  if (delta.action === "delete") {
    return "删除后当天节点数减少，后续时间会重新计算。";
  }
  if (delta.action === "add") {
    return `将插入 Day${delta.target?.day_index ?? "?"}，当天时间线会重新计算。`;
  }
  if (delta.action === "reorder" || delta.action === "move") {
    return "排序变化后，交通时间和地图连线会更新。";
  }
  return "修改后地图和列表会同步刷新。";
}

function newId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

async function streamTripChat(
  tripId: string,
  payload: {
    message: string;
    thread_id?: string;
    write_mode?: TripChatWriteMode;
    context?: { day_index?: number; item_id?: string };
  },
  onEvent: (event: string, data: Record<string, unknown>) => void,
) {
  const response = await fetch(`/api/v1/trips/${tripId}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok || !response.body) {
    throw new Error(`Chat stream failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);

      let event = "message";
      const dataLines: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) {
          event = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          dataLines.push(line.slice(5).trim());
        }
      }
      if (dataLines.length > 0) {
        onEvent(event, JSON.parse(dataLines.join("\n")));
      }
    }
  }
}

export default function ChatPanel({ tripId }: { tripId: string }) {
  const queryClient = useQueryClient();
  const selectedDayIndex = useTripStore((s) => s.selectedDayIndex);
  const focusItemId = useTripStore((s) => s.focusItemId);
  const applyServerTrip = useTripStore((s) => s.applyServerTrip);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [threadId, setThreadId] = useState<string | undefined>(undefined);
  const [writeMode, setWriteMode] = useState<TripChatWriteMode>("propose");
  const [handled, setHandled] = useState<Record<string, "accepted" | "ignored" | "failed">>({});
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  async function refreshTrip() {
    const data = await api.get<Trip>(`/trips/${tripId}`);
    queryClient.setQueryData(["trip", tripId], data);
    applyServerTrip(data);
  }

  function markDeltasAccepted(deltas: ItineraryDelta[], messageId: string) {
    setHandled((prev) => {
      const next = { ...prev };
      deltas.forEach((delta, idx) => {
        const key = delta.suggestion_id ?? `${messageId}-a${idx}`;
        next[key] = "accepted";
      });
      return next;
    });
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;

    setMessages((prev) => [...prev, { id: newId(), role: "user", content: text }]);
    const aiMessageId = newId();
    setMessages((prev) => [...prev, { id: aiMessageId, role: "ai", content: "", suggestions: [] }]);
    setInput("");
    setLoading(true);

    try {
      await streamTripChat(
        tripId,
        {
          message: text,
          thread_id: threadId,
          write_mode: writeMode,
          context: {
            day_index: selectedDayIndex + 1,
            item_id: focusItemId ?? undefined,
          },
        },
        (event, data) => {
          if (event === "delta") {
            const chunk = String(data.text ?? "");
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === aiMessageId ? { ...msg, content: msg.content + chunk } : msg,
              ),
            );
          } else if (event === "applied") {
            const applied = (data.deltas as ItineraryDelta[]) ?? [];
            void refreshTrip().catch(() => undefined);
            markDeltasAccepted(applied, aiMessageId);
          } else if (event === "done") {
            setThreadId(String(data.thread_id ?? ""));
            const applied = (data.applied as ItineraryDelta[]) ?? [];
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === aiMessageId
                  ? { ...msg, suggestions: (data.suggestions as ItineraryDelta[]) ?? [] }
                  : msg,
              ),
            );
            if (applied.length > 0) {
              void refreshTrip().catch(() => undefined);
              markDeltasAccepted(applied, aiMessageId);
            }
          }
        },
      );
    } catch {
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === aiMessageId
            ? { ...msg, content: "抱歉，AI 对话暂时不可用，请稍后再试。" }
            : msg,
        ),
      );
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  async function handleAccept(delta: ItineraryDelta, key: string) {
    setHandled((prev) => ({ ...prev, [key]: "accepted" }));
    try {
      const data = await api.post<Trip>(`/trips/${tripId}/deltas/apply`, { delta });
      queryClient.setQueryData(["trip", tripId], data);
      applyServerTrip(data);
    } catch {
      setHandled((prev) => ({ ...prev, [key]: "failed" }));
    }
  }

  async function handleAcceptAll(deltas: ItineraryDelta[], keys: string[]) {
    for (let i = 0; i < deltas.length; i++) {
      const delta = deltas[i];
      const key = keys[i];
      if (handled[key]) continue;
      setHandled((prev) => ({ ...prev, [key]: "accepted" }));
      try {
        const data = await api.post<Trip>(`/trips/${tripId}/deltas/apply`, { delta });
        queryClient.setQueryData(["trip", tripId], data);
        applyServerTrip(data);
      } catch {
        setHandled((prev) => ({ ...prev, [key]: "failed" }));
      }
    }
  }

  function handleIgnore(_delta: ItineraryDelta, key: string) {
    setHandled((prev) => ({ ...prev, [key]: "ignored" }));
  }

  return (
    <aside className="flex h-[70vh] min-h-[500px] max-h-[70vh] flex-col rounded-lg border border-gray-200 bg-white shadow-sm">
      <div className="flex items-start justify-between gap-3 border-b border-gray-100 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-gray-900">AI 行程协作</h2>
          <p className="mt-0.5 text-xs text-gray-500">当前上下文：Day {selectedDayIndex + 1}</p>
        </div>
        <div className="shrink-0 text-right">
          <div
            className="inline-flex rounded-md border border-gray-200 bg-gray-50 p-0.5"
            role="group"
            aria-label="写库模式"
          >
            <button
              type="button"
              onClick={() => setWriteMode("propose")}
              className={`rounded px-2 py-1 text-xs ${
                writeMode === "propose"
                  ? "bg-white font-medium text-gray-900 shadow-sm"
                  : "text-gray-500 hover:text-gray-800"
              }`}
            >
              只提议
            </button>
            <button
              type="button"
              onClick={() => setWriteMode("auto_apply")}
              className={`rounded px-2 py-1 text-xs ${
                writeMode === "auto_apply"
                  ? "bg-white font-medium text-gray-900 shadow-sm"
                  : "text-gray-500 hover:text-gray-800"
              }`}
            >
              授权后自动采纳
            </button>
          </div>
          <p className="mt-1 text-[11px] text-gray-400">
            {writeMode === "propose" ? "改行程需你点采纳" : "本会话允许助手直接改行程"}
          </p>
        </div>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && (
          <div className="text-center text-sm text-gray-400">
            试试对我说：“把第三天改轻松一点”
          </div>
        )}
        {messages.map((msg) => (
          <div key={msg.id}>
            <div
              className={`rounded-lg px-3 py-2 text-sm ${
                msg.role === "user"
                  ? "ml-auto max-w-[80%] bg-blue-600 text-white"
                  : "max-w-[90%] bg-gray-100 text-gray-800"
              }`}
            >
              {msg.content}
            </div>
            {msg.suggestions && msg.suggestions.length > 1 && (() => {
              const keys = msg.suggestions.map(
                (delta, idx) => delta.suggestion_id ?? `${msg.id}-s${idx}`,
              );
              const pending = keys.filter((key) => !handled[key]).length;
              if (pending === 0) return null;
              return (
                <button
                  type="button"
                  onClick={() => handleAcceptAll(msg.suggestions!, keys)}
                  className="mt-2 rounded border border-blue-300 px-2 py-1 text-xs text-blue-600 hover:bg-blue-50"
                >
                  全部采纳（{pending}）
                </button>
              );
            })()}
            {msg.suggestions && msg.suggestions.length > 0 && (
              <div className="mt-2 space-y-2">
                {msg.suggestions.map((delta, idx) => {
                  const key = delta.suggestion_id ?? `${msg.id}-s${idx}`;
                  const status = handled[key];
                  if (status) {
                    const label =
                      status === "accepted"
                        ? "✅ 已采纳"
                        : status === "failed"
                          ? "❌ 采纳失败"
                          : "已忽略";
                    return (
                      <p key={key} className="text-xs text-gray-400">
                        {label} · {deltaSummary(delta)}
                      </p>
                    );
                  }
                  return (
                    <div key={key} className="rounded-md border border-orange-200 bg-orange-50 p-3">
                      <p className="text-xs font-semibold text-orange-800">{deltaSummary(delta)}</p>
                      <p className="mt-1 text-xs text-orange-700">{deltaImpact(delta)}</p>
                      <div className="mt-2 flex gap-2">
                        <button
                          type="button"
                          onClick={() => handleAccept(delta, key)}
                          className="rounded bg-blue-600 px-2 py-1 text-xs text-white"
                        >
                          采纳
                        </button>
                        <button
                          type="button"
                          onClick={() => handleIgnore(delta, key)}
                          className="rounded bg-gray-200 px-2 py-1 text-xs text-gray-700"
                        >
                          忽略
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ))}
        {loading && <p className="text-xs text-gray-400">AI 正在思考…</p>}
      </div>

      <div className="border-t border-gray-100 p-3">
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void handleSend();
            }
          }}
          rows={2}
          placeholder="例如：把第三天改轻松一点"
          className="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
        />
        <button
          type="button"
          onClick={() => void handleSend()}
          disabled={loading || !input.trim()}
          className="mt-2 w-full rounded bg-blue-600 px-3 py-2 text-sm text-white disabled:opacity-50"
        >
          {loading ? "发送中…" : "发送"}
        </button>
      </div>
    </aside>
  );
}