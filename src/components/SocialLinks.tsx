import { NEW_TAB_NOTE, SOCIAL, type SocialName } from "@/lib/site";
import styles from "./SocialLinks.module.css";

const ICONS: Record<SocialName, React.ReactNode> = {
  Instagram: (
    <>
      <rect x="3" y="3" width="18" height="18" rx="5" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="17.2" cy="6.8" r="1.2" fill="currentColor" stroke="none" />
    </>
  ),
  X: (
    <path
      d="M3.2 3h4.4l4.2 5.7L16.9 3h3.9l-6.7 7.8L21.2 21h-4.4l-4.6-6.2L6.8 21H2.9l7.1-8.3L3.2 3Z"
      fill="currentColor"
      stroke="none"
    />
  ),
  TikTok: (
    <path
      d="M14.2 2h2.9c.2 1.6 1.1 3 2.5 3.7.7.4 1.5.6 2.3.6v2.9a8 8 0 0 1-4.7-1.6v6.6a6.2 6.2 0 1 1-6.2-6.2c.3 0 .6 0 .9.1v3a3.3 3.3 0 1 0 2.3 3.1V2Z"
      fill="currentColor"
      stroke="none"
    />
  ),
  Discord: (
    <path
      d="M19.3 5.4A16.4 16.4 0 0 0 15.2 4l-.3.6c-1.9-.3-3.8-.3-5.7 0L8.9 4a16.4 16.4 0 0 0-4.2 1.4C2.1 9.3 1.4 13.1 1.8 16.8A16.6 16.6 0 0 0 6.8 19l1-1.6c-.6-.2-1.1-.5-1.6-.8l.4-.3a11.8 11.8 0 0 0 10.9 0l.4.3c-.5.3-1.1.6-1.7.8l1 1.6a16.6 16.6 0 0 0 5-2.2c.5-4.3-.6-8.1-2.9-11.4ZM8.6 14.6c-1 0-1.8-.9-1.8-2s.8-2 1.8-2 1.8.9 1.8 2-.8 2-1.8 2Zm6.8 0c-1 0-1.8-.9-1.8-2s.8-2 1.8-2 1.8.9 1.8 2-.8 2-1.8 2Z"
      fill="currentColor"
      stroke="none"
    />
  ),
};

export default function SocialLinks() {
  return (
    <ul className={styles.list}>
      {SOCIAL.map((s) => (
        <li key={s.name}>
          <a
            href={s.href}
            aria-label={`${s.label} ${NEW_TAB_NOTE}`}
            target="_blank"
            rel="noopener noreferrer"
            className={styles.link}
          >
            <svg
              viewBox="0 0 24 24"
              width="20"
              height="20"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
              focusable="false"
            >
              {ICONS[s.name]}
            </svg>
          </a>
        </li>
      ))}
    </ul>
  );
}
