import { BentoLink } from "@/components/BentoLink";
import { SommelierChat } from "@/components/SommelierChat";

const SECTIONS = [
  {
    href: "/menu",
    title: "Menu & pairings",
    body: "Parse a menu and read wine, beer, spirit, and sake cards for each dish.",
  },
  {
    href: "/inventory",
    title: "Cellar",
    body: "Check on-hand against par, then draft purchase orders that stay unsent.",
  },
  {
    href: "/list",
    title: "List",
    body: "Build the beverage list to a cellar budget and a target multiple.",
  },
  {
    href: "/training",
    title: "Team",
    body: "Role lessons, a quiz from the list, and reviews that come back on a schedule.",
  },
];

export default function Home() {
  return (
    <section>
      <div className="hero">
        <div className="wave-accent" aria-hidden="true" />
        <p className="kicker">Maison Madira · beverage program</p>
        <h1 className="hero-title mt-3">Ask the Head Sommelier</h1>
        <p className="hero-copy">
          <span>CopilotKit AG-UI chat streams the same Deep Agent.</span>{" "}
          <span className="hero-copy-sub">Specialists still render A2UI in the well.</span>
        </p>
      </div>
      <div className="mt-8 grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_17.5rem]">
        <SommelierChat />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
          {SECTIONS.map((section) => (
            <BentoLink key={section.href} {...section} />
          ))}
        </div>
      </div>
    </section>
  );
}
