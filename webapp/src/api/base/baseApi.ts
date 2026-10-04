/** Stands in for Init Data when the app is open in a plain browser: the
 * session cookie signs the request, so no header is sent (#157). */
export const WEB_SESSION = "web-session";

/** A refused request, with the server's answer kept: `code` is the `error` the
 * route words for the app (`too_soon`, `wrong_code`…), `body` the rest of it
 * (`retry_after`, `attempts_left`). The message stays "status: code". */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    readonly body: Record<string, unknown> = {},
  ) {
    super(`${status}: ${code}`);
  }
}

export class BaseApi {
  constructor(protected readonly baseUrl: string = "") {}

  protected initHeaders(initData: string): HeadersInit {
    return initData === WEB_SESSION
      ? { "Content-Type": "application/json" }
      : { "X-Telegram-Init-Data": initData, "Content-Type": "application/json" };
  }

  protected buildUrl(
    endpoint: string = "",
    query?: Record<string, string | number | boolean | null | undefined>,
  ): string {
    const cleanBase = this.baseUrl.replace(/\/+$/, "");
    const cleanEndpoint = endpoint
      ? endpoint.startsWith("/")
        ? endpoint
        : `/${endpoint}`
      : "";
    let url = `${cleanBase}${cleanEndpoint}` || "/";

    if (query) {
      const params = new URLSearchParams();
      for (const [key, val] of Object.entries(query)) {
        if (val != null) {
          params.set(key, String(val));
        }
      }
      const qs = params.toString();
      if (qs) {
        url += (url.includes("?") ? "&" : "?") + qs;
      }
    }
    return url;
  }

  protected async request<T>(
    initData: string,
    endpoint: string = "",
    init?: RequestInit,
    query?: Record<string, string | number | boolean | null | undefined>,
  ): Promise<T> {
    const fullPath = this.buildUrl(endpoint, query);
    const response = await fetch(fullPath, {
      ...init,
      headers: {
        ...this.initHeaders(initData),
        ...(init?.headers ?? {}),
      },
    });
    if (!response.ok) {
      let detail = await response.text();
      let body: Record<string, unknown> = {};
      try {
        const json = JSON.parse(detail) as { error?: string; message?: string };
        body = json as Record<string, unknown>;
        detail = json.error || json.message || detail;
      } catch {
        /* keep text */
      }
      throw new ApiError(response.status, detail, body);
    }
    if (response.status === 204) {
      return undefined as T;
    }
    return (await response.json()) as T;
  }

  protected get<T>(
    initData: string,
    endpoint: string = "",
    query?: Record<string, string | number | boolean | null | undefined>,
    init?: RequestInit,
  ): Promise<T> {
    return this.request<T>(initData, endpoint, { ...init, method: "GET" }, query);
  }

  protected post<T>(
    initData: string,
    endpoint: string = "",
    body?: unknown,
    query?: Record<string, string | number | boolean | null | undefined>,
    init?: RequestInit,
  ): Promise<T> {
    return this.request<T>(
      initData,
      endpoint,
      {
        ...init,
        method: "POST",
        body: body !== undefined ? JSON.stringify(body) : "{}",
      },
      query,
    );
  }

  protected patch<T>(
    initData: string,
    endpoint: string = "",
    body?: unknown,
    query?: Record<string, string | number | boolean | null | undefined>,
    init?: RequestInit,
  ): Promise<T> {
    return this.request<T>(
      initData,
      endpoint,
      {
        ...init,
        method: "PATCH",
        body: body !== undefined ? JSON.stringify(body) : undefined,
      },
      query,
    );
  }

  protected put<T>(
    initData: string,
    endpoint: string = "",
    body?: unknown,
    query?: Record<string, string | number | boolean | null | undefined>,
    init?: RequestInit,
  ): Promise<T> {
    return this.request<T>(
      initData,
      endpoint,
      {
        ...init,
        method: "PUT",
        body: body !== undefined ? JSON.stringify(body) : undefined,
      },
      query,
    );
  }

  protected delete<T>(
    initData: string,
    endpoint: string = "",
    query?: Record<string, string | number | boolean | null | undefined>,
    init?: RequestInit,
  ): Promise<T> {
    return this.request<T>(initData, endpoint, { ...init, method: "DELETE" }, query);
  }
}
