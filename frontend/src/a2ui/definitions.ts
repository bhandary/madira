/** Catalog definitions shared with CopilotKit's createCatalog (Zod-shaped, serialisable). */

export const MADIRA_CATALOG_ID = "madira://beverage-catalog";

export const catalogDefinitions = {
  PairingGrid: {
    description:
      "Four pairing slots per dish — best by the glass, best bottle, a value pick, and an adventurous pick — with pin, swap, and reject.",
    props: { menu_id: "string", dishes: "array of dish pairing objects" },
  },
  DishList: {
    description: "Parsed dishes with flavor profiles.",
    props: { dishes: "array" },
  },
  DishReview: {
    description: "Dishes read from a menu, with low-confidence fields flagged. Edit a field and confirm the menu.",
    props: {
      review: "menu id, version id, name, status, and dishes with per-field confidence",
    },
  },
  BeverageListTable: {
    description: "Curated list with cost, pour, bottle, and margin.",
    props: { items: "array" },
  },
  ListEditor: {
    description: "List sections and bottles, with reprice, reorder, remove, and add from cellar candidates.",
    props: {
      listId: "string",
      currency: "string",
      sections: "array of sections",
      items: "array of list items",
      candidates: "array of cellar candidates",
    },
  },
  CoverageGrid: {
    description: "Coverage matrix of category, style, and price band. Unfilled cells are buying suggestions.",
    props: { cells: "array of coverage cells" },
  },
  ListSummary: {
    description: "Budget, spend, coverage, and gaps.",
    props: { budget: "number", spent: "number", remaining: "number", targetMargin: "number", coverage: "object", gaps: "array" },
  },
  InventoryTable: {
    description: "Stock, par, depletion.",
    props: { items: "array" },
  },
  StockAlerts: {
    description: "Low-stock alerts.",
    props: { alerts: "array" },
  },
  PurchaseOrderTable: {
    description: "Draft purchase orders by supplier.",
    props: { orders: "array" },
  },
  QuizCard: {
    description: "Training quiz. The score and the next review date come from the quiz service.",
    props: { quiz: "object" },
  },
  LessonCard: {
    description: "One role lesson. Approve and edit are for authors. Citations are standards and bottles, never prices.",
    props: { lesson: "object" },
  },
  LessonCards: {
    description: "Staff lessons and daily briefing.",
    props: { lessons: "array" },
  },
  ScheduleForm: {
    description: "Draft tasting details and .ics.",
    props: { draft: "object" },
  },
  TastingCalendar: {
    description: "Calendar of supplier tastings.",
    props: { tastings: "array" },
  },
  TastingNoteCard: {
    description: "Tasting note with a server hook, guest description, technical note, and flavor profile.",
    props: { note: "tasting note" },
  },
  ServiceCard: {
    description: "Service card with serving temperature, glassware, decanting, and pour size.",
    props: { card: "service card" },
  },
  AuditTable: {
    description: "Hash-chained audit events with chain integrity, actor, action, and before/after values.",
    props: {
      events: "audit events with seq, action, entity, before and after, and hashes",
      chain: "valid, checked count, head hash, and the first broken event",
    },
  },
  CountSheet: {
    description: "Phone count lines for one location, including device, quantity, and bin.",
    props: {
      session: "count session id, status, and location",
      lines: "counted lines with sku, quantity, device, and time",
    },
  },
  VarianceReport: {
    description: "Expected versus counted quantity, dollar impact, and multi-device conflicts.",
    props: {
      report: "session, variance lines, and conflict readings",
    },
  },
  ApprovalCard: {
    description: "Owner approval for a purchase order, with comment, approve, and reject.",
    props: {
      purchaseOrder: "purchase order number, supplier, totals, and delivery date",
      approval: "pending, approved, or rejected owner decision",
    },
  },
  ReceivingChecklist: {
    description: "Counted delivery against a purchase order and invoice, with short, over, vintage, and price flags.",
    props: {
      purchaseOrder: "purchase order being received",
      receipt: "staged receipt and discrepancy summary",
      lines: "counted lines with ordered, invoiced, and received quantities",
    },
  },
  ZoneConditionCard: {
    description: "Storage zone target temperature and humidity, the latest reading, and an excursion with affected SKUs.",
    props: {
      zone: "zone name, targets, latest reading, status, and excursion",
    },
  },
};
