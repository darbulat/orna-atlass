import Link from "next/link";

export default function AboutPage() {
  return (
    <main className="about-page" id="main-content">
      <nav className="about-nav" aria-label="About navigation">
        <Link className="about-wordmark" href="/atlas">ORNA Atlas</Link>
        <Link href="/atlas">Enter the atlas <span aria-hidden="true">↗</span></Link>
      </nav>

      <header className="about-hero">
        <p className="eyebrow">The sound of our planet</p>
        <h1>The Earth has a voice.</h1>
        <p className="about-intro">
          We have named every mountain, mapped every ocean floor, and photographed
          the planet from orbit. Yet most of us have never truly heard it.
        </p>
      </header>

      <section className="about-manifesto" aria-labelledby="manifesto-heading">
        <p className="about-section-number">01 / Manifesto</p>
        <div>
          <h2 id="manifesto-heading">One place. One continuous moment.</h2>
          <p>
            ORNA Atlas is a living, map-first archive of long-form natural soundscapes.
            It opens a doorway into the moments when landscapes speak most clearly:
            dawn arriving over a forest, wetlands waking, and night yielding to light.
          </p>
          <p>
            These are not playlists, ambient loops, or generated substitutes. Each
            session is anchored to a real landscape and preserves the continuity of
            a field recording alongside its local time, habitat, and listening notes.
          </p>
          <blockquote>Entry points into something that was always there.</blockquote>
        </div>
      </section>

      <section className="about-principles" aria-labelledby="principles-heading">
        <p className="about-section-number">02 / The atlas</p>
        <div>
          <h2 id="principles-heading">A document of a living planet.</h2>
          <div className="about-principle-grid">
            <article><span>Place first</span><h3>Sound belongs to a landscape.</h3><p>Recordings are explored through geography, habitat, local time, and season.</p></article>
            <article><span>Unbroken time</span><h3>Stay for the whole horizon.</h3><p>Long-form sessions preserve the pace and quiet of the original moment.</p></article>
            <article><span>Careful access</span><h3>Protection comes before precision.</h3><p>Sensitive recording sites are generalized or hidden rather than exposed.</p></article>
          </div>
        </div>
      </section>

      <section className="about-closing" aria-labelledby="closing-heading">
        <p className="about-section-number">03 / Begin</p>
        <h2 id="closing-heading">Somewhere on Earth,<br />a chorus is beginning.</h2>
        <Link className="about-enter" href="/atlas">Enter ORNA Atlas <span aria-hidden="true">→</span></Link>
      </section>
    </main>
  );
}
