/** Catalog definitions shared with CopilotKit's createCatalog (Zod-shaped, serialisable). */

export const MADIRA_CATALOG_ID = "madira://beverage-catalog";

export const catalogDefinitions = {
  PairingGrid: {
    description: "Pairing cards for each dish across wine, beer, spirit, and sake.",
    props: { dishes: "array of dish pairing objects" },
  },
  DishList: {
    description: "Parsed dishes with flavor profiles.",
    props: { dishes: "array" },
  },
  BeverageListTable: {
    description: "Curated list with cost, pour, bottle, and margin.",
    props: { items: "array" },
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
    description: "Training quiz with scoring.",
    props: { quiz: "object" },
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
};
