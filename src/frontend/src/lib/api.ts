// API client - calls FastAPI backend
const BASE_URL = "/api/v1";

function isFormData(body: unknown): body is FormData {
  return typeof FormData !== "undefined" && body instanceof FormData;
}

function formatApiError(status: number, raw: string): string {
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
    if (Array.isArray(parsed.detail)) {
      return parsed.detail
        .map((row) =>
          typeof row === "object" && row && "msg" in row
            ? String((row as { msg: unknown }).msg)
            : JSON.stringify(row),
        )
        .join("; ");
    }
  } catch {
    // keep raw text
  }
  return raw || `API error: ${status}`;
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers);
  const isForm = isFormData(options?.body);
  if (isForm) {
    headers.delete("Content-Type");
  } else if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${BASE_URL}${url}`, {
    ...options,
    headers,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(formatApiError(response.status, detail));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json();
}

export const api = {
  get: <T>(url: string) => request<T>(url),
  post: <T>(url: string, body: unknown) =>
    request<T>(url, { method: "POST", body: JSON.stringify(body) }),
  patch: <T>(url: string, body: unknown) =>
    request<T>(url, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(url: string) => request<T>(url, { method: "DELETE" }),
  upload: <T>(url: string, body: FormData) =>
    request<T>(url, { method: "POST", body }),
};
