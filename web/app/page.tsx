const featuredPlaces = ["Cloud forest dawn", "Atlantic wetland", "High desert wind"];

export default function HomePage() {
  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">ORNA Atlas</p>
        <h1>Explore long-form nature recordings through a living map.</h1>
        <p>
          A production foundation for place-first audio: coordinates, habitat context, local
          time, sunrise discovery, and immersive sessions anchored to real landscapes.
        </p>
        <div className="actions">
          <a href="/atlas">Open atlas placeholder</a>
          <a href="/about">Read the mission</a>
        </div>
      </section>
      <section className="panel" aria-label="Featured placeholders">
        {featuredPlaces.map((place) => (
          <article key={place}>
            <span>Coming soon</span>
            <h2>{place}</h2>
          </article>
        ))}
      </section>
    </main>
  );
}
