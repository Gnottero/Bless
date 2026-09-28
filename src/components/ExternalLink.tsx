import { NEW_TAB_NOTE } from "@/lib/site";

/**
 * Opens in a new tab and tells screen readers about it. If you want a
 * visible arrow icon, add it yourself.
 */
export default function ExternalLink({
  href,
  className,
  children,
}: {
  href: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={className}>
      {children}
      <span className="sr-only"> {NEW_TAB_NOTE}</span>
    </a>
  );
}
