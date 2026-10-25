import { useEffect, useRef, useState } from "react";
import {
  createRx, createRxTemplate, getPatient, listCases, listCatalog,
  listConnections, listLocations, listRoster, listRxTemplates, orgs,
  replaceRxItems, searchPatients, type Case, type CatalogItem,
  type Location, type Me, type Patient, type RxTemplate,
} from "../api";

type ToothOp = { tooth: string; op: string; detail?: string | null };
type DraftItem = {
  appliance_id: string; arch: string;
  options?: Record<string, unknown>;
  tooth_ops?: ToothOp[]; qty?: number;
};

function requiredOptions(c: CatalogItem | undefined): string[] {
  return (c?.option_schema as { required?: string[] } | null)?.required ?? [];
}

// FDI quadrants by arch: upper = 1x/2x, lower = 4x/3x, both = all.
const TEETH: Record<string, string[]> = {
  upper: [...[1, 2].flatMap((q) => [1, 2, 3, 4, 5, 6, 7, 8].map((t) => `${q}${t}`))],
  lower: [...[4, 3].flatMap((q) => [1, 2, 3, 4, 5, 6, 7, 8].map((t) => `${q}${t}`))],
  both: [...[1, 2, 4, 3].flatMap((q) => [1, 2, 3, 4, 5, 6, 7, 8].map((t) => `${q}${t}`))],
};

/** RX-008 SIMPLIFY: tooth checkbox/marking grid (not a drag canvas). */
function ToothPicker({ arch, ops, onChange }: {
  arch: string; ops: ToothOp[]; onChange: (ops: ToothOp[]) => void;
}) {
  const [op, setOp] = useState("reset");
  const marked = new Map(ops.map((o) => [o.tooth, o]));
  const teeth = TEETH[arch] ?? TEETH.both;
  return (
    <div style={{ marginTop: 4 }}>
      <label className="field" style={{ maxWidth: 200 }}>
        <span>Tooth op</span>
        <select aria-label="Tooth op" value={op}
                onChange={(e) => setOp(e.target.value)}>
          <option value="reset">reset</option>
          <option value="extraction">extraction</option>
          <option value="ipr">ipr</option>
        </select>
      </label>
      <div className="toothgrid">
        {teeth.map((t) => {
          const on = marked.has(t);
          return (
            <button type="button" key={t} aria-label={`tooth ${t}`}
              aria-pressed={on}
              onClick={() => {
                const next = new Map(marked);
                if (on) next.delete(t); else next.set(t, { tooth: t, op });
                onChange([...next.values()]);
              }}>
              {t}
            </button>
          );
        })}
      </div>
      {ops.length > 0 && (
        <small className="muted">
          {ops.map((o) => `${o.tooth}:${o.op}`).join("  ")}
        </small>
      )}
    </div>
  );
}

export default function RxCreate({ me, onCreated, onCancel, initialPatientId }: {
  me: Me;
  onCreated: (id: string) => void;
  onCancel: () => void;
  initialPatientId?: string;
}) {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [patientQ, setPatientQ] = useState("");
  const [labs, setLabs] = useState<{ id: string; name: string }[]>([]);
  const [doctors, setDoctors] = useState<{ id: string; name: string }[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [templates, setTemplates] = useState<RxTemplate[]>([]);
  const [patientId, setPatientId] = useState(initialPatientId ?? "");
  const [cases, setCases] = useState<Case[]>([]);
  const [caseId, setCaseId] = useState("");
  const [labId, setLabId] = useState("");
  const [doctorId, setDoctorId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [notes, setNotes] = useState("");
  const [items, setItems] = useState<DraftItem[]>([]);
  const [pick, setPick] = useState("");
  const [arch, setArch] = useState("upper");
  const [optVals, setOptVals] = useState<Record<string, string>>({});
  const [expanded, setExpanded] = useState<number | null>(null);
  const [tmplName, setTmplName] = useState("");
  const [err, setErr] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);

  const picked = catalog.find((i) => i.id === pick);
  const pickedRequired = requiredOptions(picked);

  // Load the patient's treatment cases whenever the patient changes.
  useEffect(() => {
    setCaseId("");
    if (!patientId) { setCases([]); return; }
    listCases(patientId).then(setCases).catch(() => setCases([]));
  }, [patientId]);

  // The patient picker must not silently truncate at the first page:
  // debounce a server-side name/ref search so any patient is reachable.
  useEffect(() => {
    let live = true;
    const t = setTimeout(async () => {
      try {
        const list = await searchPatients(patientQ.trim() || undefined);
        if (!live) return;
        setPatients((prev) => {
          const sel = prev.find((p) => p.id === patientId);
          return sel && !list.some((p) => p.id === sel.id)
            ? [sel, ...list] : list;
        });
      } catch { /* keep the last good list */ }
    }, 300);
    return () => { live = false; clearTimeout(t); };
  }, [patientQ]); // eslint-disable-line react-hooks/exhaustive-deps

  // Prefilled patient (patient-detail "New Rx") may be outside page one —
  // fetch it by id so the option always exists.
  useEffect(() => {
    if (!initialPatientId) return;
    getPatient(initialPatientId).then((p) =>
      setPatients((prev) => prev.some((x) => x.id === p.id)
        ? prev : [p, ...prev])).catch(() => {});
  }, [initialPatientId]);

  useEffect(() => {
    (async () => {
      try {
        if (me.org_id) {
          const [conns, allOrgs, roster, locs, tmpls] = await Promise.all([
            listConnections(me.org_id), orgs(), listRoster(me.org_id),
            listLocations(me.org_id), listRxTemplates(),
          ]);
          const accepted = new Set(
            conns.filter((c) => c.status === "accepted")
                 .map((c) => c.lab_org_id));
          setLabs(allOrgs.filter((o) => accepted.has(o.id))
                          .map((o) => ({ id: o.id, name: o.name })));
          setDoctors(roster.filter((r) => r.status === "active")
                           .map((r) => ({ id: r.id, name: r.display_name })));
          setLocations(locs);
          setTemplates(tmpls);
          // IAM-001/003: org defaults prefill (user can still change).
          const mine = allOrgs.find((o) => o.id === me.org_id);
          if (mine?.default_doctor_id) setDoctorId(mine.default_doctor_id);
          if (mine?.default_location_id) setLocationId(mine.default_location_id);
        }
        const [parts, apps] = await Promise.all([
          listCatalog("parts"), listCatalog("appliances")]);
        setCatalog([...parts, ...apps]);
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
      }
    })();
  }, [me.org_id]);

  function applyTemplate(id: string) {
    const t = templates.find((x) => x.id === id);
    if (!t) return;
    const p = t.payload as {
      items?: { catalog_item_id: string; arch: string;
                tooth_ops?: ToothOp[]; options?: Record<string, unknown>;
                qty?: number }[];
      notes?: string; due_days_offset?: number;
    };
    setItems((p.items ?? []).map((i) => ({
      appliance_id: i.catalog_item_id, arch: i.arch,
      tooth_ops: i.tooth_ops, options: i.options, qty: i.qty,
    })));
    if (p.notes) setNotes(p.notes);
    if (p.due_days_offset) {
      const d = new Date(); d.setDate(d.getDate() + p.due_days_offset);
      setDueDate(d.toISOString().slice(0, 10));
    }
  }

  async function saveAsTemplate(e: React.FormEvent) {
    e.preventDefault();
    if (!tmplName.trim() || !items.length) return;
    setErr(""); setInfo("");
    try {
      await createRxTemplate(tmplName.trim(), {
        items: items.map((i) => ({
          catalog_item_id: i.appliance_id, arch: i.arch,
          tooth_ops: i.tooth_ops ?? [], options: i.options ?? null,
          qty: i.qty ?? 1,
        })),
        notes: notes || undefined,
      });
      setTemplates(await listRxTemplates());
      setTmplName("");
      setInfo("Template saved");
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
  }

  function addItem() {
    if (!pick) return;
    setErr("");
    const missing = pickedRequired.filter((k) => !optVals[k]?.trim());
    if (missing.length) {
      setErr(`Required option${missing.length > 1 ? "s" : ""} missing: `
             + missing.join(", "));
      return;
    }
    const options = pickedRequired.length
      ? Object.fromEntries(pickedRequired.map((k) => [k, optVals[k].trim()]))
      : undefined;
    setItems([...items, { appliance_id: pick, arch, options }]);
    setExpanded(items.length);
    setPick("");
    setOptVals({});
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    if (!patientId) {
      setErr("Select a patient before saving the prescription.");
      return;
    }
    if (busyRef.current) return; // double-submit guard
    busyRef.current = true;
    setBusy(true);
    try {
      const rx = await createRx({
        patient_id: patientId,
        lab_org_id: labId || null,
        doctor_id: doctorId || null,
        location_id: locationId || null,
        case_id: caseId || null,
        due_date: dueDate || null,
        notes: notes || null,
      });
      if (items.length) {
        await replaceRxItems(rx.id, rx.version, items);
      }
      onCreated(rx.id);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
      setBusy(false);
      busyRef.current = false;
    }
  }

  return (
    <section>
      <div className="page-head">
        <h2>New Prescription</h2>
      </div>
      <form onSubmit={onSubmit} noValidate>
        <div className="card">
          <h3>Order details</h3>
          <div className="grid2">
            <label className="field"><span>Filter</span>
              <input name="patient_filter"
                     placeholder="Type a name or ref…"
                     value={patientQ}
                     onChange={(e) => setPatientQ(e.target.value)} />
            </label>
            <label className="field"><span>Patient</span>
              <select name="patient" required value={patientId}
                      onChange={(e) => setPatientId(e.target.value)}>
                <option value="">— select —</option>
                {patients.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.last_name}, {p.first_name} ({p.patient_number})
                  </option>
                ))}
              </select>
            </label>
            {patientId && (
              <label className="field"><span>Treatment case</span>
                <select name="case" value={caseId}
                        onChange={(e) => setCaseId(e.target.value)}>
                  <option value="">
                    {cases.length === 0 ? "— no cases on file —"
                     : "— select case —"}
                  </option>
                  {cases.map((c) =>
                    <option key={c.id} value={c.id}>
                      {c.label ?? `case ${c.id.slice(0, 8)}…`} ({c.stage})
                    </option>)}
                </select>
              </label>
            )}
            <label className="field"><span>Laboratory</span>
              <select name="lab" value={labId}
                      onChange={(e) => setLabId(e.target.value)}>
                <option value="">— select —</option>
                {labs.map((l) =>
                  <option key={l.id} value={l.id}>{l.name}</option>)}
              </select>
            </label>
            <label className="field"><span>Doctor</span>
              <select name="doctor" value={doctorId}
                      onChange={(e) => setDoctorId(e.target.value)}>
                <option value="">— select —</option>
                {doctors.map((d) =>
                  <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            </label>
            <label className="field"><span>Location</span>
              <select name="location" value={locationId}
                      onChange={(e) => setLocationId(e.target.value)}>
                <option value="">— select —</option>
                {locations.map((l) =>
                  <option key={l.id} value={l.id}>{l.name}</option>)}
              </select>
            </label>
            <label className="field"><span>Due date</span>
              <input name="due" type="date" value={dueDate}
                     onChange={(e) => setDueDate(e.target.value)} />
            </label>
            {templates.length > 0 && (
              <label className="field"><span>Apply template</span>
                <select aria-label="Template" defaultValue=""
                        onChange={(e) =>
                          e.target.value && applyTemplate(e.target.value)}>
                  <option value="">— select template —</option>
                  {templates.map((t) =>
                    <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </label>
            )}
          </div>
        </div>

        <div className="card">
          <h3>Parts &amp; appliances</h3>
          <div className="row">
            <label className="field grow" style={{ marginBottom: 0 }}>
              <span>Catalog item</span>
              <select name="catalog" value={pick}
                      onChange={(e) => { setPick(e.target.value);
                                         setOptVals({}); }}>
                <option value="">— select item —</option>
                {catalog.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.code} — {c.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field" style={{ marginBottom: 0 }}>
              <span>Arch</span>
              <select name="arch" value={arch}
                      onChange={(e) => setArch(e.target.value)}>
                <option value="upper">Upper</option>
                <option value="lower">Lower</option>
                <option value="both">Both</option>
              </select>
            </label>
          </div>
          {pickedRequired.length > 0 && (
            <div className="row" style={{ marginTop: "0.6rem" }}>
              {pickedRequired.map((k) => (
                <label className="field" key={k} style={{ marginBottom: 0 }}>
                  <span>{k} (required)</span>
                  <input aria-label={`Option ${k}`} value={optVals[k] ?? ""}
                    onChange={(e) =>
                      setOptVals({ ...optVals, [k]: e.target.value })} />
                </label>
              ))}
            </div>
          )}
          <div className="row" style={{ marginTop: "0.6rem" }}>
            <button type="button" onClick={addItem} disabled={!pick}>
              Add item
            </button>
          </div>
          <ul>
            {items.map((i, idx) => {
              const c = catalog.find((x) => x.id === i.appliance_id);
              return (
                <li key={idx}>
                  {c ? `${c.code} — ${c.name}` : i.appliance_id} ({i.arch})
                  {i.options &&
                    ` — ${Object.entries(i.options)
                        .map(([k, v]) => `${k}=${v}`).join(", ")}`}
                  {(i.tooth_ops?.length ?? 0) > 0 &&
                    ` — teeth ${i.tooth_ops!.map((o) => o.tooth).join(",")}`}
                  {" "}
                  <button type="button" className="small"
                          aria-label={`teeth ${idx}`}
                          onClick={() => setExpanded(
                            expanded === idx ? null : idx)}>
                    teeth
                  </button>
                  {" "}
                  <button type="button" className="small"
                          onClick={() =>
                            setItems(items.filter((_, j) => j !== idx))}>
                    remove
                  </button>
                  {expanded === idx && (
                    <ToothPicker arch={i.arch} ops={i.tooth_ops ?? []}
                      onChange={(ops) => setItems(items.map((x, j) =>
                        j === idx ? { ...x, tooth_ops: ops } : x))} />
                  )}
                </li>
              );
            })}
            {items.length === 0 &&
              <li className="empty">No items added yet.</li>}
          </ul>
          {items.length > 0 && (
            <div className="row" style={{ marginTop: "0.5rem" }}>
              <input aria-label="Template name" placeholder="Template name"
                     value={tmplName}
                     onChange={(e) => setTmplName(e.target.value)} />
              <button type="button" className="small" disabled={!tmplName.trim()}
                      onClick={saveAsTemplate}>
                Save items as template
              </button>
            </div>
          )}
        </div>

        <div className="card">
          <h3>Notes</h3>
          <label className="field"><span className="hide-sm">Notes</span>
            <textarea name="notes" rows={3} value={notes}
                      onChange={(e) => setNotes(e.target.value)} />
          </label>
          {err && <p role="alert" className="alert">{err}</p>}
          {info && <p role="status" className="notice">{info}</p>}
          <div className="row end">
            <button type="button" onClick={onCancel}>Cancel</button>
            <button type="submit" className="primary" disabled={busy}>
              {busy ? "Saving…" : "Save draft"}
            </button>
          </div>
        </div>
      </form>
    </section>
  );
}
