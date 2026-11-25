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
  RoleplayPanel: {
    description: "A guest roleplay with the service-written score and rubric.",
    props: { session: "object" },
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
  BriefingCards: {
    description: "Tonight's pre-shift card stack. The push reason is in words. Staff do not see cost or margin.",
    props: { briefing: "object" },
  },
  FloorLookup: {
    description: "Floor lookup for a dish, a bottle, or a guest preference. Pairing, script, glassware, temperature, pour, and stock.",
    props: { lookup: "object" },
  },
  ScheduleForm: {
    description: "Draft tasting details and .ics.",
    props: { draft: "object" },
  },
  TastingCalendar: {
    description: "Calendar of supplier tastings.",
    props: { tastings: "array" },
  },
  SampleCard: {
    description: "One tasting sample: label scan, score, list price and margin, the dishes it pairs with, and buy, list, or pass.",
    props: { sample: "sample card" },
  },
  SourcingBrief: {
    description: "Want list from list gaps: category, style, price band, quantity, dishes, and a rationale.",
    props: { brief: "sourcing brief" },
  },
  RepFollowup: {
    description: "Unsent draft note to a supplier rep, with the purchase order reference filled in by the service.",
    props: { followup: "rep follow-up draft" },
  },
  PosStatus: {
    description: "POS connection for this venue. The access token is not shown.",
    props: { status: "provider, location, masked token, and last sync" },
  },
  UnmappedPos: {
    description: "POS items that sold without a SKU mapping.",
    props: { items: "array of unmapped POS items" },
  },
  SensorStatus: {
    description: "Sensor last reading and whether it is stale. The signing secret is not shown.",
    props: { sensors: "array of sensor status rows" },
  },
  ReminderList: {
    description: "Open in-app reminders for licenses and certificates. Nothing is sent.",
    props: { reminders: "array of reminder rows" },
  },
  TastingHistory: {
    description: "Tasted samples against bought purchase-order lines and invoice lines.",
    props: { history: "tasting history rows" },
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
    description: "Owner or Manager approval for a purchase order, a list publish, or a tasting invite, with comment, approve, and reject.",
    props: {
      purchaseOrder: "purchase order number, supplier, totals, and delivery date",
      approval: "pending, approved, or rejected decision",
      listVersion: "list version id, name, number, and status when the card is a list publish",
      invite: "tasting invite id, session, title, and status when the card is an invite",
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
  SupplierOffers: {
    description: "Current supplier offers. Each price is the service price_label.",
    props: {
      offers: "array of current offers with price_label, supplier, and validity",
      supplier: "supplier name when the list is filtered",
    },
  },
  PriceHistory: {
    description: "Dated offer and invoice costs for one product. Amounts are price_label from the service.",
    props: {
      product: "product id, name, and producer",
      points: "array of dated price points",
    },
  },
};
