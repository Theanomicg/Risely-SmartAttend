export const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";
export const DEFAULT_CLASS_ID =
  import.meta.env.VITE_CLASS_ID ?? import.meta.env.VITE_CLASSROOM_ID ?? "class-10-a";
export const TEACHER_TOKEN = import.meta.env.VITE_TEACHER_TOKEN ?? "";
export const ADMIN_TOKEN = import.meta.env.VITE_ADMIN_TOKEN ?? "";

function getApiUrl() {
  return new URL(API_BASE, window.location.origin);
}

function buildHeaders(role, headers = {}) {
  const token = role === "admin" ? ADMIN_TOKEN : TEACHER_TOKEN || ADMIN_TOKEN;
  const nextHeaders = new Headers(headers);
  if (token) {
    nextHeaders.set("x-smartattend-token", token);
  }
  return nextHeaders;
}

export async function fetchJson(path, options = {}) {
  const { role = "teacher", headers, ...requestInit } = options;
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...requestInit,
      headers: buildHeaders(role, headers)
    });
  } catch {
    throw new Error("Failed to reach the backend. Check that the API is running.");
  }

  if (!response.ok) {
    const text = await response.text();
    let message = text || "Request failed.";
    if (text) {
      try {
        const payload = JSON.parse(text);
        message = payload.detail ?? payload.message ?? message;
      } catch {
        message = text;
      }
    }
    throw new Error(message);
  }

  return response.json();
}

export async function fetchPublicJson(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, options);
  } catch {
    throw new Error("Failed to reach the backend. Check that the API is running.");
  }

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}.`);
  }

  return response.json();
}

export function buildAlertsWebSocketUrl(classId) {
  const apiUrl = getApiUrl();
  const protocol = apiUrl.protocol === "https:" ? "wss:" : "ws:";
  const token = encodeURIComponent(TEACHER_TOKEN || ADMIN_TOKEN);
  const suffix = token ? `?token=${token}` : "";
  return `${protocol}//${apiUrl.host}/ws/alerts/${encodeURIComponent(classId)}${suffix}`;
}

export function buildProtectedAssetUrl(path, role = "admin") {
  const token = role === "admin" ? ADMIN_TOKEN : TEACHER_TOKEN || ADMIN_TOKEN;
  const assetUrl = new URL(path, getApiUrl().origin);
  if (token) {
    assetUrl.searchParams.set("token", token);
  }
  return assetUrl.toString();
}
