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
  format_status: z.string(),
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
    // Parse the body once — re-reading a consumed stream silently drops the
    // server's detail.message and degrades to "HTTP <status>".
    const d = await r.json().catch(() => null);
    if (d?.detail?.code === "possible_duplicate") {
      throw new DuplicateError(d.detail.candidates ?? []);
    }
    throw new ApiError(r.status, d?.detail?.message ?? `HTTP ${r.status}`);
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

// ---------- prescriptions (S1b-Core) ----------
const RxItemSchema = z.object({
  id: z.string(),
  appliance_id: z.string(),
  arch: z.string(),
  tooth_ops: z.array(z.any()),
  options: z.any().nullable(),
  qty: z.number(),
});
export type RxItem = z.infer<typeof RxItemSchema>;

const RxSchema = z.object({
  id: z.string(),
  rx_number: z.string(),
  patient_id: z.string(),
  case_id: z.string().nullable(),
  status: z.string(),
  fulfillment_status: z.string(),
  form_type: z.string(),
  form_payload: z.any().nullable(),
  due_date: z.string().nullable(),
  notes: z.string().nullable(),
  practice_org_id: z.string(),
  lab_org_id: z.string().nullable(),
  location_id: z.string().nullable(),
  doctor_id: z.string().nullable(),
  checked_in_via: z.string().nullable(),
  signature_name: z.string().nullable(),
  signed_rx_version: z.number().nullable(),
  version: z.number(),
  submitted_at: z.string().nullable(),
  checked_in_at: z.string().nullable(),
  completed_at: z.string().nullable(),
  created_at: z.string(),
  items: z.array(RxItemSchema).optional(),
});
export type Rx = z.infer<typeof RxSchema>;

const RxPageSchema = z.object({
  items: z.array(RxSchema),
  next_cursor: z.string().nullable(),
  counts: z.record(z.string(), z.number()),
});

const CatalogItemSchema = z.object({
  id: z.string(),
  code: z.string(),
  name: z.string(),
  kind: z.string(),
  category: z.string().nullable(),
  arch_scope: z.string(),
  option_schema: z.any().nullable(),
});
export type CatalogItem = z.infer<typeof CatalogItemSchema>;

const ConnectionSchema = z.object({
  id: z.string(),
  practice_org_id: z.string(),
  lab_org_id: z.string(),
  status: z.string(),
  version: z.number(),
});
export type Connection = z.infer<typeof ConnectionSchema>;

const RosterSchema = z.object({
  id: z.string(),
  org_id: z.string(),
  kind: z.string(),
  display_name: z.string(),
  is_default: z.boolean(),
  status: z.string(),
});

const CommentSchema = z.object({
  id: z.string(),
  rx_id: z.string(),
  body: z.string(),
  created_at: z.string(),
  parent_id: z.string().nullable(),
});
export type RxComment = z.infer<typeof CommentSchema>;

const TransitionSchema = z.object({
  id: z.string(),
  from_status: z.string().nullable(),
  to_status: z.string(),
  via: z.string(),
  note: z.string().nullable(),
  created_at: z.string(),
});
export type RxTransition = z.infer<typeof TransitionSchema>;

export async function listRx(status?: string): Promise<{ items: Rx[]; counts: Record<string, number> }> {
  const u = status ? `/api/v1/rx?status=${encodeURIComponent(status)}` : "/api/v1/rx";
  const r = await req(RxPageSchema, u);
  return { items: r.items, counts: r.counts };
}

export async function createRx(body: {
  patient_id: string; lab_org_id?: string | null; doctor_id?: string | null;
  due_date?: string | null; notes?: string | null;
}): Promise<Rx> {
  return req(RxSchema, "/api/v1/rx", {
    method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body),
  });
}

export async function getRx(id: string): Promise<Rx> {
  return req(RxSchema, `/api/v1/rx/${id}`);
}

export async function updateRx(id: string, version: number, body: {
  lab_org_id?: string | null; doctor_id?: string | null;
  due_date?: string | null; notes?: string | null;
}): Promise<Rx> {
  return req(RxSchema, `/api/v1/rx/${id}`, {
    method: "PATCH",
    headers: { ...JSON_HEADERS, "If-Match": String(version) },
    body: JSON.stringify(body),
  });
}

export async function replaceRxItems(id: string, version: number, items: {
  appliance_id: string; arch: string; options?: Record<string, unknown> | null;
  tooth_ops?: { tooth: string; op: string; detail?: string | null }[]; qty?: number;
}[]): Promise<RxItem[]> {
  const r = await req(z.object({ items: z.array(RxItemSchema) }),
    `/api/v1/rx/${id}/items`, {
    method: "PUT",
    headers: { ...JSON_HEADERS, "If-Match": String(version) },
    body: JSON.stringify({ items }),
  });
  return r.items;
}

export async function submitRx(id: string, version: number,
                               signatureName: string,
                               note?: string): Promise<Rx> {
  return req(RxSchema, `/api/v1/rx/${id}/submit`, {
    method: "POST",
    headers: { ...JSON_HEADERS, "If-Match": String(version),
               "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({ note: note ?? null,
                           signature_name: signatureName,
                           confirm_submit: true }),
  });
}

export async function unsubmitRx(id: string, version: number,
                                 reason?: string): Promise<Rx> {
  return req(RxSchema, `/api/v1/rx/${id}/unsubmit`, {
    method: "POST",
    headers: { ...JSON_HEADERS, "If-Match": String(version) },
    body: JSON.stringify({ reason: reason ?? null }),
  });
}

export async function checkInRx(id: string, version: number,
                                note?: string): Promise<Rx> {
  return req(RxSchema, `/api/v1/rx/${id}/check-in`, {
    method: "POST",
    headers: { ...JSON_HEADERS, "If-Match": String(version) },
    body: JSON.stringify({ note: note ?? null }),
  });
}

const BundleDownloadSchema = z.object({
  bundle: z.object({ id: z.string(), sha256: z.string(),
                     bytes: z.number(), rx_version: z.number() }),
  download_url: z.string(),
  expires_in: z.number(),
});

export async function downloadRxBundle(
    id: string): Promise<z.infer<typeof BundleDownloadSchema>> {
  return req(BundleDownloadSchema, `/api/v1/rx/${id}/bundle-download`, {
    method: "POST", headers: JSON_HEADERS });
}

export async function listRxComments(id: string): Promise<RxComment[]> {
  const r = await req(z.object({ items: z.array(CommentSchema) }),
    `/api/v1/rx/${id}/comments`);
  return r.items;
}

export async function createRxComment(id: string, body: string): Promise<RxComment> {
  return req(CommentSchema, `/api/v1/rx/${id}/comments`, {
    method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ body }),
  });
}

export async function listRxTransitions(id: string): Promise<RxTransition[]> {
  const r = await req(z.object({ items: z.array(TransitionSchema) }),
    `/api/v1/rx/${id}/transitions`);
  return r.items;
}

export async function listCatalog(kind: "parts" | "appliances"): Promise<CatalogItem[]> {
  const r = await req(z.object({ items: z.array(CatalogItemSchema) }),
    `/api/v1/catalog/${kind}`);
  return r.items;
}

export async function listConnections(orgId: string): Promise<Connection[]> {
  const r = await req(z.object({ items: z.array(ConnectionSchema) }),
    `/api/v1/org-connections?org_id=${orgId}`);
  return r.items;
}

export async function listRoster(orgId: string): Promise<z.infer<typeof RosterSchema>[]> {
  const r = await req(z.object({ items: z.array(RosterSchema) }),
    `/api/v1/orgs/${orgId}/roster`);
  return r.items;
}
