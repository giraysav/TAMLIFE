const areas = [
  {
    title: "Dizin",
    text: "Sahte AD/LDAP adaptoru. Yuva var, gercek bind yok.",
  },
  {
    title: "Panel veritabani",
    text: "PostgreSQL semasi. Adres TAMLIFE_DATABASE_URL.",
  },
  {
    title: "Dis kaynak",
    text: "Oracle REPORTDB ve ikinci kaynak yalniz yapilandirma yuvasi.",
  },
];

export default function App() {
  return (
    <main>
      <h1>TAMLIFE v3.5</h1>
      <p className="muted">Kabuk. Is kurali yok.</p>
      <div className="grid">
        {areas.map((area) => (
          <article key={area.title}>
            <h2>{area.title}</h2>
            <p>{area.text}</p>
          </article>
        ))}
      </div>
    </main>
  );
}
