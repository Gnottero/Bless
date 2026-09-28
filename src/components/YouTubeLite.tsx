"use client";

import { useState } from "react";
import styles from "./YouTubeLite.module.css";

/**
 * Lightweight YouTube embed. Shows a thumbnail and only loads the real
 * iframe (and YouTube's cookies) once you click play.
 */
export default function YouTubeLite({
  id,
  title,
}: {
  id: string;
  title: string;
}) {
  const [active, setActive] = useState(false);

  return (
    <div className={styles.frame}>
      {active ? (
        <iframe
          className={styles.iframe}
          src={`https://www.youtube-nocookie.com/embed/${id}?autoplay=1&rel=0`}
          title={title}
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
        />
      ) : (
        <button type="button" className={styles.facade} onClick={() => setActive(true)}>
          {/* YouTube's own thumbnail, lazy loaded. */}
          <img
            src={`https://i.ytimg.com/vi/${id}/hqdefault.jpg`}
            alt=""
            loading="lazy"
            decoding="async"
            width={480}
            height={360}
          />
          <span className={styles.play} aria-hidden="true">
            <svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor">
              <path d="M8 5.5v13l11-6.5-11-6.5Z" />
            </svg>
          </span>
          <span className={styles.label}>
            Guarda «{title}»
            <span className={styles.subtitle}>
              Il video parte su YouTube, dentro questa pagina
            </span>
          </span>
        </button>
      )}
    </div>
  );
}
