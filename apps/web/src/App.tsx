import { useState } from "react";
import { login, me, orgs, type Me, type Org } from "./api";

export default function App() {
  const [email, setEmail] = useState("admin@pa.dev");
  const [password, setPassword] = useState("Passw0rd!dev");
  const [user, setUser] = useState<Me | null>(null);
  const [orgList, setOrgs] = useState<Org[]>([]);
  const [err, setErr] = useState("");

  async function onLogin(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    try {
      await login(email, password);
      setUser(await me());
      setOrgs(await orgs());
    } catch (ex) {
      setErr(String(ex));
    }
  }

  return (
    <main style={{ fontFamily: "system-ui", maxWidth: 480, margin: "4rem auto" }}>
      <h1>EasyRS</h1>
      {!user ? (
        <form onSubmit={onLogin}>
          <label>Email <input value={email} onChange={(e) => setEmail(e.target.value)} style={{ display: "block", width: "100%" }} /></label>
          <label>Password <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} style={{ display: "block", width: "100%" }} /></label>
          <button type="submit" style={{ marginTop: 12 }}>Sign in</button>
          {err && <p style={{ color: "crimson" }}>{err}</p>}
        </form>
      ) : (
        <section>
          <p>Signed in as <strong>{user.display_name}</strong> ({user.email})</p>
          <h2>Organizations</h2>
          <ul>{orgList.map((o) => <li key={o.id}>{o.name} — {o.kind} ({o.status})</li>)}</ul>
        </section>
      )}
    </main>
  );
}
