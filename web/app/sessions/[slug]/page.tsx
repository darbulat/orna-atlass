export default function SessionPage({ params }: { params: { slug: string } }) {
  return <main className="shell"><p className="eyebrow">Session</p><h1>{params.slug}</h1><p>Session detail placeholder for upcoming audio foundation work.</p></main>;
}
