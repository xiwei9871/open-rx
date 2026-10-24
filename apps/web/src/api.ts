// Thin fetch client — cookies carry the session (SameSite=Lax).
// Every response is parsed through a zod schema: TypeScript types must not
// silently diverge from what the API actually returns (B0.1-02).
import { z } from "zod";

const LoginResultSchema = z.object({
  requires_2fa: z.boolean(),
  challenge_id: z.string().nullable(),
});
export type LoginResult = z.infer<typeof LoginResultSchema>;

const MeSchema = z.object({
  user_id: z.string(),
  email: z.string(),
  display_name: z.string(),
  org_id: z.string().nullable(),
  org_name: z.string().nullable(),
  org_kind: z.string().nullable(),
  tenant_id: z.string().nullable(),
  role: z.string(),
  permissions: z.array(z.string()),
  session_expires_at: z.string(),
});
export type Me = z.infer<typeof MeSchema>;

const OrgSchema = z.object({
  id: z.string(),
  kind: z.string(),
  name: z.string(),
  status: z.string(),
  timezone: z.string(),
  created_at: z.string(),
});
export type Org = z.infer<typeof OrgSchema>;

const OrgPageSchema = z.object({
  items: z.array(OrgSchema),
  next_cursor: z.string().nullable(),
});
export type OrgPage = z.infer<typeof OrgPageSchema>;

const JSON_HEADERS = {
  "Content-Type": "application/json",
  // CSRF guard: required by the API on every unsafe method.
  "X-Requested-With": "XMLHttpRequest",
} as const;

async function req<T>(schema: z.ZodType<T>, url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, { credentials: "include", ...init });
  if (!r.ok) throw new ApiError(r.status, await safeDetail(r));
  return schema.parse(await r.json());
}

async function safeDetail(r: Response): Promise<string> {
  try {
    const d = await r.json();
    return d?.detail?.message ?? `HTTP ${r.status}`;
  } catch {
    return `HTTP ${r.status}`;
  }
}

export class ApiError extends Error {
  constructor(public status: number, msg: string) { super(msg); }
}

export async function login(email: string, password: string): Promise<LoginResult> {
  return req(LoginResultSchema, "/api/v1/auth/login", {
    method: "POST", headers: JSON_HEADERS,
    body: JSON.stringify({ email, password }),
  });
}

export async function me(): Promise<Me> {
  return req(MeSchema, "/api/v1/auth/me");
}

export async function orgs(): Promise<Org[]> {
  const page = await req(OrgPageSchema, "/api/v1/orgs");
  return page.items;
}

export async function logout(): Promise<void> {
  await fetch("/api/v1/auth/logout", {
    method: "POST", credentials: "include", headers: JSON_HEADERS,
  });
}
