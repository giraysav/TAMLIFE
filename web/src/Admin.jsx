import { useEffect, useState } from "react";

export default function Admin() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let gone = false;
    fetch("/api/v1/admin", { credentials: "same-origin" })
      .then(async (response) => {
        if (response.status === 403) {
          throw new Error("403");
        }
        if (response.status === 401) {
          throw new Error("401");
        }
        if (!response.ok) {
          throw new Error(String(response.status));
        }
        return response.json();
      })
      .then((body) => {
        if (!gone) {
          setData(body.data);
        }
      })
      .catch((err) => {
        if (!gone) {
          setError(err.message);
        }
      });
    return () => {
      gone = true;
    };
  }, []);

  return (
    <section className="admin">
      <h2>Yonetim</h2>
      {error === "403" ? <p className="error">403 Yetki yok</p> : null}
      {error === "401" ? <p className="error">Oturum gerekli</p> : null}
      {error && error !== "403" && error !== "401" ? (
        <p className="error">Yonetim acilamadi</p>
      ) : null}
      <div className="grid">
        <article>
          <h3>DB baglantilari</h3>
          {data ? (
            <ul>
              {data.connections.map((row) => (
                <li key={row.id}>
                  {row.slot}: {row.configured ? "ayarli" : "ayarli degil"}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">Yalniz admin oturumu.</p>
          )}
        </article>
        <article>
          <h3>Veri yonetimi</h3>
          {data ? (
            <>
              <ul>
                {data.data_management.tables.map((name) => (
                  <li key={name}>
                    <code>{name}</code>
                  </li>
                ))}
              </ul>
              <p>{data.data_management.note}</p>
            </>
          ) : (
            <p className="muted">Ice alma tablolari admin oturumunda.</p>
          )}
        </article>
      </div>
    </section>
  );
}
