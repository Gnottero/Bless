import type { MetadataRoute } from "next";
import { CARDS } from "@/data/cards";
import { SITE } from "@/lib/site";

/* Indexable pages only. The legal pages are `noindex` for now and Search
   Console complains about noindex URLs in the sitemap. Once the texts are
   in, remove the `noindex` and add them here.

   No `lastModified` either: it would just be the build date for every page,
   and search engines ignore dates they can't trust. */
export default function sitemap(): MetadataRoute.Sitemap {
  const staticPages: MetadataRoute.Sitemap = [
    { url: SITE.url, changeFrequency: "monthly", priority: 1 },
    { url: `${SITE.url}/gioco`, changeFrequency: "weekly", priority: 0.9 },
    { url: `${SITE.url}/database`, changeFrequency: "monthly", priority: 0.8 },
    { url: `${SITE.url}/rules`, changeFrequency: "monthly", priority: 0.8 },
  ];

  const cardPages: MetadataRoute.Sitemap = CARDS.map((c) => ({
    url: `${SITE.url}/database/${c.id}`,
    changeFrequency: "yearly",
    priority: 0.6,
  }));

  return [...staticPages, ...cardPages];
}
