import { useEffect, useState } from "react";
import Admin from "./Admin.jsx";
import Login from "./Login.jsx";

const areas = [
  { title: "Dizin", text: "Sahte AD/LDAP adaptoru. Yuva var, gercek bind yok." },
  { title: "Panel veritabani", text: "PostgreSQL semasi. Adres TAMLIFE_DATABASE_URL." },
  { title: "Dis kaynak", text: "Oracle REPORTDB ve ikinci kaynak yalniz yapilandirma yuvasi." },
];

export default function App() {
  const [user, setUser] = useState(undefined);

  useEffect(() => {
    fetch("/api/v1/session/me", { credentials: "same-origin" })
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => setUser(body ? body.data : null))
      .catch(() => setUser(null));
  }, []);

  async function logout() {
    await fetch("/api/v1/session/logout", { method: "POST", credentials: "same-origin" });
    setUser(null);
  }

  if (user === undefined) return null;
  if (user === null) return <Login onLogin={setUser} />;

  return (
    <main>
      <header className="bar">
        <h1>TAMLIFE v3.5</h1>
        <span className="muted">
          {user.username} · {user.role}
        </span>
        <button type="button" onClick={logout}>Çıkış</button>
      </header>
      <div className="grid">
        {areas.map((area) => (
          <article key={area.title}>
            <h2>{area.title}</h2>
            <p>{area.text}</p>
          </article>
        ))}
      </div>
      <Admin />
    </main>
  );
}
