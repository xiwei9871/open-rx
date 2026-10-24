// Thin fetch client — cookies carry the session (SameSite=Lax).
export interface Me { id: string; email: string; display_name: string; memberships: unknown[]; }
export interface Org { id: string; kind: string; name: string; status: string; }

export async function login(email: string, password: string): Promise<{ status: string }> {
  const r = await fetch("/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });
  if (!r.ok) throw new Error(`login failed: ${r.status}`);
  return r.json();
}

export async function me(): Promise<Me> {
  const r = await fetch("/api/v1/auth/me", { credentials: "include" });
  if (!r.ok) throw new Error(`me failed: ${r.status}`);
  return r.json();
}

export async function orgs(): Promise<Org[]> {
  const r = await fetch("/api/v1/orgs", { credentials: "include" });
  if (!r.ok) throw new Error(`orgs failed: ${r.status}`);
  return r.json();
}
