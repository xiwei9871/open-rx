import { useCallback, useEffect, useState } from "react";
import {
  ApiError, createPatient, searchPatients,
  type Me, type Patient,
} from "../api";

const input = { display: "block", width: "100%", marginBottom: 6, padding: 4 } as const;

export default function PatientsPage({ me, onOpen }: {
  me: Me; onOpen: (id: string) => void;
}) {
  const [items, setItems] = useState<Patient[]>([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [denied, setDenied] = useState(false);
  const canWrite = me.permissions.includes("patient:write");

  const [form, setForm] = useState({ first_name: "", last_name: "", dob: "", external_ref: "" });
  const [createErr, setCreateErr] = useState("");
  const [dup, setDup] = useState<{ patient_id: string; last_name: string; dob: string | null }[] | null>(null);

  const refresh = useCallback(async (query?: string) => {
    setLoading(true); setErr("");
    try {
      setItems(await searchPatients(query));
    } catch (ex) {
      if (ex instanceof ApiError && ex.status === 403) setDenied(true);
      else setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  // PAT-002: search-as-you-type — debounce keystrokes, keep manual submit.
  useEffect(() => {
    const t = setTimeout(() => { void refresh(q || undefined); }, 300);
    return () => clearTimeout(t);
  }, [q, refresh]);

  async function onSearch(e: React.FormEvent) {
    e.preventDefault();
    await refresh(q || undefined);
  }

  async function onCreate(e: React.FormEvent, confirm = false) {
    e.preventDefault();
    setCreateErr(""); setDup(null);
    try {
      const p = await createPatient({
        first_name: form.first_name, last_name: form.last_name,
        dob: form.dob || null, external_ref: form.external_ref || null,
        confirm_duplicate: confirm,
      });
      setForm({ first_name: "", last_name: "", dob: "", external_ref: "" });
      onOpen(p.id);
    } catch (ex) {
      if (ex instanceof Error && "candidates" in ex) {
        setDup((ex as { candidates: typeof dup }).candidates ?? []);
      } else {
        setCreateErr(ex instanceof Error ? ex.message : String(ex));
      }
    }
  }

  if (denied) return <p role="alert">Access denied — your role cannot view patients.</p>;

  return (
    <section>
      <h2>Patients</h2>
      <form onSubmit={onSearch} style={{ display: "flex", gap: 8 }}>
        <input aria-label="Search" placeholder="Search name / external ref"
          value={q} onChange={(e) => setQ(e.target.value)}
          style={{ flex: 1, padding: 4 }} />
        <button type="submit">Search</button>
      </form>
      {loading ? <p>Loading…</p> : err ? <p role="alert">{err}</p> : (
        items.length === 0 ? <p>No patients.</p> : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr>
              <th align="left">Number</th><th align="left">Name</th>
              <th align="left">DOB</th><th align="left">External ref</th>
            </tr></thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.id} style={{ cursor: "pointer" }}
                  onClick={() => onOpen(p.id)}>
                  <td>{p.patient_number}</td>
                  <td>{p.last_name}, {p.first_name}</td>
                  <td>{p.dob ?? "—"}</td>
                  <td>{p.external_ref ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}

      {canWrite && (
        <form onSubmit={onCreate} style={{ marginTop: 24 }}>
          <h3>New patient</h3>
          <input required aria-label="First name" placeholder="First name"
            value={form.first_name}
            onChange={(e) => setForm({ ...form, first_name: e.target.value })} style={input} />
          <input required aria-label="Last name" placeholder="Last name"
            value={form.last_name}
            onChange={(e) => setForm({ ...form, last_name: e.target.value })} style={input} />
          <input aria-label="Date of birth" type="date" value={form.dob}
            onChange={(e) => setForm({ ...form, dob: e.target.value })} style={input} />
          <input aria-label="External ref" placeholder="External ref (optional)"
            value={form.external_ref}
            onChange={(e) => setForm({ ...form, external_ref: e.target.value })} style={input} />
          <button type="submit">Create patient</button>
          {createErr && <p role="alert" style={{ color: "crimson" }}>{createErr}</p>}
          {dup && (
            <div role="alert" style={{ border: "1px solid orange", padding: 8 }}>
              <p>Possible duplicate patients:</p>
              <ul>{dup.map((c) => (
                <li key={c.patient_id}>{c.last_name} — {c.dob ?? "no dob"}</li>))}</ul>
              <button type="button" onClick={(e) => onCreate(e, true)}>
                Create anyway
              </button>
            </div>
          )}
        </form>
      )}
    </section>
  );
}
