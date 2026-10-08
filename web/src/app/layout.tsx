import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DeliveryOS — clear decisions for delivered work",
  description: "Agree on work, submit public commit-pinned evidence, and get a GenLayer-backed acceptance or revision decision. Decisions first, payments later.",
  openGraph: {
    title: "DeliveryOS",
    description: "From deliverable to decision. A neutral, agent-ready delivery protocol on GenLayer Studionet.",
    type: "website",
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
