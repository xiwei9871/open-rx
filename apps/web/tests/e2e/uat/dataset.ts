/* UAT dataset — six reusable synthetic patients (P01..P06) plus their
 * treatment cases. Idempotent: keyed on external_ref UAT-P0x, so re-runs
 * never duplicate. Created through the real API (precondition only). */
import { expect, type APIRequestContext } from "@playwright/test";
import { apiGet, apiLogin, apiPost, PA_ADMIN } from "./helpers";

export const UAT_PATIENTS = {
  P01: { ref: "UAT-P01", first: "Jordan", last: "Keeley",
         dob: "2012-03-14", caseLabel: "Retention — Hawley upper",
         note: "P01 teen retainer, simplest happy path" },
  P02: { ref: "UAT-P02", first: "Milo", last: "Vargas",
         dob: "2011-07-02", caseLabel: "Expansion — RPE",
         note: "P02 expander, required options + tooth ops" },
  P03: { ref: "UAT-P03", first: "Casey", last: "Reyes",
         dob: "2009-11-30", caseLabel: "Retainer check",
         note: "P03 duplicate-detection twin A" },
  P03B: { ref: "UAT-P03B", first: "Casey", last: "Reyes",
          dob: "2009-11-30", caseLabel: "Retainer check (dup)",
          note: "P03B same identity, confirm_duplicate twin" },
  P04: { ref: "UAT-P04", first: "Amara", last: "Osei",
         dob: "1998-05-21", caseLabel: "Aligner finishing",
         note: "P04 clinical communication case" },
  P05: { ref: "UAT-P05", first: "Noor", last: "Lindqvist",
         dob: "2005-02-09", caseLabel: "Fixed retainer",
         note: "P05 QC -> ship -> receive -> deliver closure" },
  P06: { ref: "UAT-P06", first: "Daniil", last: "Petrov",
         dob: "2000-09-17", caseLabel: "Post-debond retainer",
         note: "P06 delete-protection subject" },
} as const;

type Ref = keyof typeof UAT_PATIENTS;

async function findPatient(ctx: APIRequestContext, ref: string) {
  const r = await apiGet(ctx,
    `/api/v1/patients?external_ref=${encodeURIComponent(ref)}`);
  const items = (await r.json()).items ?? [];
  return items[0] ?? null;
}

async function ensurePatient(ctx: APIRequestContext, ref: Ref) {
  const p = UAT_PATIENTS[ref];
  let found = await findPatient(ctx, p.ref);
  if (found) {
    // Loser of a create race may see the patient before the winner commits
    // its case — retry until a case is visible rather than returning early.
    for (let i = 0; i < 20; i++) {
      const cs = await apiGet(ctx, `/api/v1/patients/${found.id}/cases`);
      if (((await cs.json()).items ?? []).length > 0) return found;
      await new Promise((r) => setTimeout(r, 500));
    }
    return found;
  }
  const r = await apiPost(ctx, "/api/v1/patients", {
    first_name: p.first, last_name: p.last, dob: p.dob,
    external_ref: p.ref, notes: p.note,
    // P03B deliberately duplicates P03's identity — confirm it.
    confirm_duplicate: ref === "P03B",
  });
  if (!r.ok()) {
    // Parallel workers race the create; the unique external_ref means the
    // loser can simply pick up the row the winner just committed.
    found = await findPatient(ctx, p.ref);
    expect(found, `create ${p.ref}`).toBeTruthy();
    return found;
  }
  found = await r.json();

  // treatment case on the new patient
  const c = await apiPost(ctx, `/api/v1/patients/${found.id}/cases`,
    { label: p.caseLabel });
  expect(c.ok(), `case ${p.ref}`).toBeTruthy();
  return found;
}

/** Ensures all six dataset patients + cases exist; returns the map. */
export async function ensureDataset():
    Promise<Record<Ref, { id: string; patient_number: string }>> {
  const ctx = await apiLogin(PA_ADMIN.email, PA_ADMIN.password);
  const out = {} as Record<Ref, { id: string; patient_number: string }>;
  for (const ref of Object.keys(UAT_PATIENTS) as Ref[]) {
    out[ref] = await ensurePatient(ctx, ref);
  }
  await ctx.dispose();
  return out;
}
