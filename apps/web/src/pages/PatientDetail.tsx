import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError, createCase, deletePatient, downloadUrl, getPatient,
  grantReference, listCases, listPatientAssets, listRxHistory,
  revokeReference, updatePatient, uploadAsset,
  type Case, type Me, type Patient, type PatientAsset, type Rx,
} from "../api";
import StlPreview from "../components/StlPreview";

const DEMO = import.meta.env.VITE_DEMO === "1";
import { fmtDate, saveAs, statusLabel, useActionLock } from "../lib";

export default function PatientDetailPage({ me, patientId, onDeleted, onOpenRx, onNewRx }: {
  me: Me; patientId: string; onDeleted: () => void;
  onOpenRx?: (rxId: string) => void;
  onNewRx?: (patientId: string) => void;
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

  const lock = useActionLock();
  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    if (!patient) return;
    await lock(async () => {
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
    });
  }

  async function onDelete() {
    if (!patient) return;
    await lock(async () => {
    try {
      await deletePatient(patient.id);
      onDeleted();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
    });
  }

  async function onAddCase(e: React.FormEvent) {
    e.preventDefault();
    await lock(async () => {
    try {
      await createCase(patientId, caseLabel);
      setCaseLabel("");
      setCases(await listCases(patientId));
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
    });
  }

  async function onUpload(e: React.FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file || !patient) return;
    await lock(async () => {
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
    });
  }

  if (denied) return <p role="alert" className="alert">Access denied.</p>;
  if (err && !patient) return <p role="alert" className="alert">{err}</p>;
  if (!patient) return <p className="empty">Loading…</p>;

  return (
    <section>
      <div className="page-head">
        <h2>{patient.last_name}, {patient.first_name}{" "}
          <small className="muted">({patient.patient_number})</small></h2>
      </div>
      <p className="muted">DOB: {patient.dob ?? "—"} ·
        External ref: {patient.external_ref ?? "—"} · v{patient.version}</p>
      {msg && <p role="status" className="notice">{msg}</p>}
      {err && <p role="alert" className="alert">{err}</p>}

      {canWrite && (
        <form onSubmit={onSave} className="card stack">
          <h3>Edit</h3>
          <input required aria-label="First name" value={edit.first_name}
            onChange={(e) => setEdit({ ...edit, first_name: e.target.value })} />
          <input required aria-label="Last name" value={edit.last_name}
            onChange={(e) => setEdit({ ...edit, last_name: e.target.value })} />
          <textarea aria-label="Notes" placeholder="Notes" rows={2}
            value={edit.notes}
            onChange={(e) => setEdit({ ...edit, notes: e.target.value })} />
          <div className="row">
            <button type="submit" className="primary">Save</button>
            {canDelete &&
              <button type="button" className="danger" onClick={onDelete}>
                Delete patient</button>}
          </div>
        </form>
      )}
      {!canWrite && canDelete &&
        <button className="danger" onClick={onDelete}>Delete patient</button>}

      <div className="card">
      <h3>Treatment cases</h3>
      {cases.length === 0 ? <p className="empty">No cases.</p> : (
        <ul>{cases.map((c) => (
          <li key={c.id}>{c.label ?? "(no label)"} — {c.stage}
            {" "}· opened {fmtDate(c.opened_at)}</li>
        ))}</ul>
      )}
      {canWrite && (
        <form onSubmit={onAddCase} className="row">
          <input required aria-label="Case label" className="grow"
            placeholder="New case label"
            value={caseLabel} onChange={(e) => setCaseLabel(e.target.value)} />
          <button type="submit">Open case</button>
        </form>
      )}
      </div>

      <div className="card">
      <div className="row spread">
        <h3>Prescription history</h3>
        {onNewRx && me.permissions.includes("rx:write") && (
          <button type="button" className="small primary"
                  onClick={() => onNewRx(patientId)}>
            New Rx for this patient
          </button>
        )}
      </div>
      {rxHistory.length === 0 ? <p className="empty">No prescriptions.</p> : (
        <ul>{rxHistory.map((r) => (
          <li key={r.id}>
            <a href={`/rx/${r.id}`}
               onClick={(e) => { e.preventDefault(); onOpenRx?.(r.id); }}>
              {r.rx_number}
            </a>{" "}
            <span className={`pill st-${r.status}`}>{statusLabel(r.status)}</span>
            {" "}· due {fmtDate(r.due_date)} · {fmtDate(r.created_at)}
          </li>
        ))}</ul>
      )}
      </div>

      <div className="card">
      <h3>Files</h3>
      {assets.length === 0 ? <p className="empty">No files.</p> : (
        <ul>{assets.map((a) => (
          <li key={a.id}>
            {a.asset.kind === "stl" ? "Digital scan" : a.asset.kind}
            {a.asset.jaw === "upper" ? " — Upper arch"
              : a.asset.jaw === "lower" ? " — Lower arch" : ""}
            {" "}· {a.asset.bytes} bytes · SHA-256 {a.asset.sha256.slice(0, 16)}…
            {" "}· {a.asset.format_status === "format_ok"
                ? "valid mesh" : "not a valid mesh"}
            {" "}<button type="button" className="small" onClick={() => lock(
              async () => {
                try {
                  const u = await downloadUrl(a.asset_id);
                  await saveAs(u, `${a.asset.kind}-${a.asset.sha256.slice(0, 12)}.stl`);
                } catch (ex) {
                  setErr(ex instanceof Error ? ex.message : String(ex));
                }
              })}>Download</button>
            {a.asset.kind === "stl" && a.asset.format_status === "format_ok" && (
              <button type="button" className="small"
                aria-label={`Preview ${a.asset_id}`}
                onClick={() => setPreviewId(
                  previewId === a.asset_id ? null : a.asset_id)}>
                {previewId === a.asset_id ? "Hide" : "Preview"}</button>
            )}
            {previewId === a.asset_id && <StlPreview assetId={a.asset_id} />}
            {canShare && (
              <button type="button" className="small" onClick={async () => {
                await revokeReference(a.asset_id, a.subject_type, a.subject_id);
                setAssets(await listPatientAssets(patientId));
              }}>Unlink</button>
            )}
          </li>
        ))}</ul>
      )}
      {canUpload && DEMO && (
        <p className="muted">Do not upload real patient records,
        identifiable scans, or clinical data.</p>
      )}
      {canUpload && (
        <form onSubmit={onUpload} className="row">
          <input required aria-label="STL file" type="file" accept=".stl"
            ref={fileRef} />
          <select aria-label="Jaw" value={jaw} onChange={(e) => setJaw(e.target.value)}>
            <option value="na">n/a</option>
            <option value="upper">Upper arch</option>
            <option value="lower">Lower arch</option>
          </select>
          <button type="submit" disabled={busy}>
            {busy ? "Uploading…" : "Upload STL"}
          </button>
        </form>
      )}
      </div>
    </section>
  );
}
