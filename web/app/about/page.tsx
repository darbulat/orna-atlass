import Link from "next/link";

export default function AboutPage() {
  return (
    <main className="shell" id="main-content">
      <p className="eyebrow">About ORNA Atlas</p>
      <h1>Listen to places, not playlists.</h1>
      <p>
        ORNA Atlas is a map-first archive of long-form natural soundscapes. Public
        coordinates follow the visibility policy of each recording site, and
        sensitive locations are generalized or hidden.
      </p>
      <p>
        Sessions preserve continuous field recordings, contextual notes, dawn
        timing, and reviewed bird-vocal activity without presenting generated
        fallback audio as a real recording.
      </p>
      <Link href="/atlas">Explore the atlas</Link>
    </main>
  );
}
