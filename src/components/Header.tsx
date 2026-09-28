"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { NAV } from "@/lib/site";
import SocialLinks from "./SocialLinks";
import styles from "./Header.module.css";

function isActive(href: string, pathname: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavLinks({
  pathname,
  itemClass,
  withHome = true,
}: {
  pathname: string;
  itemClass: string;
  withHome?: boolean;
}) {
  const links = withHome ? NAV : NAV.filter((v) => v.href !== "/");
  return links.map((v) => {
    const active = isActive(v.href, pathname);
    return (
      <li key={v.href}>
        <Link
          href={v.href}
          className={`${itemClass} ${active ? styles.active : ""}`}
          aria-current={active ? "page" : undefined}
        >
          {v.label}
        </Link>
      </li>
    );
  });
}

export default function Header() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => setOpen(false), [pathname]);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <header className={`${styles.header} ${scrolled ? styles.scrolled : ""}`}>
      <div className={styles.inner}>
        <Link href="/" className={styles.logo} aria-label="Bless — vai alla home">
          <Image
            src="/logo.png"
            alt="Bless"
            width={351}
            height={101}
            sizes="118px"
            priority={pathname === "/"}
          />
        </Link>

        <nav className={styles.nav} aria-label="Navigazione principale">
          {/* The logo already links home, so no Home link on desktop. */}
          <ul className={styles.navList}>
            <NavLinks pathname={pathname} itemClass={styles.navItem} withHome={false} />
          </ul>
        </nav>

        <div className={styles.actions}>
          <Link href="/gioco" className={`btn btn--sm ${styles.cta}`}>
            Gioca gratis
          </Link>
          <button
            type="button"
            className={styles.burger}
            aria-expanded={open}
            aria-controls="mobile-menu"
            onClick={() => setOpen((v) => !v)}
          >
            <span>{open ? "Chiudi" : "Menu"}</span>
          </button>
        </div>
      </div>

      <div id="mobile-menu" className={styles.mobile} hidden={!open}>
        <ul className={styles.mobileList}>
          <NavLinks pathname={pathname} itemClass={styles.mobileItem} />
        </ul>
        <SocialLinks />
      </div>
    </header>
  );
}
