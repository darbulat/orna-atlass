import Link from "next/link";

import { AnalyticsLink } from "../components/analytics-link";
import { AtlasExplorer } from "../components/atlas/AtlasExplorer";
import { HomeListeningSample } from "../components/home-listening-sample";
import { fetchCollections, type CollectionSummary } from "../lib/api/collections";
import {
  fetchAtlasPoints,
  fetchCurrentDawn,
  fetchFeaturedSessions,
  type FeaturedSession,
} from "../lib/api/sessions";

export const dynamic = "force-dynamic";

async function fetchHomeAtlas() {
  const atlas = await fetchAtlasPoints("globe", [], { cache: "no-store" });
  const dawn = await fetchCurrentDawn(Math.max(250, atlas.points.length), { cache: "no-store" });
  return { atlas, dawn };
}

export default async function HomePage() {
  const [atlasResult, featuredResult, collectionsResult] = await Promise.allSettled([
    fetchHomeAtlas(),
    fetchFeaturedSessions(6),
    fetchCollections(6),
  ]);
  const featuredSessions = featuredResult.status === "fulfilled" ? featuredResult.value : null;
  const collections = collectionsResult.status === "fulfilled" ? collectionsResult.value : null;
  const collectionDestination = (slug: string) => (
    collections?.some((collection) => collection.slug === slug) ? `/collections/${slug}` : "/atlas"
  );

  return (
    <div className="shell home-shell">
      <nav className="site-nav home-nav" aria-label="Primary navigation">
        <Link className="site-wordmark" href="/">ORNA Atlas</Link>
        <div>
          <Link href="#atlas-entry">Map</Link>
          <Link href="#collections">Collections</Link>
          <Link href="/about">About</Link>
          <Link href="#atlas-search">Search</Link>
          <Link href="/membership?mode=login">Sign in</Link>
          <Link href="/membership?mode=register">Subscribe</Link>
        </div>
      </nav>
      <main id="main-content">
      {atlasResult.status === "fulfilled" ? (
        <div className="home-atlas-entry" id="atlas-entry">
          <AtlasExplorer
            initialView="globe"
            points={atlasResult.value.atlas.points}
            dawn={atlasResult.value.dawn}
            sidePanelSession={null}
            showInternalNavigation={false}
          />
        </div>
      ) : (
        <section className="panel unavailable-panel home-atlas-unavailable" role="alert">
          <p className="eyebrow">Atlas unavailable</p>
          <h1>We could not load the listening globe.</h1>
          <p>The atlas is temporarily unavailable. Please try again soon.</p>
        </section>
      )}
      <section className="hero">
        <p className="eyebrow">Continuous field archive</p>
        <h1>Real places for focus, rest, and deep listening.</h1>
        <p>
          Continuous nature recordings from living landscapes—no loops and no generated sound.
          Start listening now, or travel through the archive by place and local time.
        </p>
        {featuredSessions && featuredSessions.length > 0 ? (
          <HomeListeningSample session={featuredSessions[0]} />
        ) : null}
        <div className="actions">
          <AnalyticsLink destination="/atlas" eventName="hero_cta_clicked" placement="hero_primary">Explore the atlas</AnalyticsLink>
          <AnalyticsLink destination="/about" eventName="hero_cta_clicked" placement="hero_secondary">Read the mission</AnalyticsLink>
        </div>
      </section>

      <section className="conversion-section intent-section" aria-label="Choose your listening path">
        <div className="section-heading conversion-heading">
          <p className="eyebrow">Listen with intention</p>
          <h2 id="intent-heading">Where do you want the sound to take you?</h2>
          <p>Every path leads to a real, continuous field recording—not a loop or a generated substitute.</p>
        </div>
        <div className="intent-grid">
          <AnalyticsLink destination={collectionDestination("no-human-noise")} eventName="listening_path_selected" placement="intent_focus"><span>01</span><h3>Focus</h3><p>Low-interruption landscapes selected for long stretches of attention.</p><strong>Find quiet sessions →</strong></AnalyticsLink>
          <AnalyticsLink destination={collectionDestination("dawn-archive")} eventName="listening_path_selected" placement="intent_restore"><span>02</span><h3>Restore</h3><p>Unhurried first-light recordings for a slower, calmer pause.</p><strong>Meet the dawn →</strong></AnalyticsLink>
          <AnalyticsLink destination={collectionDestination("wetlands")} eventName="listening_path_selected" placement="intent_unwind"><span>03</span><h3>Unwind</h3><p>Water, reeds, wind, and long natural rhythms for the end of the day.</p><strong>Enter the wetlands →</strong></AnalyticsLink>
          <AnalyticsLink destination="/atlas" eventName="listening_path_selected" placement="intent_explore"><span>04</span><h3>Explore</h3><p>Travel by geography, habitat, season, and local time.</p><strong>Open the living map →</strong></AnalyticsLink>
        </div>
      </section>

      <section className="editorial-section" aria-labelledby="featured-heading">
        <div className="section-heading"><p className="eyebrow">Editorial</p><h2 id="featured-heading">Featured sessions</h2></div>
        {featuredSessions === null ? (
          <p className="unavailable-state" role="alert">Featured sessions are temporarily unavailable. Please try again soon.</p>
        ) : featuredSessions.length > 0 ? (
          <div className="panel featured-grid">
            {featuredSessions.map((session: FeaturedSession) => (
              <article key={session.id}><span>{session.location.habitat ?? "Field recording"}</span><h3><Link href={`/sessions/${session.slug}`}>{session.title}</Link></h3><p>{session.location.name}</p></article>
            ))}
          </div>
        ) : <p className="empty-state">Featured sessions will appear once editorial curation is published.</p>}
      </section>

      <section className="editorial-section" id="collections" aria-labelledby="collections-heading">
        <div className="section-heading"><p className="eyebrow">Collections</p><h2 id="collections-heading">Atlas journeys</h2></div>
        {collections === null ? (
          <p className="unavailable-state" role="alert">Collections are temporarily unavailable. Please try again soon.</p>
        ) : collections.length > 0 ? (
          <div className="panel featured-grid">
            {collections.map((collection: CollectionSummary) => (
              <article key={collection.id}><span>{collection.session_count} sessions</span><h3><Link href={`/collections/${collection.slug}`}>{collection.title}</Link></h3><p>{collection.description}</p></article>
            ))}
          </div>
        ) : <p className="empty-state">Collections are being curated for the public atlas.</p>}
      </section>

      <section className="conversion-section proof-section" aria-label="Atlas in numbers">
        <div className="section-heading conversion-heading"><p className="eyebrow">A growing archive</p><h2 id="proof-heading">Real places. Unbroken time.</h2></div>
        <div className="proof-grid">
          <div><strong>{featuredSessions?.length ?? "—"}</strong><span>featured continuous field recordings</span></div>
          <div><strong>{collections?.length ?? "—"}</strong><span>curated journeys available today</span></div>
          <div><strong>0</strong><span>generated soundscapes or invented fallback recordings</span></div>
        </div>
        <p className="proof-note">Counts reflect the live public catalogue shown on this page. Sensitive locations are generalized or hidden.</p>
      </section>

      <section className="conversion-section story-section" aria-label="Listener stories">
        <div className="section-heading conversion-heading"><p className="eyebrow">Made for deep listening</p><h2 id="stories-heading">A place for the moments between everything else.</h2></div>
        <div className="story-grid">
          <article><span>For focused work</span><h3>Stay with one landscape.</h3><p>Choose a long session with minimal human noise instead of switching between short tracks.</p></article>
          <article><span>For an evening reset</span><h3>Let natural time set the pace.</h3><p>Follow a real recording from darkness into first light, without edits that hurry the moment.</p></article>
          <article><span>For curious listeners</span><h3>Hear the context, not only the chorus.</h3><p>Explore habitat, local time, listening notes, and detected bird activity alongside the recording.</p></article>
        </div>
      </section>

      <section className="conversion-section membership-comparison" aria-label="Membership comparison">
        <div className="section-heading conversion-heading"><p className="eyebrow">Choose your access</p><h2 id="comparison-heading">Begin freely. Go deeper as a member.</h2></div>
        <div className="comparison-table-wrap"><table>
          <thead><tr><th scope="col">Access</th><th scope="col">Free</th><th scope="col">Member</th></tr></thead>
          <tbody>
            <tr><th scope="row">Explore the public atlas</th><td><span aria-label="Included">✓</span></td><td><span aria-label="Included">✓</span></td></tr>
            <tr><th scope="row">Public listening previews</th><td><span aria-label="Included">✓</span></td><td><span aria-label="Included">✓</span></td></tr>
            <tr><th scope="row">Complete long-form sessions</th><td>Selected sessions</td><td><span aria-label="Included">✓</span></td></tr>
            <tr><th scope="row">Members-only recordings</th><td>—</td><td><span aria-label="Included">✓</span></td></tr>
            <tr><th scope="row">Protected playback access</th><td>—</td><td><span aria-label="Included">✓</span></td></tr>
          </tbody>
        </table></div>
      </section>

      <section className="conversion-section pricing-section" aria-labelledby="pricing-heading">
        <div><p className="eyebrow">ORNA membership</p><h2 id="pricing-heading">One membership. The complete atlas.</h2><p>Unlock entitled sessions and help sustain a careful, place-first archive of the living planet.</p><ul><li>Complete members-only listening</li><li>Secure playback across the catalogue</li><li>Cancel before any future renewal</li></ul></div>
        <div className="price-card"><p className="eyebrow">Early member access</p><strong>No charge to join</strong><p>Create a free account to reserve early access. Pricing is announced before payment, and ORNA Atlas does not currently initiate checkout on this page.</p><AnalyticsLink destination="/membership?mode=register" eventName="membership_cta_clicked" placement="pricing_card">Join early access</AnalyticsLink><small>No invented discount, countdown, or hidden checkout step.</small></div>
      </section>

      <section className="conversion-section faq-section" aria-label="Frequently asked questions">
        <div className="section-heading conversion-heading"><p className="eyebrow">Questions</p><h2 id="faq-heading">Know what you are hearing.</h2></div>
        <div className="faq-list">
          <details><summary>Are these sounds generated by AI?</summary><p>No. ORNA Atlas presents field recordings anchored to real landscapes. Automated analysis may annotate bird activity, but it does not generate the recording.</p></details>
          <details><summary>What is included without membership?</summary><p>You can explore the public atlas, collections, and available public sessions. A membership entitlement unlocks recordings marked for members.</p></details>
          <details><summary>Why are some coordinates hidden?</summary><p>Exact locations can put sensitive habitats or species at risk. Public views use generalized coordinates or omit a location when protection requires it.</p></details>
          <details><summary>Are the sessions loops or playlists?</summary><p>No. Sessions preserve the continuity and pace of field recordings instead of assembling short ambient loops.</p></details>
          <details><summary>Can I buy a membership here today?</summary><p>Account and entitlement support is live. Checkout and public subscription pricing are not yet offered on this page, so we do not present a fictional price or payment flow.</p></details>
        </div>
        <div className="closing-cta"><p>Start with a place. Stay for the whole horizon.</p><AnalyticsLink destination="/atlas" eventName="final_cta_clicked" placement="footer_atlas">Explore the atlas</AnalyticsLink><AnalyticsLink destination="/membership?mode=register" eventName="final_cta_clicked" placement="footer_membership">Join early access</AnalyticsLink></div>
      </section>
      </main>
    </div>
  );
}
