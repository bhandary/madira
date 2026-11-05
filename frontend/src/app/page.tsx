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
    <div className="max-w-3xl">
      <p className="kicker">Head Sommelier desk</p>
      <h1 className="mt-2 h-page">The floor program, delegated.</h1>
      <p className="lead">
        Madira is a Deep Agents orchestrator for restaurants. Six specialists sit behind one Head Sommelier.
        They speak A2UI — pairing cards, margin tables, quizzes — not walls of chat.
      </p>
      <ul className="panel mt-6 divide-y divide-line">
        {CARDS.map((card) => (
          <li key={card.href}>
            <Link href={card.href} className="desk-link">
              <h2 className="text-sm font-medium">{card.title}</h2>
              <p className="mt-1 text-sm leading-5 text-muted">{card.body}</p>
            </Link>
          </li>
        ))}
      </ul>
      <section className="mt-8">
        <h2 className="text-base font-medium">Ask the Head Sommelier</h2>
        <p className="mb-3 mt-1 text-sm text-muted">
          CopilotKit AG-UI chat streams the same Deep Agent. Specialists still render A2UI in the well.
        </p>
        <SommelierChat />
      </section>
    </div>
  );
}
