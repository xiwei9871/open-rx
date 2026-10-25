import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError, createCase, deletePatient, downloadUrl, getPatient,
  grantReference, listCases, listPatientAssets, listRxHistory,
  revokeReference, updatePatient, uploadAsset,
  type Case, type Me, type Patient, type PatientAsset, type Rx,
} from "../api";
import StlPreview from "../components/StlPreview";

const input = { display: "block", width: "100%", marginBottom: 6, padding: 4 } as const;

export default function PatientDetailPage({ me, patientId, onDeleted, onOpenRx }: {
  me: Me; patientId: string; onDeleted: () => void;
  onOpenRx?: (rxId: string) => void;
}) {
  const [patient, setPatient] = useState<Patient | null>(null);
  const [cases, setCases] = useState<Case[]>([]);
  const [rxHistory, setRxHistory] = useState<Rx[]>([]);
  const [assets, setAssets] = useState<PatientAsset[]>([]);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const [denied, setDenied] = useState(false);
  const [edit, setEdit] = useState({ first_name: "", last_name: "", notes: "" });
  const [caseLabel, setCaseLabel] = useState("");
  const [jaw, setJaw] = useState("na");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const canWrite = me.permissions.includes("patient:write");
  const canDelete = me.permissions.includes("patient:delete");
  const canUpload = me.permissions.includes("asset:write");
  const canShare = me.permissions.includes("asset:share");

  const refresh = useCallback(async () => {
    setErr("");
    try {
      const p = await getPatient(patientId);
      setPatient(p);
      setEdit({ first_name: p.first_name, last_name: p.last_name, notes: p.notes ?? "" });
      setCases(await listCases(patientId));
      setAssets(await listPatientAssets(patientId));
      if (me.permissions.includes("rx:read")) {
        setRxHistory(await listRxHistory(patientId));
      }
    } catch (ex) {
      if (ex instanceof ApiError && ex.status === 403) setDenied(true);
      else setErr(ex instanceof Error ? ex.message : String(ex));
    }
  }, [patientId]);

  useEffect(() => { void refresh(); }, [refresh]);

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    if (!patient) return;
    setErr("");
    try {
      const p = await updatePatient(patient.id, patient.version, {
        first_name: edit.first_name, last_name: edit.last_name,
        notes: edit.notes || null,
      });
      setPatient(p);
      setMsg("Saved");
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
  }

  async function onDelete() {
    if (!patient) return;
    try {
      await deletePatient(patient.id);
      onDeleted();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
  }

  async function onAddCase(e: React.FormEvent) {
    e.preventDefault();
    try {
      await createCase(patientId, caseLabel);
      setCaseLabel("");
      setCases(await listCases(patientId));
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
  }

  async function onUpload(e: React.FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file || !patient) return;
    setBusy(true); setErr(""); setMsg("");
    try {
      const asset = await uploadAsset(file, jaw);
      if (canShare) {
        await grantReference(asset.id, "patient", patient.id, "original");
      }
      setAssets(await listPatientAssets(patientId));
      setMsg(`Uploaded ${asset.sha256.slice(0, 12)}…`);
      if (fileRef.current) fileRef.current.value = "";
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusy(false);
    }
  }

  if (denied) return <p role="alert">Access denied.</p>;
  if (err && !patient) return <p role="alert">{err}</p>;
  if (!patient) return <p>Loading…</p>;

  return (
    <section>
      <h2>{patient.last_name}, {patient.first_name} <small>({patient.patient_number})</small></h2>
      <p>DOB: {patient.dob ?? "—"} · External ref: {patient.external_ref ?? "—"} · v{patient.version}</p>
      {msg && <p role="status" style={{ color: "green" }}>{msg}</p>}
      {err && <p role="alert" style={{ color: "crimson" }}>{err}</p>}

      {canWrite && (
        <form onSubmit={onSave}>
          <h3>Edit</h3>
          <input required aria-label="First name" value={edit.first_name}
            onChange={(e) => setEdit({ ...edit, first_name: e.target.value })} style={input} />
          <input required aria-label="Last name" value={edit.last_name}
            onChange={(e) => setEdit({ ...edit, last_name: e.target.value })} style={input} />
          <textarea aria-label="Notes" placeholder="Notes" value={edit.notes}
            onChange={(e) => setEdit({ ...edit, notes: e.target.value })} style={input} />
          <button type="submit">Save</button>
        </form>
      )}
      {canDelete && <button onClick={onDelete}>Delete patient</button>}

      <h3>Treatment cases</h3>
      {cases.length === 0 ? <p>No cases.</p> : (
        <ul>{cases.map((c) => (
          <li key={c.id}>{c.label ?? "(no label)"} — {c.stage}
            {" "}· opened {new Date(c.opened_at).toLocaleDateString()}</li>
        ))}</ul>
      )}
      {canWrite && (
        <form onSubmit={onAddCase} style={{ display: "flex", gap: 8 }}>
          <input required aria-label="Case label" placeholder="New case label"
            value={caseLabel} onChange={(e) => setCaseLabel(e.target.value)}
            style={{ flex: 1, padding: 4 }} />
          <button type="submit">Open case</button>
        </form>
      )}

      <h3>Prescription history</h3>
      {rxHistory.length === 0 ? <p>No prescriptions.</p> : (
        <ul>{rxHistory.map((r) => (
          <li key={r.id}>
            <a href="#" onClick={(e) => { e.preventDefault(); onOpenRx?.(r.id); }}>
              {r.rx_number}
            </a>{" "}
            — {r.status} · due {r.due_date ?? "—"} · {r.created_at.slice(0, 10)}
          </li>
        ))}</ul>
      )}

      <h3>Files</h3>
      {assets.length === 0 ? <p>No files.</p> : (
        <ul>{assets.map((a) => (
          <li key={a.id}>
            {a.asset.kind}/{a.asset.jaw} — {a.asset.bytes} bytes —
            sha256 {a.asset.sha256.slice(0, 16)}… — {a.asset.format_status}
            {" "}<button type="button" onClick={async () => {
              const u = await downloadUrl(a.asset_id); window.open(u, "_blank");
            }}>Download</button>
            {a.asset.kind === "stl" && a.asset.format_status === "format_ok" && (
              <button type="button" aria-label={`Preview ${a.asset_id}`}
                onClick={() => setPreviewId(
                  previewId === a.asset_id ? null : a.asset_id)}>Preview</button>
            )}
            {previewId === a.asset_id && <StlPreview assetId={a.asset_id} />}
            {canShare && (
              <button type="button" onClick={async () => {
                await revokeReference(a.asset_id, a.subject_type, a.subject_id);
                setAssets(await listPatientAssets(patientId));
              }}>Unlink</button>
            )}
          </li>
        ))}</ul>
      )}
      {canUpload && (
        <form onSubmit={onUpload} style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input required aria-label="STL file" type="file" accept=".stl"
            ref={fileRef} />
          <select aria-label="Jaw" value={jaw} onChange={(e) => setJaw(e.target.value)}>
            <option value="na">n/a</option>
            <option value="upper">upper</option>
            <option value="lower">lower</option>
          </select>
          <button type="submit" disabled={busy}>
            {busy ? "Uploading…" : "Upload STL"}
          </button>
        </form>
      )}
    </section>
  );
}
