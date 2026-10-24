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

const PatientSchema = z.object({
  id: z.string(),
  org_id: z.string(),
  patient_number: z.string(),
  first_name: z.string(),
  last_name: z.string(),
  dob: z.string().nullable(),
  external_ref: z.string().nullable(),
  notes: z.string().nullable(),
  version: z.number(),
  deleted_at: z.string().nullable(),
  created_at: z.string(),
});
export type Patient = z.infer<typeof PatientSchema>;

const PatientPageSchema = z.object({
  items: z.array(PatientSchema),
  next_cursor: z.string().nullable(),
});

export class DuplicateError extends Error {
  constructor(public candidates: { patient_id: string; last_name: string; dob: string | null }[]) {
    super("Possible existing patient");
  }
}

const CaseSchema = z.object({
  id: z.string(),
  patient_id: z.string(),
  label: z.string().nullable(),
  stage: z.string(),
  opened_at: z.string(),
  closed_at: z.string().nullable(),
});
export type Case = z.infer<typeof CaseSchema>;

const AssetSchema = z.object({
  id: z.string(),
  sha256: z.string(),
  kind: z.string(),
  jaw: z.string(),
  parent_asset_id: z.string().nullable(),
  scan_status: z.string(),
  bytes: z.number(),
  created_at: z.string(),
});
export type Asset = z.infer<typeof AssetSchema>;

const PatientAssetSchema = z.object({
  id: z.string(),
  asset_id: z.string(),
  subject_type: z.string(),
  subject_id: z.string(),
  role: z.string(),
  revoked_at: z.string().nullable(),
  asset: AssetSchema,
});
export type PatientAsset = z.infer<typeof PatientAssetSchema>;

const UploadSessionSchema = z.object({
  id: z.string(),
  status: z.string(),
  upload_urls: z.array(z.string()),
  expires_at: z.string(),
  resumed: z.boolean(),
});

const JSON_HEADERS = {
  "Content-Type": "application/json",
  // CSRF guard: required by the API on every unsafe method.
  "X-Requested-With": "XMLHttpRequest",
} as const;

async function req<T>(schema: z.ZodType<T>, url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, { credentials: "include", ...init });
  if (!r.ok) {
    if (r.status === 409) {
      try {
        const d = await r.json();
        if (d?.detail?.code === "possible_duplicate") {
          throw new DuplicateError(d.detail.candidates ?? []);
        }
      } catch (e) {
        if (e instanceof DuplicateError) throw e;
      }
    }
    throw new ApiError(r.status, await safeDetail(r));
  }
  return schema.parse(await r.json());
}

async function req204(url: string, init?: RequestInit): Promise<void> {
  const r = await fetch(url, { credentials: "include", ...init });
  if (!r.ok) throw new ApiError(r.status, await safeDetail(r));
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

// ---------- auth ----------
export async function login(email: string, password: string): Promise<LoginResult> {
  return req(LoginResultSchema, "/api/v1/auth/login", {
    method: "POST", headers: JSON_HEADERS,
    body: JSON.stringify({ email, password }),
  });
}

export async function verify2fa(challengeId: string, code: string): Promise<LoginResult> {
  return req(LoginResultSchema, "/api/v1/auth/2fa/verify", {
    method: "POST", headers: JSON_HEADERS,
    body: JSON.stringify({ challenge_id: challengeId, code }),
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

// ---------- patients ----------
export async function searchPatients(q?: string): Promise<Patient[]> {
  const u = q ? `/api/v1/patients?q=${encodeURIComponent(q)}` : "/api/v1/patients";
  return (await req(PatientPageSchema, u)).items;
}

export async function createPatient(body: {
  first_name: string; last_name: string; dob?: string | null;
  external_ref?: string | null; notes?: string | null;
  confirm_duplicate?: boolean;
}): Promise<Patient> {
  return req(PatientSchema, "/api/v1/patients", {
    method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body),
  });
}

export async function getPatient(id: string): Promise<Patient> {
  return req(PatientSchema, `/api/v1/patients/${id}`);
}

export async function updatePatient(id: string, version: number, body: {
  first_name?: string; last_name?: string; dob?: string | null;
  external_ref?: string | null; notes?: string | null;
}): Promise<Patient> {
  return req(PatientSchema, `/api/v1/patients/${id}`, {
    method: "PATCH",
    headers: { ...JSON_HEADERS, "If-Match": String(version) },
    body: JSON.stringify(body),
  });
}

export async function deletePatient(id: string): Promise<void> {
  return req204(`/api/v1/patients/${id}`, {
    method: "DELETE", headers: JSON_HEADERS,
  });
}

export async function listCases(patientId: string): Promise<Case[]> {
  const r = await req(z.object({ items: z.array(CaseSchema) }),
    `/api/v1/patients/${patientId}/cases`);
  return r.items;
}

export async function createCase(patientId: string, label: string): Promise<Case> {
  return req(CaseSchema, `/api/v1/patients/${patientId}/cases`, {
    method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ label }),
  });
}

export async function listPatientAssets(patientId: string): Promise<PatientAsset[]> {
  const r = await req(z.object({ items: z.array(PatientAssetSchema) }),
    `/api/v1/patients/${patientId}/assets`);
  return r.items;
}

// ---------- assets ----------
async function sha256hex(buf: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", buf);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function uploadAsset(file: File, jaw: string): Promise<Asset> {
  const buf = await file.arrayBuffer();
  const sha = await sha256hex(buf);
  const sess = await req(UploadSessionSchema, "/api/v1/uploads", {
    method: "POST", headers: JSON_HEADERS,
    body: JSON.stringify({
      sha256: sha, bytes: buf.byteLength, kind: "stl", jaw,
      filename_hint: file.name,
    }),
  });
  // Always PUT — a resumed session may point at a staging object that never
  // landed (interrupted previous attempt). PUT is idempotent; skipping it
  // makes the server-side completion check fail permanently.
  const put = await fetch(sess.upload_urls[0], { method: "PUT", body: buf });
  if (!put.ok) throw new ApiError(put.status, `storage upload failed (${put.status})`);
  return req(AssetSchema, `/api/v1/uploads/${sess.id}/complete`, {
    method: "POST", headers: JSON_HEADERS,
    body: JSON.stringify({ sha256: sha }),
  });
}

export async function grantReference(assetId: string, subjectType: string,
                                     subjectId: string, role: string): Promise<void> {
  await req(z.object({ id: z.string() }), `/api/v1/assets/${assetId}/references`, {
    method: "POST", headers: JSON_HEADERS,
    body: JSON.stringify({ subject_type: subjectType, subject_id: subjectId, role }),
  });
}

export async function revokeReference(assetId: string, subjectType: string,
                                      subjectId: string): Promise<void> {
  return req204(`/api/v1/assets/${assetId}/references` +
    `?subject_type=${subjectType}&subject_id=${subjectId}`, {
    method: "DELETE", headers: JSON_HEADERS,
  });
}

export async function downloadUrl(assetId: string): Promise<string> {
  const r = await req(z.object({ url: z.string(), expires_at: z.string(), grant_id: z.string() }),
    `/api/v1/assets/${assetId}/download`, {
    method: "POST", headers: JSON_HEADERS, body: "{}",
  });
  return r.url;
}
