export default function CollectionPage({ params }: { params: { slug: string } }) {
  return <main className="shell"><p className="eyebrow">Collection</p><h1>{params.slug}</h1><p>Collection placeholder for editorial atlas journeys.</p></main>;
}
