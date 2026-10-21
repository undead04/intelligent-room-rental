import type {
  CityDto,
  DistrictDto,
  ListingDetailDto,
  ListingCountDto,
  ListingDto,
  ListingQueryDto,
  PriceStatsDto,
  ResponseDto,
  RoomTypeDto,
  WardDto,
  AgentChatRequest,
  AgentResponse,
  AgentTraceEvent,
} from "@/types/dto";
const DEFAULT_API_URL = "http://localhost:8000/api/v1";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL).replace(/\/$/, "");
const DEFAULT_AGENT_URL = "http://localhost:8001";
const AGENT_BASE_URL = (process.env.NEXT_PUBLIC_AI_AGENT_URL || DEFAULT_AGENT_URL).replace(/\/$/, "");

class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
    public readonly requestId?: string | null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function buildQuery<T extends object>(params: T) {
  const query = new URLSearchParams();

  Object.entries(params as Record<string, number | string | undefined>).forEach(([key, value]) => {
    if (value !== undefined && value !== "") {
      query.set(key, String(value));
    }
  });

  const serialized = query.toString();
  return serialized ? `?${serialized}` : "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => null) as {
      message?: string;
      code?: string;
      request_id?: string | null;
    } | null;
    throw new ApiError(
      error?.message || `API request failed: ${response.status} ${response.statusText}`,
      response.status,
      error?.code,
      error?.request_id,
    );
  }

  const envelope = (await response.json()) as ResponseDto<T>;
  return envelope.data;
}

export const listingsApi = {
  list(params: ListingQueryDto = {}) {
    return request<ListingDto[]>(`/listings/${buildQuery(params)}`);
  },

  count(params: Omit<ListingQueryDto, "limit" | "offset"> = {}) {
    return request<ListingCountDto>(`/listings/total${buildQuery(params)}`);
  },

  getById(listingId: string) {
    return request<ListingDetailDto>(`/listings/${encodeURIComponent(listingId)}`);
  },
};

export const locationsApi = {
  cities() {
    return request<CityDto[]>("/locations/cities");
  },

  districts(params: { city_id?: number; search?: string } = {}) {
    return request<DistrictDto[]>(`/locations/districts${buildQuery(params)}`);
  },

  wards(params: { district_id?: number; search?: string } = {}) {
    return request<WardDto[]>(`/locations/wards${buildQuery(params)}`);
  },
};

export const roomTypesApi = {
  list() {
    return request<RoomTypeDto[]>("/room-types");
  },
};

export const priceStatsApi = {
  get(params: { city_id?: number; district_id?: number; room_type_id?: number; room_type?: number } = {}) {
    return request<PriceStatsDto>(`/listings/price-stats${buildQuery(params)}`);
  },
};

async function agentRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${AGENT_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    const error = (await response.json().catch(() => null)) as {
      detail?: string;
      message?: string;
    } | null;
    throw new ApiError(
      error?.detail || error?.message || `AI Agent request failed: ${response.status} ${response.statusText}`,
      response.status,
    );
  }

  return (await response.json()) as T;
}

export interface AgentStreamCallbacks {
  onTrace?: (event: AgentTraceEvent) => void;
  onTextDelta?: (delta: string) => void;
  onDone?: (response: AgentResponse) => void;
}

export const agentApi = {
  chat(data: AgentChatRequest) {
    return agentRequest<AgentResponse>("/api/v1/chat", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async chatStream(data: AgentChatRequest, callbacks: AgentStreamCallbacks = {}): Promise<AgentResponse> {
    const response = await fetch(`${AGENT_BASE_URL}/api/v1/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify(data),
    });

    if (!response.ok || !response.body) {
      const error = (await response.json().catch(() => null)) as {
        detail?: string;
        message?: string;
      } | null;
      throw new ApiError(
        error?.detail || error?.message || `AI Agent stream failed: ${response.status} ${response.statusText}`,
        response.status,
      );
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let finalResponse: AgentResponse | null = null;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";

      for (const block of blocks) {
        if (!block.trim()) continue;
        let eventName = "message";
        const dataLines: string[] = [];

        for (const line of block.split("\n")) {
          if (line.startsWith("event:")) {
            eventName = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            dataLines.push(line.slice(5).trim());
          }
        }

        const rawData = dataLines.join("\n");
        if (!rawData) continue;

        try {
          const parsed = JSON.parse(rawData);
          const eventType = parsed?.type || eventName;

          if (eventName === "trace" || eventType === "trace" || eventType === "node_step") {
            callbacks.onTrace?.(parsed as AgentTraceEvent);
          } else if (eventName === "text_delta" || eventType === "text_delta") {
            if (typeof parsed.delta === "string") {
              callbacks.onTextDelta?.(parsed.delta);
            }
          } else if (
            eventName === "complete" ||
            eventName === "done" ||
            eventType === "complete" ||
            eventType === "done"
          ) {
            finalResponse = parsed as AgentResponse;
            callbacks.onDone?.(finalResponse);
          } else if (eventName === "error" || eventType === "error") {
            throw new ApiError(parsed.error || "Lỗi trong quá trình stream từ AI Agent", 500);
          }
        } catch (err) {
          if (err instanceof ApiError) throw err;
        }
      }
    }

    if (!finalResponse) {
      throw new ApiError("Luồng phản hồi kết thúc bất ngờ trước khi hoàn tất", 500);
    }
    return finalResponse;
  },

  health() {
    return agentRequest<{ status: string; service: string; version: string }>("/api/v1/health");
  },

  clearSession(sessionId: string) {
    return agentRequest<{ status: string; message: string }>(`/api/v1/session/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
    }).catch(() => null);
  },
};


