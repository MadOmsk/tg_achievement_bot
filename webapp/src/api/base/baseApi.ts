export class BaseApi {
  constructor(protected readonly baseUrl: string = "") {}

  protected initHeaders(initData: string): HeadersInit {
    return {
      "X-Telegram-Init-Data": initData,
      "Content-Type": "application/json",
    };
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
      try {
        const json = JSON.parse(detail) as { error?: string; message?: string };
        detail = json.error || json.message || detail;
      } catch {
        /* keep text */
      }
      throw new Error(`${response.status}: ${detail}`);
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
