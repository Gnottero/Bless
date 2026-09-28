/**
 * Renders a JSON-LD script tag. `<` is escaped to `\u003c` so a string
 * containing `</script>` can't close the tag early.
 */
export default function JsonLd({ data }: { data: object }) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{
        __html: JSON.stringify(data).replace(/</g, "\\u003c"),
      }}
    />
  );
}
