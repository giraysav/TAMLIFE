import { useState } from "react";

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/v1/session/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username.trim(), password }),
      });
      if (response.status === 401) {
        setError("Kullanıcı adı veya şifre hatalı.");
      } else if (!response.ok) {
        setError(`Giriş yapılamadı (${response.status}).`);
      } else {
        const body = await response.json();
        onLogin(body.data);
      }
    } catch {
      setError("Sunucuya ulaşılamadı.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <form className="login-card" onSubmit={submit}>
        <h1>TAMLIFE</h1>
        <p className="muted">AD/LDAP hesabınızla giriş yapın</p>
        <label>
          Kullanıcı adı (AD/LDAP)
          <input
            type="text"
            autoComplete="username"
            autoFocus
            required
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </label>
        <label>
          Şifre
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error ? <p className="error" role="alert">{error}</p> : null}
        <button type="submit" disabled={busy}>{busy ? "Giriş yapılıyor…" : "Giriş"}</button>
      </form>
    </main>
  );
}
