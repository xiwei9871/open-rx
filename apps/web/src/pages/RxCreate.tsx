import { useEffect, useState } from "react";
import {
  createRx, createRxTemplate, listCatalog, listConnections,
  listLocations, listRoster, listRxTemplates, orgs, replaceRxItems,
  searchPatients, type CatalogItem, type Location, type Me, type Patient,
  type RxTemplate,
} from "../api";

const input = { display: "block", width: "100%", marginBottom: 8, padding: 4 } as const;

type ToothOp = { tooth: string; op: string; detail?: string | null };
type DraftItem = {
  appliance_id: string; arch: string;
  options?: Record<string, unknown>;
  tooth_ops?: ToothOp[]; qty?: number;
};

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
      <label>Tooth op
        <select aria-label="Tooth op" value={op}
                onChange={(e) => setOp(e.target.value)}>
          <option value="reset">reset</option>
          <option value="extraction">extraction</option>
          <option value="ipr">ipr</option>
        </select>
      </label>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 3, maxWidth: 420 }}>
        {teeth.map((t) => {
          const on = marked.has(t);
          return (
            <button type="button" key={t} aria-label={`tooth ${t}`}
              aria-pressed={on}
              style={{
                width: 34, padding: "2px 0", fontSize: 11,
                background: on ? "#2b6cb0" : "#fff",
                color: on ? "#fff" : "#333",
                border: "1px solid #bbb", borderRadius: 3,
              }}
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
        <small>{ops.map((o) => `${o.tooth}:${o.op}`).join("  ")}</small>
      )}
    </div>
  );
}

export default function RxCreate({ me, onCreated, onCancel }: {
  me: Me;
  onCreated: (id: string) => void;
  onCancel: () => void;
}) {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [labs, setLabs] = useState<{ id: string; name: string }[]>([]);
  const [doctors, setDoctors] = useState<{ id: string; name: string }[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [templates, setTemplates] = useState<RxTemplate[]>([]);
  const [patientId, setPatientId] = useState("");
  const [labId, setLabId] = useState("");
  const [doctorId, setDoctorId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [notes, setNotes] = useState("");
  const [items, setItems] = useState<DraftItem[]>([]);
  const [pick, setPick] = useState("");
  const [arch, setArch] = useState("upper");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        setPatients(await searchPatients());
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

  async function saveAsTemplate() {
    const name = window.prompt("Template name");
    if (!name || !items.length) return;
    setErr("");
    try {
      await createRxTemplate(name, {
        items: items.map((i) => ({
          catalog_item_id: i.appliance_id, arch: i.arch,
          tooth_ops: i.tooth_ops ?? [], options: i.options ?? null,
          qty: i.qty ?? 1,
        })),
        notes: notes || undefined,
      });
      setTemplates(await listRxTemplates());
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  function addItem() {
    if (!pick) return;
    const c = catalog.find((i) => i.id === pick);
    const required: string[] = (c?.option_schema as { required?: string[] } | null)?.required ?? [];
    const options = required.length
      ? Object.fromEntries(required.map((k) => [k, window.prompt(`${c!.name} — ${k} (required)`) ?? ""]))
      : undefined;
    setItems([...items, { appliance_id: pick, arch, options }]);
    setExpanded(items.length);
    setPick("");
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(""); setBusy(true);
    try {
      const rx = await createRx({
        patient_id: patientId,
        lab_org_id: labId || null,
        doctor_id: doctorId || null,
        location_id: locationId || null,
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
    }
  }

  return (
    <section>
      <h2>New Prescription</h2>
      <form onSubmit={onSubmit}>
        <label>Patient
          <select name="patient" required value={patientId}
                  onChange={(e) => setPatientId(e.target.value)} style={input}>
            <option value="">— select —</option>
            {patients.map((p) => (
              <option key={p.id} value={p.id}>
                {p.last_name}, {p.first_name} ({p.patient_number})
              </option>
            ))}
          </select>
        </label>
        <label>Laboratory
          <select name="lab" value={labId}
                  onChange={(e) => setLabId(e.target.value)} style={input}>
            <option value="">— select —</option>
            {labs.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        </label>
        <label>Doctor
          <select name="doctor" value={doctorId}
                  onChange={(e) => setDoctorId(e.target.value)} style={input}>
            <option value="">— select —</option>
            {doctors.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </label>
        <label>Location
          <select name="location" value={locationId}
                  onChange={(e) => setLocationId(e.target.value)} style={input}>
            <option value="">— select —</option>
            {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        </label>
        <label>Due date
          <input name="due" type="date" value={dueDate}
                 onChange={(e) => setDueDate(e.target.value)} style={input} />
        </label>
        {templates.length > 0 && (
          <label>Apply template
            <select aria-label="Template" defaultValue=""
                    onChange={(e) => e.target.value && applyTemplate(e.target.value)}>
              <option value="">— select template —</option>
              {templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </label>
        )}
        <fieldset>
          <legend>Parts &amp; appliances</legend>
          <div style={{ display: "flex", gap: 8 }}>
            <label>catalog
              <select name="catalog" value={pick}
                      onChange={(e) => setPick(e.target.value)}>
                <option value="">— select item —</option>
                {catalog.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.code} — {c.name}
                  </option>
                ))}
              </select>
            </label>
            <select name="arch" value={arch}
                    onChange={(e) => setArch(e.target.value)}>
              <option value="upper">Upper</option>
              <option value="lower">Lower</option>
              <option value="both">Both</option>
            </select>
            <button type="button" onClick={addItem}>Add</button>
          </div>
          <ul>
            {items.map((i, idx) => {
              const c = catalog.find((x) => x.id === i.appliance_id);
              return (
                <li key={idx}>
                  {c ? `${c.code} — ${c.name}` : i.appliance_id} ({i.arch})
                  {i.options && ` — ${Object.entries(i.options).map(([k, v]) => `${k}=${v}`).join(", ")}`}
                  {(i.tooth_ops?.length ?? 0) > 0 &&
                    ` — teeth ${i.tooth_ops!.map((o) => o.tooth).join(",")}`}
                  {" "}
                  <button type="button" aria-label={`teeth ${idx}`}
                          onClick={() => setExpanded(
                            expanded === idx ? null : idx)}>
                    teeth
                  </button>
                  {" "}
                  <button type="button"
                          onClick={() => setItems(items.filter((_, j) => j !== idx))}>
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
          </ul>
          {items.length > 0 && (
            <button type="button" onClick={saveAsTemplate}>
              Save items as template
            </button>
          )}
        </fieldset>
        <label>Notes
          <textarea name="notes" value={notes}
                    onChange={(e) => setNotes(e.target.value)} style={input} />
        </label>
        <button type="submit" disabled={busy}>Save draft</button>{" "}
        <button type="button" onClick={onCancel}>Cancel</button>
        {err && <p role="alert" style={{ color: "crimson" }}>{err}</p>}
      </form>
    </section>
  );
}
