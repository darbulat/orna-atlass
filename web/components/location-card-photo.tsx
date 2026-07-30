/* eslint-disable @next/next/no-img-element -- location photos are data-driven remote URLs; next/image requires a static host allowlist. */

type LocationCardPhotoProps = {
  name: string;
  photoUrl: string | null | undefined;
  variant: "atlas" | "popular";
};

export function LocationCardPhoto({ name, photoUrl, variant }: LocationCardPhotoProps) {
  return (
    <span className={`location-card-photo location-card-photo-${variant}`}>
      {photoUrl ? (
        <img
          src={photoUrl}
          alt={`Landscape at ${name}`}
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          onError={(event) => {
            event.currentTarget.hidden = true;
          }}
        />
      ) : null}
    </span>
  );
}
