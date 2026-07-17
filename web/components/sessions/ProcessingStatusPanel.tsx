import type { MediaAssetRead } from "../../lib/api/sessions";

export function ProcessingStatusPanel({
  status,
  assets,
}: {
  status: string;
  assets: MediaAssetRead[];
}) {
  const sourceAssets = assets.filter((asset) => asset.kind !== "streaming_rendition");
  const renditions = assets.filter((asset) => asset.kind === "streaming_rendition");

  return (
    <details className="processing-panel processing-details">
      <summary aria-label="Show technical details">
        <span><strong>Recording {formatStatus(status)}</strong><small>Technical details</small></span>
      </summary>
      <dl className="processing-grid">
        <div>
          <dt>Source assets</dt>
          <dd>{sourceAssets.length}</dd>
        </div>
        <div>
          <dt>Streaming renditions</dt>
          <dd>{renditions.length}</dd>
        </div>
        <div>
          <dt>Session status</dt>
          <dd>{formatStatus(status)}</dd>
        </div>
      </dl>
      {assets.length > 0 ? (
        <ol className="asset-list">
          {assets.map((asset) => (
            <li key={asset.id}>
              <strong>{asset.kind}</strong>
              <span>{formatStatus(asset.processing_status)}</span>
            </li>
          ))}
        </ol>
      ) : null}
    </details>
  );
}

function formatStatus(value: string) {
  return value.replaceAll("_", " ");
}
