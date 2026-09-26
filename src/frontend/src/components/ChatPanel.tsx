import { useEffect, useRef, useState, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useTrip } from "@/hooks/useTrip";
import { useTripStore } from "@/stores/tripStore";
import type { ItineraryDelta, Trip, TripChatWriteMode } from "@/lib/types";

interface ActivityEntry {
  id: string;
  text: string;
}

interface ChatMessage {
  id: string;
  role: "user" | "ai";
  content: string;
  suggestions?: ItineraryDelta[];
  activity?: ActivityEntry[];
  appliedCount?: number;
  streaming?: boolean;
}

interface ChatTurn {
  id: string;
  user: ChatMessage | null;
  ai: ChatMessage | null;
}

const ACTION_LABELS: Record<string, string> = {
  add: "新增地点",
  update: "修改地点",
  delete: "删除地点",
  move: "移动地点",
  reorder: "调整顺序",
  replace: "换成新地点",
  dismiss_visit_stop: "去掉计划外停留",
  reassign_photo: "改挂照片",
  unassign_photo: "拿掉照片归属",
  attach_visit_stop: "停留并进计划节点",
};

function isPhotoDelta(delta: ItineraryDelta): boolean {
  return (
    delta.action === "dismiss_visit_stop" ||
    delta.action === "reassign_photo" ||
    delta.action === "unassign_photo" ||
    delta.action === "attach_visit_stop"
  );
}


function composerPlaceholder(focusName: string | undefined, hasPhoto: boolean): string {
  if (hasPhoto) {
    return focusName?.trim()
      ? `例如：把这张照片改挂到${focusName.trim()} / 取消这张照片的归属`
      : "例如：把这张照片改挂到计划节点 / 取消这张照片的归属";
  }
  if (focusName?.trim()) {
    return `例如：删掉${focusName.trim()} / 这天会下雨吗`;
  }
  return "例如：删掉当前关注的点 / 这天会下雨吗";
}

function buildStarterPrompts(input: {
  dayNumber: number;
  dayCount: number;
  focusName?: string;
  hasPhoto: boolean;
}): string[] {
  const { dayNumber, dayCount, focusName, hasPhoto } = input;
  const poi = focusName?.trim();
  const moveTarget =
    dayCount > 1 ? (dayNumber < dayCount ? dayNumber + 1 : Math.max(1, dayNumber - 1)) : null;

  const prompts: string[] = [];
  if (poi) {
    prompts.push(`删掉${poi}`);
    prompts.push(`把${poi}换成…`);
    if (moveTarget != null) prompts.push(`把${poi}挪到第 ${moveTarget} 天`);
  } else {
    prompts.push("删掉当前关注的点");
    prompts.push("换成别的景点");
    if (moveTarget != null) prompts.push(`挪到第 ${moveTarget} 天`);
  }

  prompts.push(`Day${dayNumber} 会下雨吗`);
  prompts.push("按这段攻略加点：");

  if (hasPhoto) {
    if (poi) prompts.push(`把这张照片改挂到${poi}`);
    else prompts.push("把这张照片改挂到计划节点");
    prompts.push("取消这张照片的归属");
    prompts.push("去掉这个计划外停留");
  }

  const unique: string[] = [];
  for (const prompt of prompts) {
    if (!unique.includes(prompt)) unique.push(prompt);
  }
  return unique.slice(0, hasPhoto ? 6 : 5);
}

function deltaActionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action;
}

function deltaTargetText(delta: ItineraryDelta): string {
  const payload = delta.payload;
  const target = delta.target;
  const name = payload?.poi_name?.trim() || "该地点";
  const day = target?.day_index ?? "?";
  if (delta.action === "add") {
    return `${name} → Day${day} 第${target?.seq ?? "?"}位`;
  }
  if (delta.action === "delete") {
    return `${name}（Day${day}）`;
  }
  if (delta.action === "replace") {
    return `改为 ${name}（Day${day}）`;
  }
  if (delta.action === "move") {
    return `${name} → Day${day}`;
  }
  if (delta.action === "reorder") {
    return `Day${day} 共 ${payload?.item_ids?.length ?? 0} 个节点`;
  }
  if (delta.action === "update") {
    return `${name} 的时间/备注`;
  }
  return name;
}

function deltaImpact(delta: ItineraryDelta): string {
  if (isPhotoDelta(delta)) {
    return "只改照片归属或计划外停留，不会改行程计划。";
  }
  if (delta.action === "delete") {
    return "删除后当天节点数减少，后续时间会重新计算。";
  }
  if (delta.action === "add") {
    return `将插入 Day${delta.target?.day_index ?? "?"}，当天时间线会重新计算。`;
  }
  if (delta.action === "replace") {
    return "更换景点后，当天路线和时间会重新计算。";
  }
  if (delta.action === "reorder" || delta.action === "move") {
    return "排序变化后，交通时间和地图连线会更新。";
  }
  return "修改后地图和列表会同步刷新。";
}

function hasContrast(delta: ItineraryDelta): boolean {
  return Boolean(
    delta.preview_before &&
      delta.preview_after &&
      delta.preview_before !== delta.preview_after,
  );
}

function newId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function withActivity(message: ChatMessage, text: string): ChatMessage {
  const activity = message.activity ?? [];
  if (!text || activity.some((entry) => entry.text === text)) return message;
  return { ...message, activity: [...activity, { id: newId(), text }] };
}

function noteApplied(message: ChatMessage, applied: ItineraryDelta[]): ChatMessage {
  let next = message;
  for (const delta of applied) {
    next = withActivity(next, `已写入 ${deltaActionLabel(delta.action)} · ${deltaTargetText(delta)}`);
  }
  return {
    ...next,
    appliedCount: Math.max(next.appliedCount ?? 0, applied.length),
  };
}

function groupTurns(messages: ChatMessage[]): ChatTurn[] {
  const turns: ChatTurn[] = [];
  for (let index = 0; index < messages.length; index += 1) {
    const message = messages[index];
    if (message.role === "user") {
      const next = messages[index + 1];
      if (next?.role === "ai") {
        turns.push({ id: message.id, user: message, ai: next });
        index += 1;
      } else {
        turns.push({ id: message.id, user: message, ai: null });
      }
    } else {
      turns.push({ id: message.id, user: null, ai: message });
    }
  }
  return turns;
}

function renderInline(text: string) {
  const chunks = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return chunks.map((chunk, index) => {
    if (chunk.startsWith("**") && chunk.endsWith("**") && chunk.length > 4) {
      return (
        <strong key={index} className="font-semibold">
          {chunk.slice(2, -2)}
        </strong>
      );
    }
    if (chunk.startsWith("`") && chunk.endsWith("`") && chunk.length > 2) {
      return (
        <code key={index} className="rounded bg-chrome px-1 py-px font-mono text-[12px]">
          {chunk.slice(1, -1)}
        </code>
      );
    }
    return <span key={index}>{chunk}</span>;
  });
}

function ProseBlock({ text }: { text: string }) {
  const lines = text.split("\n");
  const listLines = lines.filter((line) => line.trim().length > 0);
  const isList = listLines.length > 0 && listLines.every((line) => /^[-*]\s+/.test(line.trim()));
  if (isList) {
    return (
      <ul className="list-disc space-y-1 pl-4">
        {listLines.map((line, index) => (
          <li key={index}>{renderInline(line.trim().replace(/^[-*]\s+/, ""))}</li>
        ))}
      </ul>
    );
  }
  return (
    <p className="whitespace-pre-wrap">
      {lines.map((line, index) => (
        <span key={index}>
          {index > 0 && <br />}
          {renderInline(line)}
        </span>
      ))}
    </p>
  );
}

function Prose({ text, streaming }: { text: string; streaming?: boolean }) {
  if (!text) return null;
  const segments = text.split(/```/);
  return (
    <div className="space-y-2 text-[13px] leading-5 text-ink">
      {segments.map((segment, index) => {
        if (index % 2 === 1) {
          return (
            <pre
              key={index}
              className="overflow-x-auto rounded-lg border border-line-tertiary bg-elevated px-3 py-2 font-mono text-[12px] leading-5 text-ink"
            >
              {segment.replace(/^\w+\n/, "")}
            </pre>
          );
        }
        const blocks = segment.split(/\n{2,}/).filter((block) => block.length > 0);
        return blocks.map((block, blockIndex) => (
          <ProseBlock key={`${index}-${blockIndex}`} text={block} />
        ));
      })}
      {streaming && (
        <span className="inline-block h-3 w-px animate-pulse bg-ink-tertiary align-middle" />
      )}
    </div>
  );
}

function Chevron({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 12 12" aria-hidden="true" className={`h-3 w-3 ${className}`}>
      <path
        d="M4.5 2.5 8 6 4.5 9.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function Spinner() {
  return (
    <span
      className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-r-transparent"
      aria-hidden="true"
    />
  );
}

function UserBubble({ content }: { content: string }) {
  const textRef = useRef<HTMLParagraphElement>(null);
  const [open, setOpen] = useState(false);
  const [canToggle, setCanToggle] = useState(false);
  const collapsed = canToggle && !open;

  useEffect(() => {
    const node = textRef.current;
    if (!node || open) return;
    setCanToggle(node.scrollHeight > node.clientHeight + 1);
  }, [content, open]);
  const body = (
    <>
      <p
        ref={textRef}
        className={`whitespace-pre-wrap pr-6 text-[13px] leading-[18px] text-ink ${
          collapsed || !open ? "max-h-[68px] overflow-hidden" : ""
        }`}
      >
        {content}
      </p>
      {collapsed && (
        <span className="pointer-events-none absolute inset-x-0 bottom-0 h-5 rounded-b-xl bg-gradient-to-t from-elevated to-transparent" />
      )}
      {canToggle && (
        <Chevron
          className={`absolute right-2 top-2 text-ink-tertiary transition-opacity ${
            open ? "rotate-90 opacity-60" : "opacity-0 group-hover:opacity-60"
          }`}
        />
      )}
    </>
  );
  const className =
    "group relative w-full rounded-xl border border-line-tertiary bg-elevated px-3 py-2 text-left";
  if (!canToggle) {
    return <div className={className}>{body}</div>;
  }
  return (
    <button
      type="button"
      onClick={() => setOpen((value) => !value)}
      aria-expanded={open}
      className={className}
    >
      {body}
    </button>
  );
}

function ActivityTrail({
  entries,
  streaming,
  appliedCount,
}: {
  entries: ActivityEntry[];
  streaming: boolean;
  appliedCount: number;
}) {
  const [open, setOpen] = useState(false);
  const wasStreaming = useRef(streaming);

  useEffect(() => {
    if (wasStreaming.current && !streaming) setOpen(false);
    wasStreaming.current = streaming;
  }, [streaming]);

  if (!streaming && entries.length === 0 && appliedCount === 0) return null;

  const label = streaming
    ? entries[entries.length - 1]?.text || "正在处理…"
    : appliedCount > 0
      ? `本次处理 · 已写入 ${appliedCount} 条`
      : "本次处理";

  return (
    <div className="mb-2">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="group flex w-full items-center gap-1.5 py-0.5 text-left text-[13px] leading-5 text-ink-secondary hover:text-ink"
      >
        <span className="flex h-3 w-3 shrink-0 items-center justify-center text-ink-tertiary">
          {streaming ? (
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
          ) : (
            <Chevron
              className={`transition ${open ? "rotate-90 opacity-60" : "opacity-0 group-hover:opacity-60"}`}
            />
          )}
        </span>
        <span className="truncate">{label}</span>
      </button>
      {open && (
        <ul className="mb-1 ml-[18px] space-y-0.5">
          {entries.map((entry) => (
            <li key={entry.id} className="truncate text-[12px] leading-5 text-ink-tertiary">
              {entry.text}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SuggestionCard({
  delta,
  status,
  onAccept,
  onIgnore,
}: {
  delta: ItineraryDelta;
  status?: "accepted" | "ignored" | "failed";
  onAccept: () => void;
  onIgnore: () => void;
}) {
  const [open, setOpen] = useState(false);
  const contrast = hasContrast(delta);
  const statusLabel =
    status === "accepted" ? "已采纳" : status === "failed" ? "采纳失败" : status === "ignored" ? "已忽略" : null;

  return (
    <div className="group rounded-lg border border-line-tertiary bg-elevated">
      <div className="flex items-center gap-1 px-1.5 py-1">
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
        >
          <Chevron
            className={`shrink-0 text-ink-tertiary transition ${
              open ? "rotate-90 opacity-60" : "opacity-0 group-hover:opacity-60"
            }`}
          />
          <span className="shrink-0 rounded bg-chrome px-1.5 py-0.5 text-[11px] leading-4 text-ink-secondary">
            {deltaActionLabel(delta.action)}
          </span>
          <span className="truncate text-[13px] leading-5 text-ink">{deltaTargetText(delta)}</span>
        </button>
        {statusLabel ? (
          <span
            className={`shrink-0 px-1 text-[12px] ${
              status === "accepted"
                ? "text-emerald-700"
                : status === "failed"
                  ? "text-red-600"
                  : "text-ink-tertiary"
            }`}
          >
            {statusLabel}
          </span>
        ) : (
          <div className="flex shrink-0 items-center">
            <button
              type="button"
              onClick={onAccept}
              className="rounded px-1.5 py-0.5 text-[12px] text-ink-secondary hover:bg-chrome hover:text-ink"
            >
              采纳
            </button>
            <button
              type="button"
              onClick={onIgnore}
              className="rounded px-1.5 py-0.5 text-[12px] text-ink-tertiary hover:bg-chrome hover:text-ink-secondary"
            >
              忽略
            </button>
          </div>
        )}
      </div>
      {open && (
        <div className="space-y-1 border-t border-line-tertiary px-3 py-2">
          {contrast && (
            <>
              <p className="text-[12px] leading-5 text-ink-tertiary">
                <span className="mr-1 text-ink-secondary">原</span>
                {delta.preview_before}
              </p>
              <p className="text-[12px] leading-5 text-ink">
                <span className="mr-1 text-ink-secondary">新</span>
                {delta.preview_after}
              </p>
            </>
          )}
          <p className="text-[12px] leading-5 text-ink-tertiary">{deltaImpact(delta)}</p>
        </div>
      )}
    </div>
  );
}

function TurnView({
  turn,
  handled,
  onAccept,
  onIgnore,
  onAcceptAll,
}: {
  turn: ChatTurn;
  handled: Record<string, "accepted" | "ignored" | "failed">;
  onAccept: (delta: ItineraryDelta, key: string) => void;
  onIgnore: (key: string) => void;
  onAcceptAll: (deltas: ItineraryDelta[], keys: string[]) => void;
}) {
  const suggestions = turn.ai?.suggestions ?? [];
  const keys = suggestions.map((delta, index) => delta.suggestion_id ?? `${turn.ai?.id}-s${index}`);
  const pending = keys.filter((key) => !handled[key]).length;

  return (
    <section className="border-b border-line-tertiary last:border-b-0">
      {turn.user && (
        <div className="sticky top-0 z-10 bg-chrome px-3 pb-1 pt-3">
          <UserBubble content={turn.user.content} />
          <div className="pointer-events-none -mx-3 mt-1 h-3 bg-gradient-to-b from-chrome to-transparent" />
        </div>
      )}
      {turn.ai && (
        <div className="px-3 pb-4">
          <ActivityTrail
            entries={turn.ai.activity ?? []}
            streaming={Boolean(turn.ai.streaming)}
            appliedCount={turn.ai.appliedCount ?? 0}
          />
          <Prose text={turn.ai.content} streaming={turn.ai.streaming} />
          {suggestions.length > 1 && pending > 0 && (
            <div className="mt-3 flex justify-end">
              <button
                type="button"
                onClick={() => onAcceptAll(suggestions, keys)}
                className="rounded px-1.5 py-0.5 text-[12px] text-ink-secondary hover:bg-elevated hover:text-ink"
              >
                全部采纳（{pending}）
              </button>
            </div>
          )}
          {suggestions.length > 0 && (
            <div className="mt-2 space-y-1.5">
              {suggestions.map((delta, index) => {
                const key = keys[index];
                return (
                  <SuggestionCard
                    key={key}
                    delta={delta}
                    status={handled[key]}
                    onAccept={() => onAccept(delta, key)}
                    onIgnore={() => onIgnore(key)}
                  />
                );
              })}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

async function streamTripChat(
  tripId: string,
  payload: {
    message: string;
    thread_id?: string;
    write_mode?: TripChatWriteMode;
    context?: { day_index?: number; item_id?: string; photo_id?: string };
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
  const { data: trip } = useTrip(tripId);
  const selectedDayIndex = useTripStore((s) => s.selectedDayIndex);
  const focusItemId = useTripStore((s) => s.focusItemId);
  const focusPhotoId = useTripStore((s) => s.focusPhotoId);
  const applyServerTrip = useTripStore((s) => s.applyServerTrip);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [threadId, setThreadId] = useState<string | undefined>(undefined);
  const [writeMode, setWriteMode] = useState<TripChatWriteMode>("propose");
  const [handled, setHandled] = useState<Record<string, "accepted" | "ignored" | "failed">>({});
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const stickToBottom = useRef(true);

  const focusName = trip?.days
    ?.flatMap((day) => day.items ?? [])
    .find((item) => item.id === focusItemId)?.poi_name;
  const contextLabel = `当前关注点：Day ${selectedDayIndex + 1}${focusName ? ` · ${focusName}` : ""}${focusPhotoId ? " · 已打开一张照片" : ""}`;
  const dayCount = trip?.days?.length ?? 0;
  const starterPrompts = useMemo(
    () =>
      buildStarterPrompts({
        dayNumber: selectedDayIndex + 1,
        dayCount,
        focusName,
        hasPhoto: Boolean(focusPhotoId),
      }),
    [selectedDayIndex, dayCount, focusName, focusPhotoId],
  );
  const inputPlaceholder = composerPlaceholder(focusName, Boolean(focusPhotoId));


  useEffect(() => {
    const el = scrollerRef.current;
    if (!el || !stickToBottom.current) return;
    el.scrollTop = el.scrollHeight;
  }, [messages]);

  useEffect(() => {
    let cancelled = false;
    setHistoryLoading(true);
    setMessages([]);
    setThreadId(undefined);
    setHandled({});
    stickToBottom.current = true;

    (async () => {
      try {
        const data = await api.get<{ thread_id: string; messages: { role: "user" | "ai"; content: string }[] }>(
          `/trips/${tripId}/chat/history`,
        );
        if (cancelled) return;
        setThreadId(data.thread_id || undefined);
        setMessages(
          (data.messages ?? []).map((row) => ({
            id: newId(),
            role: row.role === "ai" ? "ai" : "user",
            content: row.content,
          })),
        );
      } catch {
        if (!cancelled) {
          setMessages([]);
          setThreadId(undefined);
        }
      } finally {
        if (!cancelled) setHistoryLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [tripId]);

  async function refreshTrip() {
    const data = await api.get<Trip>(`/trips/${tripId}`);
    queryClient.setQueryData(["trip", tripId], data);
    applyServerTrip(data);
  }
  function refreshPhotos() {
    queryClient.invalidateQueries({ queryKey: ["trip-photos", tripId] });
    queryClient.invalidateQueries({ queryKey: ["trip-photo-summary", tripId] });
    queryClient.invalidateQueries({ queryKey: ["trip-visit-stops", tripId] });
  }

  async function refreshAll() {
    await refreshTrip();
    refreshPhotos();
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

  function patchAi(aiMessageId: string, updater: (message: ChatMessage) => ChatMessage) {
    setMessages((prev) => prev.map((message) => (message.id === aiMessageId ? updater(message) : message)));
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;

    const userMessage: ChatMessage = { id: newId(), role: "user", content: text };
    const aiMessageId = newId();
    const aiMessage: ChatMessage = {
      id: aiMessageId,
      role: "ai",
      content: "",
      suggestions: [],
      activity: [{ id: newId(), text: "AI 正在思考…" }],
      appliedCount: 0,
      streaming: true,
    };
    stickToBottom.current = true;
    setMessages((prev) => [...prev, userMessage, aiMessage]);
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
            photo_id: focusPhotoId ?? undefined,
          },
        },
        (event, data) => {
          if (event === "status") {
            const message = String(data.message ?? "");
            if (message) patchAi(aiMessageId, (current) => withActivity(current, message));
          } else if (event === "delta") {
            const chunk = String(data.text ?? "");
            patchAi(aiMessageId, (current) => ({ ...current, content: current.content + chunk }));
          } else if (event === "applied") {
            const applied = (data.deltas as ItineraryDelta[]) ?? [];
            void refreshAll().catch(() => undefined);
            markDeltasAccepted(applied, aiMessageId);
            patchAi(aiMessageId, (current) => noteApplied(current, applied));
          } else if (event === "done") {
            const applied = (data.applied as ItineraryDelta[]) ?? [];
            setThreadId(String(data.thread_id ?? ""));
            patchAi(aiMessageId, (current) =>
              noteApplied(
                {
                  ...current,
                  streaming: false,
                  content: current.content || String(data.reply ?? ""),
                  suggestions: (data.suggestions as ItineraryDelta[]) ?? [],
                },
                applied,
              ),
            );
            if (applied.length > 0) {
              void refreshAll().catch(() => undefined);
              markDeltasAccepted(applied, aiMessageId);
            }
          }
        },
      );
    } catch {
      patchAi(aiMessageId, (current) => ({
        ...current,
        streaming: false,
        content: current.content || "抱歉，AI 对话暂时不可用，请稍后再试。",
      }));
    } finally {
      patchAi(aiMessageId, (current) => ({ ...current, streaming: false }));
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
      refreshPhotos();
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
        refreshPhotos();
      } catch {
        setHandled((prev) => ({ ...prev, [key]: "failed" }));
      }
    }
  }

  function handleIgnore(key: string) {
    setHandled((prev) => ({ ...prev, [key]: "ignored" }));
  }

  const turns = groupTurns(messages);

  return (
    <aside
      aria-busy={loading || historyLoading}
      className="flex h-[70vh] min-h-[28rem] max-h-[70vh] w-full flex-col overflow-hidden rounded-lg border border-line-tertiary bg-chrome shadow-sm lg:h-[calc(100dvh-10.5rem)] lg:max-h-[calc(100dvh-2rem)] lg:min-h-[26rem]"
    >
      <header className="flex items-center justify-between gap-3 border-b border-line-tertiary px-3 py-2.5">
        <h2 className="shrink-0 text-[13px] font-semibold text-ink">AI 行程协作</h2>
        <p className="min-w-0 truncate text-right text-[12px] text-ink-tertiary" title={contextLabel}>
          {contextLabel}
        </p>
      </header>

      <div
        ref={scrollerRef}
        onScroll={() => {
          const el = scrollerRef.current;
          if (!el) return;
          stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
        }}
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain"
      >
        {historyLoading ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-3 py-4 text-[12px] text-ink-tertiary">
            <Spinner />
            <span>加载对话记录…</span>
          </div>
        ) : turns.length === 0 ? (

          <div className="flex h-full flex-col justify-center px-3 py-4">
            <p className="mb-2 text-[12px] text-ink-tertiary">可以这样说</p>
            <div className="flex flex-col items-start gap-1.5">
              {starterPrompts.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => {
                    setInput(prompt);
                    inputRef.current?.focus();
                  }}
                  className="max-w-full truncate rounded-lg border border-line-tertiary bg-elevated px-2.5 py-1.5 text-left text-[13px] text-ink-secondary hover:text-ink"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : (
          turns.map((turn) => (
            <TurnView
              key={turn.id}
              turn={turn}
              handled={handled}
              onAccept={(delta, key) => void handleAccept(delta, key)}
              onIgnore={handleIgnore}
              onAcceptAll={(deltas, keys) => void handleAcceptAll(deltas, keys)}
            />
          ))
        )}
      </div>

      <footer className="sticky bottom-0 z-20 border-t border-line-tertiary bg-chrome px-3 pb-3 pt-2">
        <div className="rounded-xl border border-line-tertiary bg-elevated shadow-sm focus-within:border-[rgb(20_20_20/0.16)]">
          <textarea
            ref={inputRef}
            value={input}
            rows={2}
            disabled={loading || historyLoading}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                void handleSend();
              }
            }}
            placeholder={inputPlaceholder}
            className="chat-composer-input w-full resize-none bg-transparent px-3 pt-3 text-[13px] leading-5 text-ink outline-none placeholder:text-ink-tertiary disabled:cursor-not-allowed disabled:opacity-60"
          />
          <div className="flex items-center justify-between gap-2 px-2 pb-1">
            <div
              className="inline-flex max-w-full rounded-md bg-chrome p-0.5"
              role="group"
              aria-label="写库模式"
            >
              <button
                type="button"
                onClick={() => setWriteMode("propose")}
                disabled={loading || historyLoading}
                className={`rounded px-2 py-1 text-[11px] ${
                  writeMode === "propose"
                    ? "bg-elevated font-medium text-ink shadow-sm"
                    : "text-ink-tertiary hover:text-ink-secondary"
                }`}
              >
                只提议
              </button>
              <button
                type="button"
                onClick={() => setWriteMode("auto_apply")}
                disabled={loading || historyLoading}
                className={`rounded px-2 py-1 text-[11px] ${
                  writeMode === "auto_apply"
                    ? "bg-elevated font-medium text-ink shadow-sm"
                    : "text-ink-tertiary hover:text-ink-secondary"
                }`}
              >
                授权后自动采纳
              </button>
            </div>
            <button
              type="button"
              onClick={() => void handleSend()}
              disabled={loading || historyLoading || !input.trim()}
              className="inline-flex h-7 shrink-0 items-center justify-center gap-1 rounded-md bg-ink px-2.5 text-[12px] text-elevated disabled:opacity-40"
            >
              {loading ? <Spinner /> : "发送"}
            </button>
          </div>
          <p className="flex items-center justify-between gap-2 px-2.5 pb-2 text-[11px] text-ink-tertiary">
            <span className="truncate">
              {writeMode === "propose" ? "改行程或照片需你点采纳" : "本会话允许助手直接改行程和照片"}
            </span>
            <span className="shrink-0">Enter 发送</span>
          </p>
        </div>
      </footer>
    </aside>
  );
}
