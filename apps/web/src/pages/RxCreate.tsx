import { useEffect, useState } from "react";
import {
  createRx, listCatalog, listConnections, listRoster, orgs,
  replaceRxItems, searchPatients, type CatalogItem, type Me, type Patient,
} from "../api";

const input = { display: "block", width: "100%", marginBottom: 8, padding: 4 } as const;

type DraftItem = { appliance_id: string; arch: string; options?: Record<string, unknown> };

export default function RxCreate({ me, onCreated, onCancel }: {
  me: Me;
  onCreated: (id: string) => void;
  onCancel: () => void;
}) {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [labs, setLabs] = useState<{ id: string; name: string }[]>([]);
  const [doctors, setDoctors] = useState<{ id: string; name: string }[]>([]);
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [patientId, setPatientId] = useState("");
  const [labId, setLabId] = useState("");
  const [doctorId, setDoctorId] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [notes, setNotes] = useState("");
  const [items, setItems] = useState<DraftItem[]>([]);
  const [pick, setPick] = useState("");
  const [arch, setArch] = useState("upper");
  const [err, setErr] = useState("");

  useEffect(() => {
    (async () => {
      try {
        setPatients(await searchPatients());
        if (me.org_id) {
          const [conns, allOrgs, roster] = await Promise.all([
            listConnections(me.org_id), orgs(), listRoster(me.org_id),
          ]);
          const accepted = new Set(
            conns.filter((c) => c.status === "accepted")
                 .map((c) => c.lab_org_id));
          setLabs(allOrgs.filter((o) => accepted.has(o.id))
                          .map((o) => ({ id: o.id, name: o.name })));
          setDoctors(roster.filter((r) => r.status === "active")
                           .map((r) => ({ id: r.id, name: r.display_name })));
        }
        const [parts, apps] = await Promise.all([
          listCatalog("parts"), listCatalog("appliances")]);
        setCatalog([...parts, ...apps]);
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
      }
    })();
  }, [me.org_id]);

  function addItem() {
    if (!pick) return;
    const c = catalog.find((i) => i.id === pick);
    const required: string[] = (c?.option_schema as { required?: string[] } | null)?.required ?? [];
    const options = required.length
      ? Object.fromEntries(required.map((k) => [k, window.prompt(`${c!.name} — ${k} (required)`) ?? ""]))
      : undefined;
    setItems([...items, { appliance_id: pick, arch, options }]);
    setPick("");
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    try {
      const rx = await createRx({
        patient_id: patientId,
        lab_org_id: labId || null,
        doctor_id: doctorId || null,
        due_date: dueDate || null,
        notes: notes || null,
      });
      if (items.length) {
        await replaceRxItems(rx.id, rx.version, items);
      }
      onCreated(rx.id);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
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
        <label>Due date
          <input name="due" type="date" value={dueDate}
                 onChange={(e) => setDueDate(e.target.value)} style={input} />
        </label>
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
                  {" "}
                  <button type="button"
                          onClick={() => setItems(items.filter((_, j) => j !== idx))}>
                    remove
                  </button>
                </li>
              );
            })}
          </ul>
        </fieldset>
        <label>Notes
          <textarea name="notes" value={notes}
                    onChange={(e) => setNotes(e.target.value)} style={input} />
        </label>
        <button type="submit">Save draft</button>{" "}
        <button type="button" onClick={onCancel}>Cancel</button>
        {err && <p role="alert" style={{ color: "crimson" }}>{err}</p>}
      </form>
    </section>
  );
}
