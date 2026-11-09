import { SommelierChat } from "@/components/SommelierChat";

export default function Home() {
  return (
    <section className="max-w-3xl">
      <h1 className="h-page">Ask the Head Sommelier</h1>
      <p className="lead">
        CopilotKit AG-UI chat streams the same Deep Agent. Specialists still render A2UI in the well.
      </p>
      <div className="mt-4">
        <SommelierChat />
      </div>
    </section>
  );
}
