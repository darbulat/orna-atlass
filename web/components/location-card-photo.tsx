import Image from "next/image";

type LocationCardPhotoProps = {
  name: string;
  photoUrl: string | null | undefined;
  variant: "atlas" | "popular";
};

export function LocationCardPhoto({ name, photoUrl, variant }: LocationCardPhotoProps) {
  return (
    <span className={`location-card-photo location-card-photo-${variant}`}>
      {photoUrl ? (
        <Image
          src={photoUrl}
          alt={`Landscape at ${name}`}
          fill
          sizes={variant === "atlas" ? "(max-width: 720px) 82vw, 320px" : "(max-width: 720px) 100vw, 33vw"}
          onError={(event) => {
            event.currentTarget.hidden = true;
          }}
        />
      ) : null}
    </span>
  );
}
