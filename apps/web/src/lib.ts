/** Shared display helpers — status labels, pills, date formatting. */
import { useCallback, useRef } from "react";

/** Re-entrancy lock for async event handlers. A double-click (or Enter+click)
 *  can fire twice before React re-renders a `disabled` button; the second
 *  invocation returns immediately instead of double-submitting. */
export function useActionLock() {
  const locked = useRef(false);
  return useCallback(async (fn: () => Promise<void>) => {
    if (locked.current) return;
    locked.current = true;
    try { await fn(); } finally { locked.current = false; }
  }, []);
}

export const STATUS_LABELS: Record<string, string> = {
  draft: "Saved", submitted: "Submitted", checked_in: "Checked-In",
  in_progress: "In Progress", on_hold: "On Hold", completed: "Completed",
  reopened: "Reopened", cancelled: "Cancelled",
};

export const FULFILLMENT_LABELS: Record<string, string> = {
  none: "—", qc_pending: "QC pending", qc_passed: "QC passed",
  shipped: "Shipped", dispatched: "Dispatched", in_transit: "In transit",
  received: "Received", delivered: "Delivered", exception: "Exception",
};

export const QC_LABELS: Record<string, string> = {
  none: "Not checked", pass: "Pass", fail: "Fail",
};

export function statusLabel(s: string): string {
  return STATUS_LABELS[s] ?? s.replace(/_/g, " ");
}

export function fulfillmentLabel(s: string): string {
  return FULFILLMENT_LABELS[s] ?? s.replace(/_/g, " ");
}

/** "2026-10-25T04:14:40+00:00" → "Oct 25, 2026 04:14" (UTC display). */
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-US", {
    month: "short", day: "numeric", year: "numeric",
    hour: "2-digit", minute: "2-digit", hour12: false,
  });
}

/** Fetch a presigned URL and save it as a file. window.open() after an
 *  await is popup-blocked in real browsers; a blob + anchor download is
 *  reliable and keeps the user on the page. */
export async function saveAs(presignedUrl: string, filename: string) {
  const resp = await fetch(presignedUrl);
  if (!resp.ok) throw new Error(`download failed (${resp.status})`);
  const blob = await resp.blob();
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(href);
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric", timeZone: "UTC",
  });
}
