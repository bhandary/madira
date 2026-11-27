/**
 * The Zod schemas stay the runtime validators. These aliases fail `tsc` when a
 * schema and the generated API type stop describing the same fields.
 */

import { approvalInvite, approvalListVersion, approvalPurchaseOrder, approvalRecord } from "@/a2ui/approvalCardSchema";
import { auditChain, auditEvent } from "@/a2ui/auditTableSchema";
import { auditorTable } from "@/a2ui/auditorTableSchema";
import { briefingPayload } from "@/a2ui/briefingCardsSchema";
import { countLine, countSession } from "@/a2ui/countSheetSchema";
import { coverageCell } from "@/a2ui/coverageGridSchema";
import { dishReviewValue } from "@/a2ui/dishReviewSchema";
import { lookupHit, lookupPayload } from "@/a2ui/floorLookupSchema";
import { lessonPayload } from "@/a2ui/lessonCardSchema";
import { candidate, type EditorCandidate, type EditorItem, type EditorSection } from "@/a2ui/listEditorSchema";
import { pairingDish, type PairingDish as ZodPairingDish, type PairingOption as ZodPairingOption, type PairingSlot as ZodPairingSlot } from "@/a2ui/pairingGridSchema";
import { posStatus, unmappedPosItem } from "@/a2ui/posSchema";
import { priceHistoryProduct, pricePoint } from "@/a2ui/priceHistorySchema";
import { quizPayload } from "@/a2ui/quizCardSchema";
import { receivingLine, receivingPurchaseOrder, receivingReceipt } from "@/a2ui/receivingChecklistSchema";
import { roleplaySession } from "@/a2ui/roleplayPanelSchema";
import { sampleCard } from "@/a2ui/sampleCardSchema";
import { reminderItem, sensorStatusItem } from "@/a2ui/sensorSchema";
import { repFollowup, sourcingBrief, tastingHistory } from "@/a2ui/sourcingSchema";
import { supplierOffer } from "@/a2ui/supplierOffersSchema";
import { conflictReading, countConflict, varianceLine, varianceReport } from "@/a2ui/varianceReportSchema";
import { affectedSku, zoneCondition, zoneExcursion, zoneReading } from "@/a2ui/zoneConditionCardSchema";
import type { z } from "zod/v3";

import type {
  AffectedSku,
  AuditChain,
  AuditEventRow,
  AuditorTable,
  CountConflict,
  CountLineRecord,
  CountReading,
  CountReport,
  CountSessionRecord,
  CoverageCell,
  ListCandidate,
  ListItemRecord,
  ListSectionRecord,
  ListVersionRecord,
  LookupHit,
  LookupResult,
  MenuReview,
  OfferRecord,
  RepFollowup,
  PairingDish,
  PairingOption,
  PairingSlot,
  PosGapItem,
  PosStatus,
  PricePointRecord,
  PriceProduct,
  PurchaseApproval,
  PurchaseOrderRow,
  ReceiptLineRecord,
  ReceiptRecord,
  ReminderRecord,
  RoleplaySession,
  SampleCard,
  SensorRecord,
  SourcingBrief,
  StorageZone,
  TastingHistory,
  TastingInvite,
  TonightBriefing,
  TrainingLesson,
  TrainingQuiz,
  VarianceLine,
  ZoneExcursion,
  ZoneReading,
} from "./api-types.gen";

type Equal<X, Y> = (<T>() => T extends X ? 1 : 2) extends <T>() => T extends Y ? 1 : 2 ? true : false;

type Expect<T extends true> = T;

type Out<T extends z.ZodTypeAny> = z.infer<T>;

type Bare<T> = Exclude<T, null | undefined>;

/**
 * Shared fields must agree. A card may omit a stored field or mark it optional,
 * and it may carry a binding the response model does not publish.
 */
type SameDeep<Card, Api> = [Bare<Card>] extends [Bare<Api>]
  ? true
  : [Bare<Card>] extends [readonly (infer Item)[]]
    ? [Bare<Api>] extends [readonly (infer ApiItem)[]]
      ? SameDeep<Item, ApiItem>
      : false
    : [Bare<Card>] extends [object]
      ? [Bare<Api>] extends [object]
        ? false extends {
            [K in keyof Bare<Card> & keyof Bare<Api>]: SameDeep<Bare<Card>[K], Bare<Api>[K]>;
          }[keyof Bare<Card> & keyof Bare<Api>]
          ? false
          : true
        : false
      : false;

export type ApiTypeChecks = [
  Expect<Equal<ZodPairingDish, PairingDish>>,
  Expect<Equal<ZodPairingSlot, PairingSlot>>,
  Expect<Equal<ZodPairingOption, PairingOption>>,
  Expect<Equal<Out<typeof pairingDish>, PairingDish>>,
  Expect<Equal<Out<typeof dishReviewValue>, MenuReview>>,
  Expect<Equal<Out<typeof sampleCard>, SampleCard>>,
  Expect<Equal<Out<typeof roleplaySession>, RoleplaySession>>,
  Expect<Equal<Out<typeof sourcingBrief>, SourcingBrief>>,
  Expect<Equal<Out<typeof repFollowup>, RepFollowup>>,
  Expect<Equal<Out<typeof tastingHistory>, TastingHistory>>,
  Expect<Equal<Out<typeof auditEvent>, AuditEventRow>>,
  Expect<Equal<Out<typeof auditChain>, AuditChain>>,
  Expect<Equal<Out<typeof auditorTable>, AuditorTable>>,
  Expect<Equal<Out<typeof lookupHit>, LookupHit>>,
  Expect<Equal<Out<typeof pricePoint>, PricePointRecord>>,
  Expect<Equal<Out<typeof priceHistoryProduct>, PriceProduct>>,
  Expect<Equal<Out<typeof coverageCell>, CoverageCell>>,
  Expect<Equal<Out<typeof affectedSku>, AffectedSku>>,
  Expect<Equal<Out<typeof briefingPayload>, TonightBriefing>>,
  Expect<Equal<Out<typeof unmappedPosItem>, PosGapItem>>,
  Expect<Equal<Out<typeof supplierOffer>, OfferRecord>>,
  Expect<SameDeep<Out<typeof lookupPayload>, LookupResult>>,
  Expect<SameDeep<Out<typeof posStatus>, PosStatus>>,
  Expect<SameDeep<Out<typeof quizPayload>, TrainingQuiz>>,
  Expect<SameDeep<Out<typeof lessonPayload>, TrainingLesson>>,
  Expect<SameDeep<EditorItem, ListItemRecord>>,
  Expect<SameDeep<EditorSection, ListSectionRecord>>,
  Expect<SameDeep<EditorCandidate, ListCandidate>>,
  Expect<SameDeep<Out<typeof candidate>, ListCandidate>>,
  Expect<SameDeep<Out<typeof sensorStatusItem>, SensorRecord>>,
  Expect<SameDeep<Out<typeof reminderItem>, ReminderRecord>>,
  Expect<SameDeep<Out<typeof zoneCondition>, StorageZone>>,
  Expect<SameDeep<Out<typeof zoneReading>, ZoneReading>>,
  Expect<SameDeep<Out<typeof zoneExcursion>, ZoneExcursion>>,
  Expect<SameDeep<Out<typeof countSession>, CountSessionRecord>>,
  Expect<SameDeep<Out<typeof countLine>, CountLineRecord>>,
  Expect<SameDeep<Out<typeof varianceLine>, VarianceLine>>,
  Expect<SameDeep<Out<typeof countConflict>, CountConflict>>,
  Expect<SameDeep<Out<typeof conflictReading>, CountReading>>,
  Expect<SameDeep<Out<typeof varianceReport>, CountReport>>,
  Expect<SameDeep<Out<typeof approvalRecord>, PurchaseApproval>>,
  Expect<SameDeep<Out<typeof approvalPurchaseOrder>, PurchaseOrderRow>>,
  Expect<SameDeep<Out<typeof approvalListVersion>, ListVersionRecord>>,
  Expect<SameDeep<Out<typeof approvalInvite>, TastingInvite>>,
  Expect<SameDeep<Out<typeof receivingLine>, ReceiptLineRecord>>,
  Expect<SameDeep<Out<typeof receivingReceipt>, ReceiptRecord>>,
  Expect<SameDeep<Out<typeof receivingPurchaseOrder>, PurchaseOrderRow>>,
];
