import Link from "next/link";
import { SommelierChat } from "@/components/SommelierChat";

const CARDS = [
  {
    href: "/menu",
    title: "Menu & pairings",
    body: "Upload a menu. Menu Analyst parses dishes; Pairing Sommelier returns wine, beer, spirit, and sake cards.",
  },
  {
    href: "/list",
    title: "List curation",
    body: "State a buying budget and pour margin. List Curator fills gaps by category, region, and style.",
  },
  {
    href: "/inventory",
    title: "Inventory",
    body: "Par levels, depletion, low-stock alerts, draft purchase orders. Nothing is transmitted.",
  },
  {
    href: "/training",
    title: "Staff training",
    body: "Service etiquette, tonight's briefing, scored quizzes, and diner roleplay.",
  },
  {
    href: "/suppliers",
    title: "Supplier tastings",
    body: "Hold a cellar tasting with an importer. Export .ics. No email, no invite.",
  },
];

export default function Home() {
  return (
    <div>
      <p className="demo-ribbon text-xs text-burgundy">Head Sommelier desk</p>
      <h1 className="mt-2 max-w-3xl font-serif text-5xl leading-tight">
        The floor program, delegated.
      </h1>
      <p className="mt-4 max-w-2xl text-lg text-[#5c4c3c]">
        Madira is a Deep Agents orchestrator for restaurants. Six specialists sit behind one Head Sommelier.
        They speak A2UI — pairing cards, margin tables, quizzes — not walls of chat.
      </p>
      <div className="mt-8 grid gap-4 md:grid-cols-2">
        {CARDS.map((card) => (
          <Link
            key={card.href}
            href={card.href}
            className="rounded-2xl border border-gold/40 bg-white/70 p-5 transition hover:border-burgundy"
          >
            <h2 className="font-serif text-2xl">{card.title}</h2>
            <p className="mt-2 text-sm leading-6 text-[#5c4c3c]">{card.body}</p>
          </Link>
        ))}
      </div>
      <section className="mt-10">
        <h2 className="font-serif text-3xl">Ask the Head Sommelier</h2>
        <p className="mb-3 text-sm text-[#5c4c3c]">
          CopilotKit AG-UI chat streams the same Deep Agent. Specialists still render A2UI in the well.
        </p>
        <SommelierChat />
      </section>
    </div>
  );
}
