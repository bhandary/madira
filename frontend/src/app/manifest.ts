import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Madira",
    short_name: "Madira",
    description: "Maison Madira beverage program. Tonight's briefing, floor lookup, and open counts stay on the phone.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#0d1738",
    theme_color: "#122054",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
    ],
  };
}
