from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from madira.db import Base
from madira.money import DEFAULT_CURRENCY
from madira.timestamps import AwareDateTime

ROLES = ("Owner", "Sommelier", "Manager", "Staff", "Auditor")
INVITE_POSITIONS = ("server", "bartender", "barback", "host")
ROLEPLAY_PERSONAS = ("skeptic", "budget-conscious", "connoisseur", "celebration")
ROLEPLAY_STATUSES = ("open", "scored")
CERTIFICATE_KINDS = ("responsible_service", "food_handler", "other")


def _pk():
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def _fk(target: str, *, nullable: bool = False, index: bool = False):
    return mapped_column(Uuid, ForeignKey(target), nullable=nullable, index=index)


def _currency():
    return mapped_column(String(3), default=DEFAULT_CURRENCY, server_default=text("'USD'"))


def _stamp():
    return mapped_column(AwareDateTime, server_default=func.now())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    # Manju's approved default. The compliance service only accepts 1..25.
    document_retention_years: Mapped[int] = mapped_column(
        Integer, nullable=False, default=7, server_default=text("7")
    )
    # Null means the limit is off. Cents and requests are integers. There is no plan or invoice.
    monthly_spend_cap_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requests_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Venue(Base):
    __tablename__ = "venues"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_venues_org_slug"),
        CheckConstraint("invite_delivery IN ('draft_only')", name="ck_venues_invite_delivery"),
    )

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _fk("organizations.id", index=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80))
    currency: Mapped[str] = _currency()
    timezone: Mapped[str] = mapped_column(
        String(64), default="America/Los_Angeles", server_default=text("'America/Los_Angeles'")
    )
    briefing_hour: Mapped[int] = mapped_column(Integer, default=15, server_default=text("15"))
    invite_delivery: Mapped[str] = mapped_column(
        String(16), default="draft_only", server_default=text("'draft_only'")
    )
    # Launch market. Seeded reminder rules are chosen from this code.
    jurisdiction: Mapped[str] = mapped_column(
        String(16), default="US-CA", server_default=text("'US-CA'")
    )


class Membership(Base):
    """A user's role at one venue. The same person can belong to several venues."""

    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "venue_id", name="uq_memberships_user_venue"),
        CheckConstraint(
            "role IN ('Owner', 'Sommelier', 'Manager', 'Staff', 'Auditor')",
            name="ck_memberships_role",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _fk("users.id", index=True)
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    role: Mapped[str] = mapped_column(String(32))
    # Floor role for lessons: server, bartender, barback, or host. Empty for everyone else.
    position: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # scrypt string. Never the PIN itself.
    pin_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)
    pin_failures: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    pin_locked_until: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)


class SharedTablet(Base):
    """One browser signed in by an Owner or Manager and shared at a venue."""

    __tablename__ = "shared_tablets"
    __table_args__ = (CheckConstraint("pin_failures >= 0", name="ck_shared_tablets_pin_failures"),)

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _fk("organizations.id", index=True)
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    host_user_id: Mapped[uuid.UUID] = _fk("users.id", index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
    pin_failures: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    pin_locked_until: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    created_at: Mapped[datetime] = _stamp()
    disabled_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)


class TabletActor(Base):
    """The person currently using a shared tablet. Idle expiry is ``expires_at``."""

    __tablename__ = "tablet_actors"

    id: Mapped[uuid.UUID] = _pk()
    tablet_id: Mapped[uuid.UUID] = _fk("shared_tablets.id", index=True)
    organization_id: Mapped[uuid.UUID] = _fk("organizations.id", index=True)
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    user_id: Mapped[uuid.UUID] = _fk("users.id", index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(AwareDateTime)
    created_at: Mapped[datetime] = _stamp()


class Product(Base):
    """A drink in the organization catalog. Venues stock it as SKUs."""

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "category",
            "producer",
            "name",
            "region",
            "country",
            "style",
            "grape",
            name="uq_products_identity",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _fk("organizations.id", index=True)
    category: Mapped[str] = mapped_column(String(32), default="")
    producer: Mapped[str] = mapped_column(String(200), default="")
    name: Mapped[str] = mapped_column(String(200))
    region: Mapped[str] = mapped_column(String(200), default="")
    country: Mapped[str] = mapped_column(String(80), default="")
    style: Mapped[str] = mapped_column(String(200), default="")
    grape: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(String(32), default="")
    acidity: Mapped[str] = mapped_column(String(32), default="")
    tannin: Mapped[str] = mapped_column(String(32), default="")
    sweetness: Mapped[str] = mapped_column(String(32), default="")
    oak: Mapped[str] = mapped_column(String(32), default="")
    intensity: Mapped[str] = mapped_column(String(32), default="")
    aroma_families: Mapped[list] = mapped_column(JSON, default=list)
    variants: Mapped[list[ProductVariant]] = relationship(back_populates="product")


class ProductVariant(Base):
    """Vintage and bottle size of one product."""

    __tablename__ = "product_variants"
    __table_args__ = (
        UniqueConstraint("product_id", "vintage", "bottle_size", name="uq_product_variants_identity"),
    )

    id: Mapped[uuid.UUID] = _pk()
    product_id: Mapped[uuid.UUID] = _fk("products.id", index=True)
    vintage: Mapped[str] = mapped_column(String(32), default="")
    bottle_size: Mapped[str] = mapped_column(String(32), default="")
    drink_from_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    drink_by_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product: Mapped[Product] = relationship(back_populates="variants")
    skus: Mapped[list[Sku]] = relationship(back_populates="variant")


class Sku(Base):
    """One venue's stock identity for a variant: barcode, bin, par, and cost."""

    __tablename__ = "skus"
    __table_args__ = (
        UniqueConstraint("venue_id", "product_variant_id", name="uq_skus_venue_variant"),
        Index(
            "uq_skus_venue_barcode",
            "venue_id",
            "barcode",
            unique=True,
            sqlite_where=text("barcode != ''"),
            postgresql_where=text("barcode <> ''"),
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    product_variant_id: Mapped[uuid.UUID] = _fk("product_variants.id", index=True)
    barcode: Mapped[str] = mapped_column(String(64), default="")
    bin_label: Mapped[str] = mapped_column(String(200), default="")
    par: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = _currency()
    best_by: Mapped[date | None] = mapped_column(Date, nullable=True)
    eighty_sixed_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    eighty_sixed_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True, index=True)
    variant: Mapped[ProductVariant] = relationship(back_populates="skus")


class TastingNote(Base):
    """A venue's note for one product: three texts, a proposed profile, and an approval."""

    __tablename__ = "tasting_notes"
    __table_args__ = (
        CheckConstraint("source IN ('agent', 'staff')", name="ck_tasting_notes_source"),
        CheckConstraint("status IN ('draft', 'approved')", name="ck_tasting_notes_status"),
        CheckConstraint(
            "(status = 'draft' AND approved_by IS NULL AND approved_at IS NULL) OR "
            "(status = 'approved' AND approved_by IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_tasting_notes_approval",
        ),
        Index("ix_tasting_notes_venue_product", "venue_id", "product_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    product_id: Mapped[uuid.UUID] = _fk("products.id", index=True)
    server_hook: Mapped[str] = mapped_column(Text, default="")
    guest_description: Mapped[str] = mapped_column(Text, default="")
    technical_note: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(String(32), default="")
    acidity: Mapped[str] = mapped_column(String(32), default="")
    tannin: Mapped[str] = mapped_column(String(32), default="")
    sweetness: Mapped[str] = mapped_column(String(32), default="")
    oak: Mapped[str] = mapped_column(String(32), default="")
    intensity: Mapped[str] = mapped_column(String(32), default="")
    aroma_families: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    approved_by: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True, index=True)
    approved_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    tech_sheet_key: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = _stamp()
    product: Mapped[Product] = relationship()


class ServiceCard(Base):
    """How one venue serves a product. Drafted with a tasting note and approved on its own."""

    __tablename__ = "service_cards"
    __table_args__ = (
        UniqueConstraint("tasting_note_id", name="uq_service_cards_note"),
        CheckConstraint("source IN ('agent', 'staff')", name="ck_service_cards_source"),
        CheckConstraint("status IN ('draft', 'approved')", name="ck_service_cards_status"),
        CheckConstraint(
            "(status = 'draft' AND approved_by IS NULL AND approved_at IS NULL) OR "
            "(status = 'approved' AND approved_by IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_service_cards_approval",
        ),
        Index("ix_service_cards_venue_product", "venue_id", "product_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    product_id: Mapped[uuid.UUID] = _fk("products.id", index=True)
    tasting_note_id: Mapped[uuid.UUID] = _fk("tasting_notes.id", index=True)
    serving_temperature: Mapped[str] = mapped_column(String(80), default="")
    glassware: Mapped[str] = mapped_column(String(80), default="")
    decanting: Mapped[str] = mapped_column(String(80), default="")
    pour_size: Mapped[str] = mapped_column(String(80), default="")
    source: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    approved_by: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True, index=True)
    approved_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    created_at: Mapped[datetime] = _stamp()
    note: Mapped[TastingNote] = relationship()
    product: Mapped[Product] = relationship()


class CatalogEmbedding(Base):
    """One embedding for a venue SKU or an approved tasting note.

    ``values`` is the vector as JSON so SQLite and a Postgres without pgvector
    can rank in Python. A Postgres that has the vector extension also stores a
    ``vector`` column, added by migration 0030 and not mapped here. ``model_name``
    and ``dimension`` keep a model change from being mixed with older vectors.
    """

    __tablename__ = "catalog_embeddings"
    __table_args__ = (
        UniqueConstraint("venue_id", "subject_type", "subject_id", name="uq_catalog_embeddings_subject"),
        CheckConstraint("subject_type IN ('sku', 'note')", name="ck_catalog_embeddings_subject"),
        CheckConstraint("dimension >= 1", name="ck_catalog_embeddings_dimension"),
        Index("ix_catalog_embeddings_venue_model", "venue_id", "model_name", "dimension"),
    )

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _fk("organizations.id", index=True)
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    subject_type: Mapped[str] = mapped_column(String(16))
    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    model_name: Mapped[str] = mapped_column(String(120))
    dimension: Mapped[int] = mapped_column(Integer)
    values: Mapped[list] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime] = mapped_column(AwareDateTime, server_default=func.now())


class Menu(Base):
    __tablename__ = "menus"

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    name: Mapped[str] = mapped_column(String(200), default="Untitled menu")
    source_type: Mapped[str] = mapped_column(String(32), default="text")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    cuisine: Mapped[str] = mapped_column(String(80), default="")
    price_tier: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = _stamp()
    versions: Mapped[list[MenuVersion]] = relationship(
        back_populates="menu",
        cascade="all, delete-orphan",
        order_by="MenuVersion.number",
    )
    dishes: Mapped[list[Dish]] = relationship(
        back_populates="menu",
        cascade="all, delete-orphan",
        foreign_keys="Dish.menu_id",
        order_by="Dish.position",
    )


class MenuVersion(Base):
    """One capture of a menu. Pairing reads a confirmed version only."""

    __tablename__ = "menu_versions"
    __table_args__ = (
        UniqueConstraint("menu_id", "number", name="uq_menu_versions_menu_number"),
        CheckConstraint("number >= 1", name="ck_menu_versions_number"),
        CheckConstraint("source_type IN ('photo', 'pdf', 'url', 'text')", name="ck_menu_versions_source"),
        CheckConstraint("status IN ('draft', 'confirmed')", name="ck_menu_versions_status"),
        CheckConstraint(
            "(status = 'draft' AND confirmed_by IS NULL AND confirmed_at IS NULL) OR "
            "(status = 'confirmed' AND confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL)",
            name="ck_menu_versions_confirm",
        ),
        Index("ix_menu_versions_venue_menu", "venue_id", "menu_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    menu_id: Mapped[uuid.UUID] = _fk("menus.id", index=True)
    number: Mapped[int] = mapped_column(Integer)
    source_type: Mapped[str] = mapped_column(String(16))
    source_key: Mapped[str] = mapped_column(String(500), default="")
    source_filename: Mapped[str] = mapped_column(String(300), default="")
    source_url: Mapped[str] = mapped_column(String(1000), default="")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16))
    confirmed_by: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True, index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    created_at: Mapped[datetime] = _stamp()
    menu: Mapped[Menu] = relationship(back_populates="versions")
    dishes: Mapped[list[Dish]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
        foreign_keys="Dish.menu_version_id",
        order_by="Dish.position",
    )


class Dish(Base):
    __tablename__ = "dishes"
    __table_args__ = (
        UniqueConstraint("menu_version_id", "stable_id", name="uq_dishes_version_stable"),
        CheckConstraint("position >= 0", name="ck_dishes_position"),
        CheckConstraint("richness >= 0 AND richness <= 5", name="ck_dishes_richness"),
        CheckConstraint("acidity >= 0 AND acidity <= 5", name="ck_dishes_acidity"),
        CheckConstraint("sweetness >= 0 AND sweetness <= 5", name="ck_dishes_sweetness"),
        CheckConstraint("spice >= 0 AND spice <= 5", name="ck_dishes_spice"),
        CheckConstraint("umami >= 0 AND umami <= 5", name="ck_dishes_umami"),
        Index("ix_dishes_version_position", "menu_version_id", "position"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    menu_id: Mapped[uuid.UUID] = _fk("menus.id")
    menu_version_id: Mapped[uuid.UUID] = _fk("menu_versions.id", index=True)
    stable_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4)
    position: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(200))
    course: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    flavor_profile: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = _currency()
    main_component: Mapped[str] = mapped_column(String(200), default="")
    cooking_method: Mapped[str] = mapped_column(String(200), default="")
    sauce: Mapped[str] = mapped_column(String(200), default="")
    richness: Mapped[int] = mapped_column(Integer, default=0)
    acidity: Mapped[int] = mapped_column(Integer, default=0)
    sweetness: Mapped[int] = mapped_column(Integer, default=0)
    spice: Mapped[int] = mapped_column(Integer, default=0)
    umami: Mapped[int] = mapped_column(Integer, default=0)
    allergens: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[dict] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    needs_repairing: Mapped[bool] = mapped_column(Boolean, default=True)
    is_special: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    menu: Mapped[Menu] = relationship(back_populates="dishes", foreign_keys="Dish.menu_id")
    version: Mapped[MenuVersion] = relationship(back_populates="dishes", foreign_keys="Dish.menu_version_id")
    pairings: Mapped[list[Pairing]] = relationship(back_populates="dish", cascade="all, delete-orphan")


class Pairing(Base):
    __tablename__ = "pairings"
    __table_args__ = (
        CheckConstraint(
            "slot IN ('best_by_the_glass', 'best_bottle', 'value', 'adventurous', '')",
            name="ck_pairings_slot",
        ),
        CheckConstraint(
            "status IN ('suggested', 'pinned', 'swapped', 'rejected', 'gap')",
            name="ck_pairings_status",
        ),
        CheckConstraint("confidence IN ('high', 'medium', 'low', '')", name="ck_pairings_confidence"),
        CheckConstraint(
            "(status = 'gap' AND sku_id IS NULL) OR (status <> 'gap' AND sku_id IS NOT NULL)",
            name="ck_pairings_gap_sku",
        ),
        Index(
            "uq_pairings_dish_slot",
            "dish_id",
            "slot",
            unique=True,
            sqlite_where=text("slot != ''"),
            postgresql_where=text("slot <> ''"),
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    dish_id: Mapped[uuid.UUID] = _fk("dishes.id")
    sku_id: Mapped[uuid.UUID | None] = _fk("skus.id", nullable=True, index=True)
    slot: Mapped[str] = mapped_column(String(32), default="", server_default=text("''"))
    status: Mapped[str] = mapped_column(String(16), default="suggested", server_default=text("'suggested'"))
    rationale: Mapped[str] = mapped_column(Text, default="")
    server_script: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    confidence: Mapped[str] = mapped_column(String(16), default="", server_default=text("''"))
    gap: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    price_tier: Mapped[str] = mapped_column(String(32), default="")
    glass_price: Mapped[int] = mapped_column(Integer, default=0)
    bottle_price: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = _currency()
    dish: Mapped[Dish] = relationship(back_populates="pairings")
    sku: Mapped[Sku | None] = relationship()


class PairingCache(Base):
    """One deterministic slot assignment for a dish at a venue.

    The key covers the dish version, the published list versions, and the
    bottles, stock, notes, and pins that the scorer reads. A different venue
    id never matches. Copy text from the model is not stored here.
    """

    __tablename__ = "pairing_cache"
    __table_args__ = (
        UniqueConstraint("venue_id", "dish_id", name="uq_pairing_cache_venue_dish"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    dish_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("dishes.id", ondelete="CASCADE"), index=True)
    menu_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("menu_versions.id", ondelete="CASCADE"), index=True
    )
    list_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("list_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cache_key: Mapped[str] = mapped_column(String(64))
    result: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = _stamp()


class PairingPreference(Base):
    """A pin, swap, or rejection the sommelier made for a dish, across versions."""

    __tablename__ = "pairing_preferences"
    __table_args__ = (
        CheckConstraint("kind IN ('pin', 'swap', 'reject')", name="ck_pairing_preferences_kind"),
        CheckConstraint(
            "slot IN ('best_by_the_glass', 'best_bottle', 'value', 'adventurous', '')",
            name="ck_pairing_preferences_slot",
        ),
        Index(
            "uq_pairing_preferences_choice",
            "venue_id",
            "dish_stable_id",
            "slot",
            unique=True,
            sqlite_where=text("kind != 'reject'"),
            postgresql_where=text("kind <> 'reject'"),
        ),
        Index(
            "uq_pairing_preferences_reject",
            "venue_id",
            "dish_stable_id",
            "sku_id",
            unique=True,
            sqlite_where=text("kind = 'reject'"),
            postgresql_where=text("kind = 'reject'"),
        ),
        Index("ix_pairing_preferences_venue_dish", "venue_id", "dish_stable_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    dish_stable_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    slot: Mapped[str] = mapped_column(String(32), default="")
    kind: Mapped[str] = mapped_column(String(16))
    sku_id: Mapped[uuid.UUID] = _fk("skus.id", index=True)
    created_at: Mapped[datetime] = _stamp()
    sku: Mapped[Sku] = relationship()


PRICING_CATEGORIES = ("wine", "beer", "spirits", "sake", "other", "*")


class PricingRule(Base):
    """Markup for one category and wholesale cost band. Margin is not stored here."""

    __tablename__ = "pricing_rules"
    __table_args__ = (
        UniqueConstraint("venue_id", "category", "cost_min_cents", name="uq_pricing_rules_band"),
        CheckConstraint(
            "category IN ('wine', 'beer', 'spirits', 'sake', 'other', '*')",
            name="ck_pricing_rules_category",
        ),
        CheckConstraint("cost_min_cents >= 0", name="ck_pricing_rules_cost_min"),
        CheckConstraint(
            "cost_max_cents IS NULL OR cost_max_cents > cost_min_cents",
            name="ck_pricing_rules_cost_max",
        ),
        CheckConstraint("bottle_multiple > 0", name="ck_pricing_rules_bottle_multiple"),
        CheckConstraint("glass_pours_per_bottle >= 1", name="ck_pricing_rules_pours"),
        CheckConstraint("glass_multiple > 0", name="ck_pricing_rules_glass_multiple"),
        CheckConstraint("round_to_cents >= 1", name="ck_pricing_rules_round"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    category: Mapped[str] = mapped_column(String(32))
    cost_min_cents: Mapped[int] = mapped_column(Integer)
    cost_max_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bottle_multiple: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    glass_pours_per_bottle: Mapped[int] = mapped_column(Integer)
    glass_multiple: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    round_to_cents: Mapped[int] = mapped_column(Integer)


class BeverageList(Base):
    __tablename__ = "beverage_lists"

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    name: Mapped[str] = mapped_column(String(200), default="House list")
    budget: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = _currency()
    target_margin: Mapped[float] = mapped_column(Float, default=3.0)
    target_beverage_cost_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    concept: Mapped[str] = mapped_column(String(400), default="", server_default=text("''"))
    price_tier: Mapped[str] = mapped_column(String(32), default="", server_default=text("''"))
    notes: Mapped[str] = mapped_column(Text, default="")
    source_key: Mapped[str] = mapped_column(String(500), default="", server_default=text("''"))
    source_filename: Mapped[str] = mapped_column(String(300), default="", server_default=text("''"))
    created_at: Mapped[datetime] = _stamp()
    items: Mapped[list[ListItem]] = relationship(back_populates="beverage_list", cascade="all, delete-orphan")
    sections: Mapped[list[ListSection]] = relationship(
        back_populates="beverage_list",
        cascade="all, delete-orphan",
        order_by="ListSection.position",
    )


class ListSection(Base):
    """A named group on one list, with an optional share of the buying budget."""

    __tablename__ = "list_sections"
    __table_args__ = (
        UniqueConstraint("list_id", "name", name="uq_list_sections_list_name"),
        CheckConstraint(
            "budget_share_pct IS NULL OR (budget_share_pct >= 0 AND budget_share_pct <= 100)",
            name="ck_list_sections_share",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    list_id: Mapped[uuid.UUID] = _fk("beverage_lists.id", index=True)
    name: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    budget_share_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    beverage_list: Mapped[BeverageList] = relationship(back_populates="sections")
    items: Mapped[list[ListItem]] = relationship(back_populates="section_row")


class ListItem(Base):
    __tablename__ = "list_items"

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    list_id: Mapped[uuid.UUID] = _fk("beverage_lists.id")
    sku_id: Mapped[uuid.UUID] = _fk("skus.id", index=True)
    section: Mapped[str] = mapped_column(String(200), default="", server_default=text("''"))
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("list_sections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    cost: Mapped[int] = mapped_column(Integer, default=0)
    pour_price: Mapped[int] = mapped_column(Integer, default=0)
    bottle_price: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = _currency()
    margin_pct: Mapped[float] = mapped_column(Float, default=0)
    beverage_list: Mapped[BeverageList] = relationship(back_populates="items")
    section_row: Mapped[ListSection | None] = relationship(back_populates="items")
    sku: Mapped[Sku] = relationship()


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = (UniqueConstraint("venue_id", "name", name="uq_suppliers_venue_name"),)

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(64), default="distributor")
    contact_email: Mapped[str] = mapped_column(String(200), default="")
    account_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    order_minimum_cents: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    default_case_size: Mapped[int] = mapped_column(Integer, default=12, server_default=text("12"))
    delivery_days: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False, server_default=text("'[]'")
    )
    lead_time_days: Mapped[int] = mapped_column(Integer, default=7, server_default=text("7"))
    payment_terms: Mapped[str | None] = mapped_column(String(80), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    rep_name: Mapped[str] = mapped_column(String(200), default="", server_default=text("''"))
    rep_email: Mapped[str] = mapped_column(String(320), default="", server_default=text("''"))
    rep_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    order_minimum_currency: Mapped[str] = mapped_column(
        String(3), default=DEFAULT_CURRENCY, server_default=text("'USD'")
    )
    created_at: Mapped[datetime] = _stamp()
    contacts: Mapped[list[SupplierContact]] = relationship(back_populates="supplier", cascade="all, delete-orphan")
    items: Mapped[list[InventoryItem]] = relationship(back_populates="supplier")
    orders: Mapped[list[PurchaseOrder]] = relationship(back_populates="supplier")
    sessions: Mapped[list[TastingSession]] = relationship(back_populates="supplier")


class SupplierContact(Base):
    __tablename__ = "supplier_contacts"

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    supplier_id: Mapped[uuid.UUID] = _fk("suppliers.id", index=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str | None] = mapped_column(String(80), nullable=True)
    email: Mapped[str] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    created_at: Mapped[datetime] = _stamp()
    supplier: Mapped[Supplier] = relationship(back_populates="contacts")


OFFER_SOURCES = ("manual", "csv", "pdf")
PRICE_SHEET_STATUSES = ("pending_review", "applied", "rejected")


class SupplierAllocation(Base):
    """Bottles a supplier has set aside for this venue over a named period."""

    __tablename__ = "supplier_allocations"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_supplier_allocations_quantity"),
        CheckConstraint(
            "period_end IS NULL OR period_start IS NULL OR period_end >= period_start",
            name="ck_supplier_allocations_period",
        ),
        Index("ix_supplier_allocations_venue_supplier", "venue_id", "supplier_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    supplier_id: Mapped[uuid.UUID] = _fk("suppliers.id", index=True)
    product_id: Mapped[uuid.UUID] = _fk("products.id", index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    period_label: Mapped[str] = mapped_column(String(120), default="", server_default=text("''"))
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = _stamp()


class PriceSheet(Base):
    """A parsed supplier price sheet. Rows become offers only when a person applies it."""

    __tablename__ = "price_sheets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_review', 'applied', 'rejected')",
            name="ck_price_sheets_status",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    supplier_id: Mapped[uuid.UUID] = _fk("suppliers.id", index=True)
    document_id: Mapped[uuid.UUID] = _fk("documents.id", index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending_review", server_default=text("'pending_review'"))
    parsed_rows: Mapped[list] = mapped_column(JSON, default=list)
    created_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True, index=True)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True, index=True)
    created_at: Mapped[datetime] = _stamp()
    reviewed_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)


class SupplierOffer(Base):
    """One quoted price. The current offer is the latest valid row per supplier and product."""

    __tablename__ = "supplier_offers"
    __table_args__ = (
        CheckConstraint("source IN ('manual', 'csv', 'pdf')", name="ck_supplier_offers_source"),
        CheckConstraint("price_cents >= 0", name="ck_supplier_offers_price"),
        CheckConstraint("case_size >= 1", name="ck_supplier_offers_case_size"),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="ck_supplier_offers_window",
        ),
        Index("ix_supplier_offers_venue_product", "venue_id", "product_id"),
        Index("ix_supplier_offers_venue_supplier", "venue_id", "supplier_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    supplier_id: Mapped[uuid.UUID] = _fk("suppliers.id", index=True)
    product_id: Mapped[uuid.UUID] = _fk("products.id", index=True)
    sku_id: Mapped[uuid.UUID | None] = _fk("skus.id", nullable=True, index=True)
    unit_description: Mapped[str] = mapped_column(String(200), default="", server_default=text("''"))
    case_size: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    price_cents: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    currency: Mapped[str] = _currency()
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(String(16))
    source_document_id: Mapped[uuid.UUID | None] = _fk("documents.id", nullable=True, index=True)
    price_sheet_id: Mapped[uuid.UUID | None] = _fk("price_sheets.id", nullable=True, index=True)
    created_at: Mapped[datetime] = _stamp()


LOCATION_KINDS = ("cellar", "bar", "walk_in", "storage", "other")
MOVEMENT_TYPES = (
    "opening_balance",
    "receive",
    "sale",
    "count_adjustment",
    "breakage",
    "comp",
    "transfer_in",
    "transfer_out",
    "return",
    "faulty_bottle",
)


class InventoryItem(Base):
    """Cached on-hand for a SKU. The stock ledger is the source of truth.

    ``on_hand`` is the sum of ``stock_movements`` for this SKU, written in the
    same transaction as each new movement. ``depletion_30d`` is not stored; it
    is derived from those movements when the cellar is read. Par and cost live
    on the SKU.
    """

    __tablename__ = "inventory_items"

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    sku_id: Mapped[uuid.UUID] = _fk("skus.id", index=True)
    supplier_id: Mapped[uuid.UUID | None] = _fk("suppliers.id", nullable=True)
    on_hand: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    unit: Mapped[str] = mapped_column(String(32), default="btl")
    supplier: Mapped[Supplier | None] = relationship(back_populates="items")
    sku: Mapped[Sku] = relationship()


class Location(Base):
    """A cellar, bar, walk-in, or other stock place inside one venue."""

    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("venue_id", "name", name="uq_locations_venue_name"),
        CheckConstraint(
            "kind IN ('cellar', 'bar', 'walk_in', 'storage', 'other')",
            name="ck_locations_kind",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(32))
    notes: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    created_at: Mapped[datetime] = _stamp()


class Bin(Base):
    """A labeled spot inside a location. ``qr_payload`` is the scannable id."""

    __tablename__ = "bins"
    __table_args__ = (UniqueConstraint("venue_id", "code", name="uq_bins_venue_code"),)

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    location_id: Mapped[uuid.UUID] = _fk("locations.id", index=True)
    code: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(200), default="")
    qr_payload: Mapped[str] = mapped_column(String(240))
    created_at: Mapped[datetime] = _stamp()


class StockMovement(Base):
    """Append-only stock ledger. Corrections are new rows, never edits."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint(
            "movement_type IN ('opening_balance', 'receive', 'sale', 'count_adjustment', "
            "'breakage', 'comp', 'transfer_in', 'transfer_out', 'return', 'faulty_bottle')",
            name="ck_stock_movements_type",
        ),
        CheckConstraint("quantity <> 0", name="ck_stock_movements_quantity"),
        Index("ix_stock_movements_venue_created", "venue_id", "created_at"),
        Index("ix_stock_movements_venue_sku_created", "venue_id", "sku_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    sku_id: Mapped[uuid.UUID] = _fk("skus.id", index=True)
    location_id: Mapped[uuid.UUID] = _fk("locations.id", index=True)
    bin_id: Mapped[uuid.UUID | None] = _fk("bins.id", nullable=True, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    movement_type: Mapped[str] = mapped_column(String(32))
    unit_cost_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime, server_default=func.now(), index=True)


COUNT_STATUSES = ("in_progress", "submitted", "approved", "canceled")
PAR_STATUSES = ("pending", "accepted", "rejected")


class CountSession(Base):
    """One physical count of a location. Lines can arrive later from offline devices."""

    __tablename__ = "count_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('in_progress', 'submitted', 'approved', 'canceled')",
            name="ck_count_sessions_status",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    location_id: Mapped[uuid.UUID] = _fk("locations.id", index=True)
    status: Mapped[str] = mapped_column(String(32), default="in_progress", server_default=text("'in_progress'"))
    started_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    submitted_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    started_at: Mapped[datetime] = _stamp()
    submitted_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))


class CountLine(Base):
    """One device's count of a SKU. Replay of client_mutation_id is a no-op."""

    __tablename__ = "count_lines"
    __table_args__ = (
        UniqueConstraint("session_id", "client_mutation_id", name="uq_count_lines_session_mutation"),
        CheckConstraint("counted_quantity >= 0", name="ck_count_lines_quantity"),
        CheckConstraint("device_id <> ''", name="ck_count_lines_device"),
        CheckConstraint("client_mutation_id <> ''", name="ck_count_lines_mutation"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    session_id: Mapped[uuid.UUID] = _fk("count_sessions.id", index=True)
    sku_id: Mapped[uuid.UUID] = _fk("skus.id", index=True)
    bin_id: Mapped[uuid.UUID | None] = _fk("bins.id", nullable=True, index=True)
    counted_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    expected_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    device_id: Mapped[str] = mapped_column(String(64), default="web", server_default=text("'web'"))
    client_mutation_id: Mapped[str] = mapped_column(String(120))
    counted_at: Mapped[datetime] = mapped_column(AwareDateTime)
    notes: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))


class CountConflictResolution(Base):
    """The quantity a person chose when two devices disagreed on a SKU."""

    __tablename__ = "count_conflict_resolutions"
    __table_args__ = (
        UniqueConstraint("session_id", "sku_id", name="uq_count_resolutions_session_sku"),
        CheckConstraint("resolved_quantity >= 0", name="ck_count_resolutions_quantity"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    session_id: Mapped[uuid.UUID] = _fk("count_sessions.id", index=True)
    sku_id: Mapped[uuid.UUID] = _fk("skus.id", index=True)
    resolved_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    notes: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    resolved_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    resolved_at: Mapped[datetime] = _stamp()


class ParProposal(Base):
    """A cellar-manager suggestion. Accepting it writes skus.par."""

    __tablename__ = "par_proposals"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'accepted', 'rejected')", name="ck_par_proposals_status"),
        CheckConstraint("lead_time_days >= 0", name="ck_par_proposals_lead"),
        CheckConstraint("safety_days >= 0", name="ck_par_proposals_safety"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    sku_id: Mapped[uuid.UUID] = _fk("skus.id", index=True)
    current_par: Mapped[int] = mapped_column(Integer)
    proposed_par: Mapped[int] = mapped_column(Integer)
    depletion_30d: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    lead_time_days: Mapped[int] = mapped_column(Integer, default=7, server_default=text("7"))
    safety_days: Mapped[int] = mapped_column(Integer, default=4, server_default=text("4"))
    rationale: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="pending", server_default=text("'pending'"))
    proposed_by: Mapped[str] = mapped_column(String(80), default="cellar-manager", server_default=text("'cellar-manager'"))
    decided_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    created_at: Mapped[datetime] = _stamp()


PO_STATUSES = (
    "draft",
    "approved",
    "sent",
    "part_received",
    "received",
    "closed",
    "canceled",
)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("venue_id", "po_number", name="uq_purchase_orders_venue_number"),
        CheckConstraint(
            "status IN ('draft', 'approved', 'sent', 'part_received', 'received', 'closed', 'canceled')",
            name="ck_purchase_orders_status",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    supplier_id: Mapped[uuid.UUID] = _fk("suppliers.id", index=True)
    po_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    expected_delivery_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    subtotal_cents: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    order_minimum_cents: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    minimum_met: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
    pdf_document_id: Mapped[uuid.UUID | None] = _fk("documents.id", nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    sent_via: Mapped[str | None] = mapped_column(String(40), nullable=True)
    delivery_adapter_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    created_at: Mapped[datetime] = _stamp()
    updated_at: Mapped[datetime] = _stamp()
    supplier: Mapped[Supplier] = relationship(back_populates="orders")
    lines: Mapped[list[POLine]] = relationship(back_populates="purchase_order", cascade="all, delete-orphan")


class POLine(Base):
    """A line on a purchase order. ``po_id`` is the purchase order foreign key.

    ``qty`` and ``unit_cost`` stay for the original reorder draft. Case-rounded
    orders also fill ``cases_ordered``, ``quantity_ordered``, and the cent totals.
    """

    __tablename__ = "po_lines"

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    po_id: Mapped[uuid.UUID] = _fk("purchase_orders.id", index=True)
    sku: Mapped[str] = mapped_column(String(64), index=True)
    sku_id: Mapped[uuid.UUID | None] = _fk("skus.id", nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    product_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    qty: Mapped[int] = mapped_column(Integer, default=1)
    case_size: Mapped[int] = mapped_column(Integer, default=12, server_default=text("12"))
    cases_ordered: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    quantity_ordered: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), server_default=text("0"))
    quantity_received: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), server_default=text("0"))
    unit_cost: Mapped[int] = mapped_column(Integer, default=0)
    unit_cost_cents: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    line_total_cents: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    currency: Mapped[str] = _currency()
    vintage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="lines")


class Approval(Base):
    """A decision on a venue record. Purchase orders require the Owner."""

    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('pending', 'approved', 'rejected')",
            name="ck_approvals_decision",
        ),
        Index("ix_approvals_entity", "venue_id", "entity_type", "entity_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    decision: Mapped[str] = mapped_column(String(32), default="pending", server_default=text("'pending'"))
    required_role: Mapped[str] = mapped_column(String(32), default="owner", server_default=text("'owner'"))
    decided_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _stamp()


INVOICE_STATUSES = ("uploaded", "matched", "discrepancy", "accepted")
INVOICE_EXTRACTION_MODES = ("demo", "vision", "manual")
RECEIPT_STATUSES = ("draft", "accepted", "rejected")


class Invoice(Base):
    """A supplier invoice. The original file lives in the document vault."""

    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint(
            "status IN ('uploaded', 'matched', 'discrepancy', 'accepted')",
            name="ck_invoices_status",
        ),
        CheckConstraint(
            "extraction_mode IN ('demo', 'vision', 'manual')",
            name="ck_invoices_extraction_mode",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    supplier_id: Mapped[uuid.UUID] = _fk("suppliers.id", index=True)
    purchase_order_id: Mapped[uuid.UUID | None] = _fk("purchase_orders.id", nullable=True, index=True)
    invoice_number: Mapped[str] = mapped_column(String(80), index=True)
    invoice_date: Mapped[str] = mapped_column(String(10))
    subtotal_cents: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    tax_cents: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    total_cents: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    currency: Mapped[str] = _currency()
    document_id: Mapped[uuid.UUID] = _fk("documents.id", index=True)
    extracted_lines: Mapped[list] = mapped_column(JSON, default=list)
    extraction_mode: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), default="uploaded", server_default=text("'uploaded'"))
    created_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    created_at: Mapped[datetime] = _stamp()


class Receipt(Base):
    """A counted delivery against a purchase order, optionally tied to an invoice."""

    __tablename__ = "receipts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'accepted', 'rejected')",
            name="ck_receipts_status",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    purchase_order_id: Mapped[uuid.UUID] = _fk("purchase_orders.id", index=True)
    invoice_id: Mapped[uuid.UUID | None] = _fk("invoices.id", nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", server_default=text("'draft'"))
    received_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    discrepancies_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    discrepancy_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _stamp()
    lines: Mapped[list[ReceiptLine]] = relationship(back_populates="receipt", cascade="all, delete-orphan")


class ReceiptLine(Base):
    """One counted line. Flags record the three-way match against the PO and invoice."""

    __tablename__ = "receipt_lines"

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    receipt_id: Mapped[uuid.UUID] = _fk("receipts.id", index=True)
    po_line_id: Mapped[uuid.UUID | None] = _fk("po_lines.id", nullable=True, index=True)
    sku: Mapped[str] = mapped_column(String(64), index=True)
    product_name: Mapped[str] = mapped_column(String(200))
    ordered_qty: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    invoiced_qty: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    counted_qty: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    ordered_unit_cost_cents: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    invoiced_unit_cost_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ordered_vintage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    received_vintage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    bin_id: Mapped[uuid.UUID | None] = _fk("bins.id", nullable=True, index=True)
    flags: Mapped[list] = mapped_column(JSON, default=list)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    receipt: Mapped[Receipt] = relationship(back_populates="lines")


class Standard(Base):
    """House service standard. Madira ships a default; the venue's edit is the one lessons use."""

    __tablename__ = "standards"
    __table_args__ = (
        UniqueConstraint("venue_id", "slug", name="uq_standards_venue_slug"),
        CheckConstraint("version >= 1", name="ck_standards_version"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    slug: Mapped[str] = mapped_column(String(80))
    topic: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    is_default: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
    updated_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    updated_at: Mapped[datetime] = _stamp()


class Lesson(Base):
    __tablename__ = "lessons"
    __table_args__ = (
        UniqueConstraint("venue_id", "slug", name="uq_lessons_venue_slug"),
        CheckConstraint(
            "position IN ('server', 'bartender', 'barback', 'host', 'all')",
            name="ck_lessons_position",
        ),
        CheckConstraint("status IN ('draft', 'approved')", name="ck_lessons_status"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    slug: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(64), default="waitstaff")
    category: Mapped[str] = mapped_column(String(64), default="wine")
    body: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[str] = mapped_column(String(16), default="all", server_default=text("'all'"))
    status: Mapped[str] = mapped_column(String(16), default="approved", server_default=text("'approved'"))
    approved_by: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="seed", server_default=text("'seed'"))
    standard_ids: Mapped[list] = mapped_column(JSON, default=list)
    sku_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime, default=_now, server_default=func.now())


class Quiz(Base):
    __tablename__ = "quizzes"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'approved')", name="ck_quizzes_status"),
        CheckConstraint("source IN ('lesson', 'list')", name="ck_quizzes_source"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    lesson_id: Mapped[uuid.UUID | None] = _fk("lessons.id", nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    questions: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="approved", server_default=text("'approved'"))
    source: Mapped[str] = mapped_column(String(16), default="lesson", server_default=text("'lesson'"))
    created_at: Mapped[datetime] = mapped_column(AwareDateTime, default=_now, server_default=func.now())


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    quiz_id: Mapped[uuid.UUID] = _fk("quizzes.id")
    user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True, index=True)
    staff_name: Mapped[str] = mapped_column(String(120), default="Floor")
    answers: Mapped[list] = mapped_column(JSON, default=list)
    score: Mapped[float] = mapped_column(Float, default=0)
    # 10000 basis points is a perfect score. The service writes this; the UI does not recompute it.
    score_bp: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    per_question: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = _stamp()


class QuizReview(Base):
    """One Leitner box for a person, a quiz, and a question."""

    __tablename__ = "quiz_reviews"
    __table_args__ = (
        UniqueConstraint("user_id", "quiz_id", "question_id", name="uq_quiz_reviews_user_quiz_question"),
        CheckConstraint("box >= 0 AND box <= 5", name="ck_quiz_reviews_box"),
        CheckConstraint("last_result IN ('correct', 'wrong', '')", name="ck_quiz_reviews_last_result"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    user_id: Mapped[uuid.UUID] = _fk("users.id", index=True)
    quiz_id: Mapped[uuid.UUID] = _fk("quizzes.id", index=True)
    question_id: Mapped[str] = mapped_column(String(80))
    box: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    due_at: Mapped[datetime] = mapped_column(AwareDateTime)
    last_result: Mapped[str] = mapped_column(String(16), default="", server_default=text("''"))
    updated_at: Mapped[datetime] = _stamp()


class Briefing(Base):
    """One pre-shift briefing for a venue and a local service date."""

    __tablename__ = "briefings"
    __table_args__ = (
        UniqueConstraint("venue_id", "service_date", name="uq_briefings_venue_date"),
        CheckConstraint("status IN ('draft', 'published')", name="ck_briefings_status"),
        CheckConstraint("due_review_count >= 0", name="ck_briefings_due_reviews"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    service_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default=text("'draft'"))
    intro: Mapped[str] = mapped_column(Text, default="")
    cards: Mapped[list] = mapped_column(JSON, default=list)
    push_sku_id: Mapped[uuid.UUID | None] = _fk("skus.id", nullable=True, index=True)
    due_review_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    built_at: Mapped[datetime] = _stamp()
    published_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    published_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True, index=True)


class BriefingAck(Base):
    """One staff member's acknowledgement of a briefing."""

    __tablename__ = "briefing_acks"
    __table_args__ = (
        UniqueConstraint("briefing_id", "user_id", name="uq_briefing_acks_briefing_user"),
        CheckConstraint("seconds_to_ack >= 0", name="ck_briefing_acks_seconds"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    briefing_id: Mapped[uuid.UUID] = _fk("briefings.id", index=True)
    user_id: Mapped[uuid.UUID] = _fk("users.id", index=True)
    seconds_to_ack: Mapped[int] = mapped_column(Integer, default=0)
    acknowledged_at: Mapped[datetime] = _stamp()


TASTING_STATUSES = ("planned", "held", "closed")
SAMPLE_DECISIONS = ("undecided", "buy", "list", "pass")


class TastingSession(Base):
    """A cellar tasting. The calendar file is generated when someone downloads it."""

    __tablename__ = "tasting_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('planned', 'held', 'closed')", name="ck_tasting_sessions_status"),
        CheckConstraint("ends_at >= starts_at", name="ck_tasting_sessions_window"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    supplier_id: Mapped[uuid.UUID | None] = _fk("suppliers.id", nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    starts_at: Mapped[datetime] = mapped_column(AwareDateTime)
    ends_at: Mapped[datetime] = mapped_column(AwareDateTime)
    location: Mapped[str] = mapped_column(String(200), default="Maison Madira cellar")
    status: Mapped[str] = mapped_column(String(16), default="planned", server_default=text("'planned'"))
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True, index=True)
    created_at: Mapped[datetime] = _stamp()
    supplier: Mapped[Supplier | None] = relationship(back_populates="sessions")
    samples: Mapped[list[Sample]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Sample.created_at",
    )


class Sample(Base):
    """One bottle tasted in a session. Buy and list open drafts. Pass stores a reason."""

    __tablename__ = "samples"
    __table_args__ = (
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="ck_samples_score"),
        CheckConstraint(
            "decision IN ('undecided', 'buy', 'list', 'pass')",
            name="ck_samples_decision",
        ),
        CheckConstraint(
            "quoted_price_cents IS NULL OR quoted_price_cents >= 0",
            name="ck_samples_quoted_price",
        ),
        Index("ix_samples_venue_session", "venue_id", "session_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    session_id: Mapped[uuid.UUID] = _fk("tasting_sessions.id", index=True)
    product_id: Mapped[uuid.UUID | None] = _fk("products.id", nullable=True, index=True)
    sku_id: Mapped[uuid.UUID | None] = _fk("skus.id", nullable=True, index=True)
    supplier_id: Mapped[uuid.UUID | None] = _fk("suppliers.id", nullable=True, index=True)
    offer_id: Mapped[uuid.UUID | None] = _fk("supplier_offers.id", nullable=True, index=True)
    label_document_id: Mapped[uuid.UUID | None] = _fk("documents.id", nullable=True, index=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    quoted_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    decision: Mapped[str] = mapped_column(String(16), default="undecided", server_default=text("'undecided'"))
    decided_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True, index=True)
    decided_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    pass_reason: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    purchase_order_id: Mapped[uuid.UUID | None] = _fk("purchase_orders.id", nullable=True, index=True)
    po_line_id: Mapped[uuid.UUID | None] = _fk("po_lines.id", nullable=True, index=True)
    list_id: Mapped[uuid.UUID | None] = _fk("beverage_lists.id", nullable=True, index=True)
    list_version_id: Mapped[uuid.UUID | None] = _fk("list_versions.id", nullable=True, index=True)
    created_at: Mapped[datetime] = _stamp()
    session: Mapped[TastingSession] = relationship(back_populates="samples")
    product: Mapped[Product | None] = relationship()


class SourcingBrief(Base):
    """A want list built from list-coverage gaps. The model phrases the rationale only."""

    __tablename__ = "sourcing_briefs"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'closed')", name="ck_sourcing_briefs_status"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    list_id: Mapped[uuid.UUID | None] = _fk("beverage_lists.id", nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default=text("'draft'"))
    created_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True, index=True)
    created_at: Mapped[datetime] = _stamp()
    items: Mapped[list["WantItem"]] = relationship(
        back_populates="brief",
        cascade="all, delete-orphan",
        order_by="WantItem.position",
    )


class WantItem(Base):
    """One gap on a sourcing brief. Quantity and the price band come from services."""

    __tablename__ = "want_items"
    __table_args__ = (
        CheckConstraint("quantity_hint >= 0", name="ck_want_items_quantity"),
        CheckConstraint("position >= 0", name="ck_want_items_position"),
        Index("ix_want_items_venue_brief", "venue_id", "brief_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    brief_id: Mapped[uuid.UUID] = _fk("sourcing_briefs.id", index=True)
    category: Mapped[str] = mapped_column(String(32))
    style: Mapped[str] = mapped_column(String(80))
    price_band: Mapped[str] = mapped_column(String(16), default="", server_default=text("''"))
    quantity_hint: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    dishes: Mapped[list] = mapped_column(JSON, default=list)
    sample_id: Mapped[uuid.UUID | None] = _fk("samples.id", nullable=True, index=True)
    offer_id: Mapped[uuid.UUID | None] = _fk("supplier_offers.id", nullable=True, index=True)
    rationale: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    position: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = _stamp()
    brief: Mapped[SourcingBrief] = relationship(back_populates="items")


class RepFollowup(Base):
    """A draft note to a supplier rep. Madira stores it and does not send it."""

    __tablename__ = "rep_followups"
    __table_args__ = (UniqueConstraint("session_id", name="uq_rep_followups_session"),)

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    session_id: Mapped[uuid.UUID] = _fk("tasting_sessions.id", index=True)
    supplier_id: Mapped[uuid.UUID | None] = _fk("suppliers.id", nullable=True, index=True)
    to_email: Mapped[str] = mapped_column(String(320), default="", server_default=text("''"))
    subject: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    purchase_order_id: Mapped[uuid.UUID | None] = _fk("purchase_orders.id", nullable=True, index=True)
    created_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True, index=True)
    created_at: Mapped[datetime] = _stamp()
    updated_at: Mapped[datetime] = _stamp()


class TastingInvite(Base):
    """A tasting invite stays a draft until an Owner or a Manager approves it.

    Approval is the only path that builds the .ics and the email draft.
    ``sent`` stays false: Madira does not send the invite.
    """

    __tablename__ = "tasting_invites"
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_tasting_invites_session"),
        CheckConstraint(
            "status IN ('proposed', 'ready', 'rejected')",
            name="ck_tasting_invites_status",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    session_id: Mapped[uuid.UUID] = _fk("tasting_sessions.id")
    status: Mapped[str] = mapped_column(String(16), default="proposed")
    agenda_note: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    agenda_facts: Mapped[dict] = mapped_column(JSON, default=dict)
    approval_id: Mapped[uuid.UUID | None] = _fk("approvals.id", nullable=True, index=True)
    ics_text: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    email_subject: Mapped[str] = mapped_column(String(200), default="", server_default=text("''"))
    email_body: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    email_mailto: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    driver: Mapped[str] = mapped_column(String(16), default="", server_default=text("''"))
    sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    created_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    created_at: Mapped[datetime] = _stamp()
    updated_at: Mapped[datetime] = _stamp()


class TastingInviteSlot(Base):
    __tablename__ = "tasting_invite_slots"
    __table_args__ = (
        UniqueConstraint("invite_id", "position", name="uq_tasting_invite_slots_position"),
        Index("ix_tasting_invite_slots_venue", "venue_id", "invite_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id")
    invite_id: Mapped[uuid.UUID] = _fk("tasting_invites.id")
    position: Mapped[int] = mapped_column(Integer)
    starts_at: Mapped[datetime] = mapped_column(AwareDateTime)
    ends_at: Mapped[datetime] = mapped_column(AwareDateTime)
    source: Mapped[str] = mapped_column(String(16), default="entered", server_default=text("'entered'"))
    chosen: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))


class TastingInviteAttendee(Base):
    __tablename__ = "tasting_invite_attendees"
    __table_args__ = (Index("ix_tasting_invite_attendees_venue", "venue_id", "invite_id"),)

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id")
    invite_id: Mapped[uuid.UUID] = _fk("tasting_invites.id")
    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(200), default="", server_default=text("''"))
    email: Mapped[str] = mapped_column(String(320), default="", server_default=text("''"))
    user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))


class PosCredential(Base):
    """Fernet ciphertext for one venue's POS access token. The raw token is never stored."""

    __tablename__ = "pos_credentials"

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    ciphertext: Mapped[str] = mapped_column(Text)
    key_last4: Mapped[str] = mapped_column(String(8), default="", server_default=text("''"))
    created_at: Mapped[datetime] = _stamp()


class PosConnection(Base):
    __tablename__ = "pos_connections"
    __table_args__ = (
        UniqueConstraint("venue_id", "provider", name="uq_pos_connections_venue_provider"),
        CheckConstraint(
            "provider IN ('square', 'demo')",
            name="ck_pos_connections_provider",
        ),
        CheckConstraint(
            "status IN ('pending', 'active', 'disconnected', 'error')",
            name="ck_pos_connections_status",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    provider: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default=text("'pending'"))
    location_id: Mapped[str] = mapped_column(String(64), default="", server_default=text("''"))
    location_name: Mapped[str] = mapped_column(String(200), default="", server_default=text("''"))
    credential_id: Mapped[uuid.UUID | None] = _fk("pos_credentials.id", nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    last_cursor: Mapped[str] = mapped_column(String(512), default="", server_default=text("''"))
    watermark: Mapped[str] = mapped_column(String(64), default="", server_default=text("''"))
    actor_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    created_at: Mapped[datetime] = _stamp()
    updated_at: Mapped[datetime] = _stamp()


class PosItemMapping(Base):
    __tablename__ = "pos_item_mappings"
    __table_args__ = (
        UniqueConstraint("venue_id", "provider", "variation_id", name="uq_pos_item_mappings_variation"),
        CheckConstraint("units_per_sale > 0", name="ck_pos_item_mappings_units"),
        CheckConstraint("pour_ml IS NULL OR pour_ml > 0", name="ck_pos_item_mappings_pour"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    provider: Mapped[str] = mapped_column(String(16))
    item_id: Mapped[str] = mapped_column(String(128), default="", server_default=text("''"))
    variation_id: Mapped[str] = mapped_column(String(128))
    sku_id: Mapped[uuid.UUID] = _fk("skus.id")
    pour_ml: Mapped[int | None] = mapped_column(Integer, nullable=True)
    units_per_sale: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    created_at: Mapped[datetime] = _stamp()
    updated_at: Mapped[datetime] = _stamp()


class PosSale(Base):
    """Idempotency ledger. One row per provider line item that posted stock."""

    __tablename__ = "pos_sales"
    __table_args__ = (
        UniqueConstraint("venue_id", "provider", "external_line_id", name="uq_pos_sales_line"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    provider: Mapped[str] = mapped_column(String(16))
    external_line_id: Mapped[str] = mapped_column(String(200))
    order_id: Mapped[str] = mapped_column(String(128), default="", server_default=text("''"))
    variation_id: Mapped[str] = mapped_column(String(128), default="", server_default=text("''"))
    sku_id: Mapped[uuid.UUID] = _fk("skus.id")
    movement_id: Mapped[uuid.UUID | None] = _fk("stock_movements.id", nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    closed_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    created_at: Mapped[datetime] = _stamp()


class PosSyncRun(Base):
    __tablename__ = "pos_sync_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_pos_sync_runs_status",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    connection_id: Mapped[uuid.UUID] = _fk("pos_connections.id")
    status: Mapped[str] = mapped_column(String(16), default="running", server_default=text("'running'"))
    started_at: Mapped[datetime] = mapped_column(AwareDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    counts: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    actor_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)


class LlmCredential(Base):
    """One saved provider key. The secret is Fernet ciphertext, never the raw key."""

    __tablename__ = "llm_credentials"

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _fk("organizations.id", index=True)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(120), default="")
    ciphertext: Mapped[str] = mapped_column(Text)
    key_last4: Mapped[str] = mapped_column(String(8), default="")
    updated_at: Mapped[datetime] = _stamp()


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_org_created", "organization_id", "created_at"),)

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    # Filled for new runs so an organization limit can count them. Older rows stay null.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    reply: Mapped[str] = mapped_column(Text, default="")
    delegated: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = _stamp()


class AgentUsage(Base):
    """One metered subagent call. Cost is an estimate in micro-dollars, or zero in demo."""

    __tablename__ = "agent_usage"
    __table_args__ = (
        CheckConstraint("tokens_in >= 0", name="ck_agent_usage_tokens_in"),
        CheckConstraint("tokens_out >= 0", name="ck_agent_usage_tokens_out"),
        CheckConstraint("cost_micro_usd >= 0", name="ck_agent_usage_cost"),
        CheckConstraint("latency_ms >= 0", name="ck_agent_usage_latency"),
        CheckConstraint("cost_label IN ('demo', 'estimate')", name="ck_agent_usage_label"),
        Index("ix_agent_usage_org_created", "organization_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _fk("organizations.id", index=True)
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    agent_run_id: Mapped[uuid.UUID | None] = _fk("agent_runs.id", nullable=True, index=True)
    subagent: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(120))
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    cost_micro_usd: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    cost_label: Mapped[str] = mapped_column(String(16))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = _stamp()


class User(Base):
    """Someone who signed in with Google. `google_sub` is the OIDC subject."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _pk()
    google_sub: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(String(320), default="")
    name: Mapped[str] = mapped_column(String(200), default="")
    picture: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _stamp()
    last_login_at: Mapped[datetime] = _stamp()


DOC_TYPES = ("invoice", "po_pdf", "purchase_order", "delivery_note", "license", "certificate", "other")


class AuditEvent(Base):
    """Append-only hash-chained ledger. Corrections are new rows. No update or delete API."""

    __tablename__ = "audit_events"
    __table_args__ = (
        UniqueConstraint("venue_id", "seq", name="uq_audit_events_venue_seq"),
        CheckConstraint("seq >= 1", name="ck_audit_events_seq"),
        Index("ix_audit_events_venue_created", "venue_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _fk("organizations.id", index=True)
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    seq: Mapped[int] = mapped_column(Integer)
    actor_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True, index=True)
    actor_email: Mapped[str] = mapped_column(String(320), default="")
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(80), default="")
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    before_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    prev_hash: Mapped[str] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = _stamp()


class Document(Base):
    """Vault metadata. Bytes live under the venue prefix in file storage."""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "doc_type IN ('invoice', 'po_pdf', 'purchase_order', 'delivery_note', 'license', 'certificate', 'other')",
            name="ck_documents_doc_type",
        ),
        Index("ix_documents_venue_created", "venue_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _fk("organizations.id", index=True)
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    doc_type: Mapped[str] = mapped_column(String(32))
    filename: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    linked_entity_type: Mapped[str] = mapped_column(String(80), default="")
    linked_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    uploaded_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    created_at: Mapped[datetime] = _stamp()


EXCURSION_METRICS = (
    "temp_high",
    "temp_low",
    "humidity_high",
    "humidity_low",
    "temp_and_humidity",
)
EXCURSION_STATUSES = ("open", "acknowledged")


class StorageZone(Base):
    """A temperature and humidity target for one cellar, bar, or cold box."""

    __tablename__ = "storage_zones"
    __table_args__ = (UniqueConstraint("venue_id", "name", name="uq_storage_zones_venue_name"),)

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    location_id: Mapped[uuid.UUID | None] = _fk("locations.id", nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    target_temp_min_c: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    target_temp_max_c: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    target_humidity_min_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    target_humidity_max_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    capacity_bottles: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _stamp()


class ConditionReading(Base):
    """One manual or sensor reading for a storage zone."""

    __tablename__ = "condition_readings"

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    zone_id: Mapped[uuid.UUID] = _fk("storage_zones.id", index=True)
    temp_c: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    humidity_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    source: Mapped[str] = mapped_column(String(32), default="manual", server_default=text("'manual'"))
    recorded_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(AwareDateTime)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ConditionExcursion(Base):
    """An out-of-range reading, with the bottles sitting in that zone."""

    __tablename__ = "condition_excursions"
    __table_args__ = (
        CheckConstraint(
            "metric IN ('temp_high', 'temp_low', 'humidity_high', 'humidity_low', 'temp_and_humidity')",
            name="ck_condition_excursions_metric",
        ),
        CheckConstraint(
            "status IN ('open', 'acknowledged')",
            name="ck_condition_excursions_status",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    zone_id: Mapped[uuid.UUID] = _fk("storage_zones.id", index=True)
    reading_id: Mapped[uuid.UUID] = _fk("condition_readings.id", index=True)
    metric: Mapped[str] = mapped_column(String(32))
    measured_temp_c: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    measured_humidity_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    affected_skus: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="open", server_default=text("'open'"))
    acknowledged_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _stamp()


SENSOR_METRICS = ("temperature_c", "humidity_pct")
SENSOR_IMPORT_STATUSES = ("pending_review", "applied", "rejected")
REMINDER_SOURCE_TYPES = ("license", "certificate")
REMINDER_STATUSES = ("acknowledged", "snoozed")


class Sensor(Base):
    """A venue probe. The signing secret is ciphertext; the API returns the last four characters."""

    __tablename__ = "sensors"
    __table_args__ = (
        UniqueConstraint("venue_id", "external_id", name="uq_sensors_venue_external"),
        UniqueConstraint("sensor_key", name="uq_sensors_key"),
        CheckConstraint(
            "metric IN ('temperature_c', 'humidity_pct')",
            name="ck_sensors_metric",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    zone_id: Mapped[uuid.UUID] = _fk("storage_zones.id", index=True)
    name: Mapped[str] = mapped_column(String(200))
    metric: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(120))
    sensor_key: Mapped[str] = mapped_column(String(80))
    secret_ciphertext: Mapped[str] = mapped_column(Text)
    secret_last4: Mapped[str] = mapped_column(String(8), default="", server_default=text("''"))
    created_at: Mapped[datetime] = _stamp()


class SensorReading(Base):
    """One accepted sensor sample. The same sensor and timestamp are stored once."""

    __tablename__ = "sensor_readings"
    __table_args__ = (
        UniqueConstraint("sensor_id", "recorded_at", name="uq_sensor_readings_sensor_at"),
        CheckConstraint(
            "metric IN ('temperature_c', 'humidity_pct')",
            name="ck_sensor_readings_metric",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    sensor_id: Mapped[uuid.UUID] = _fk("sensors.id", index=True)
    condition_reading_id: Mapped[uuid.UUID] = _fk("condition_readings.id", index=True)
    metric: Mapped[str] = mapped_column(String(32))
    value: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    recorded_at: Mapped[datetime] = mapped_column(AwareDateTime)


class SensorImport(Base):
    """A CSV review. Rows are previewed, then applied or rejected."""

    __tablename__ = "sensor_imports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_review', 'applied', 'rejected')",
            name="ck_sensor_imports_status",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    filename: Mapped[str] = mapped_column(String(200), default="", server_default=text("''"))
    status: Mapped[str] = mapped_column(String(32), default="pending_review", server_default=text("'pending_review'"))
    rows_json: Mapped[list] = mapped_column(JSON, default=list)
    created_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    decided_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    created_at: Mapped[datetime] = _stamp()
    decided_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)


class VenueLicense(Base):
    """A recorded license expiry. The vault file has no date of its own."""

    __tablename__ = "venue_licenses"

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    document_id: Mapped[uuid.UUID | None] = _fk("documents.id", nullable=True, index=True)
    rule_code: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(200))
    expires_on: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = _stamp()


class ReminderRule(Base):
    """A venue copy of a seeded reminder. Wording stays neutral."""

    __tablename__ = "reminder_rules"
    __table_args__ = (
        UniqueConstraint("venue_id", "code", name="uq_reminder_rules_venue_code"),
        CheckConstraint("lead_days >= 1 AND lead_days <= 365", name="ck_reminder_rules_lead"),
        CheckConstraint(
            "applies_to IN ('license', 'certificate')",
            name="ck_reminder_rules_applies",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    jurisdiction: Mapped[str] = mapped_column(String(16))
    code: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(Text)
    lead_days: Mapped[int] = mapped_column(Integer)
    applies_to: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = _stamp()


class ReminderState(Base):
    """An in-app acknowledgement or snooze. Nothing is sent."""

    __tablename__ = "reminder_states"
    __table_args__ = (
        UniqueConstraint("venue_id", "source_type", "source_id", name="uq_reminder_states_source"),
        CheckConstraint(
            "source_type IN ('license', 'certificate')",
            name="ck_reminder_states_source",
        ),
        CheckConstraint(
            "status IN ('acknowledged', 'snoozed')",
            name="ck_reminder_states_status",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    source_type: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    status: Mapped[str] = mapped_column(String(32))
    snooze_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    updated_at: Mapped[datetime] = _stamp()


class VenueInvite(Base):
    """An invitation to join a venue. Nothing is emailed. Sign-in accepts it."""

    __tablename__ = "venue_invites"
    __table_args__ = (
        CheckConstraint(
            "role IN ('Owner', 'Sommelier', 'Manager', 'Staff', 'Auditor')",
            name="ck_venue_invites_role",
        ),
        CheckConstraint(
            "position IS NULL OR position IN ('server', 'bartender', 'barback', 'host')",
            name="ck_venue_invites_position",
        ),
        CheckConstraint(
            "(accepted_at IS NULL AND accepted_user_id IS NULL) OR "
            "(accepted_at IS NOT NULL AND accepted_user_id IS NOT NULL)",
            name="ck_venue_invites_acceptance",
        ),
        Index(
            "uq_venue_invites_active_email",
            "venue_id",
            "email",
            unique=True,
            sqlite_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
            postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(32))
    position: Mapped[str | None] = mapped_column(String(16), nullable=True)
    invited_by_user_id: Mapped[uuid.UUID] = _fk("users.id", index=True)
    created_at: Mapped[datetime] = _stamp()
    accepted_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    accepted_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)


class RoleplaySession(Base):
    """One staff-trainer roleplay. The service writes the 0-4 score."""

    __tablename__ = "roleplay_sessions"
    __table_args__ = (
        CheckConstraint(
            "persona IN ('skeptic', 'budget-conscious', 'connoisseur', 'celebration')",
            name="ck_roleplay_sessions_persona",
        ),
        CheckConstraint("status IN ('open', 'scored')", name="ck_roleplay_sessions_status"),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 4)", name="ck_roleplay_sessions_score_range"),
        CheckConstraint(
            "(status = 'open' AND score IS NULL AND scored_at IS NULL) OR "
            "(status = 'scored' AND score IS NOT NULL AND scored_at IS NOT NULL)",
            name="ck_roleplay_sessions_scored",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    user_id: Mapped[uuid.UUID] = _fk("users.id", index=True)
    persona: Mapped[str] = mapped_column(String(32))
    dish_id: Mapped[uuid.UUID | None] = _fk("dishes.id", nullable=True, index=True)
    transcript: Mapped[list] = mapped_column(JSON, default=list)
    rubric: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open", server_default=text("'open'"))
    started_at: Mapped[datetime] = _stamp()
    scored_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)


class Certificate(Base):
    """A staff certificate. Reminders start 30 days before expires_on."""

    __tablename__ = "certificates"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('responsible_service', 'food_handler', 'other')",
            name="ck_certificates_kind",
        ),
        CheckConstraint("expires_on >= issued_on", name="ck_certificates_dates"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    user_id: Mapped[uuid.UUID] = _fk("users.id", index=True)
    kind: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(200))
    issued_on: Mapped[date] = mapped_column(Date)
    expires_on: Mapped[date] = mapped_column(Date)
    document_id: Mapped[uuid.UUID | None] = _fk("documents.id", nullable=True, index=True)
    created_by_user_id: Mapped[uuid.UUID] = _fk("users.id", index=True)
    created_at: Mapped[datetime] = _stamp()


LIST_VERSION_STATUSES = ("draft", "pending_approval", "published", "superseded", "rejected")


class ListVersion(Base):
    """One immutable publication of a beverage list. Entries do not change after insert."""

    __tablename__ = "list_versions"
    __table_args__ = (
        UniqueConstraint("list_id", "number", name="uq_list_versions_list_number"),
        UniqueConstraint("public_token", name="uq_list_versions_public_token"),
        CheckConstraint(
            "status IN ('draft', 'pending_approval', 'published', 'superseded', 'rejected')",
            name="ck_list_versions_status",
        ),
        CheckConstraint("number >= 1", name="ck_list_versions_number"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    list_id: Mapped[uuid.UUID] = _fk("beverage_lists.id", index=True)
    number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="draft", server_default=text("'draft'"))
    approval_id: Mapped[uuid.UUID | None] = _fk("approvals.id", nullable=True, index=True)
    submitted_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    published_by_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    document_id: Mapped[uuid.UUID | None] = _fk("documents.id", nullable=True)
    public_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    public_revoked_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    created_at: Mapped[datetime] = _stamp()
    beverage_list: Mapped[BeverageList] = relationship()
    entries: Mapped[list["ListEntry"]] = relationship(
        back_populates="version",
        order_by="ListEntry.position",
        viewonly=True,
    )


class ListEntry(Base):
    """Insert-only snapshot of one list row. Prices and guest text stay as they were."""

    __tablename__ = "list_entries"
    __table_args__ = (
        CheckConstraint("position >= 0", name="ck_list_entries_position"),
        CheckConstraint("bottle_price_cents >= 0", name="ck_list_entries_bottle_price"),
        CheckConstraint("glass_price_cents >= 0", name="ck_list_entries_glass_price"),
    )

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    version_id: Mapped[uuid.UUID] = _fk("list_versions.id", index=True)
    section_name: Mapped[str] = mapped_column(String(200), default="", server_default=text("''"))
    position: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    sku_id: Mapped[uuid.UUID] = _fk("skus.id", index=True)
    bottle_price_cents: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    glass_price_cents: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    currency: Mapped[str] = _currency()
    display_name: Mapped[str] = mapped_column(String(200), default="")
    display_detail: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    version: Mapped[ListVersion] = relationship(back_populates="entries")


class Job(Base):
    """One unit of work for the database queue.

    ``payload`` is the job input. ``last_error`` is a short public message.
    The payload is not copied into the error or the log.
    """

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'dead')",
            name="ck_jobs_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_jobs_attempts"),
        CheckConstraint("max_attempts >= 1", name="ck_jobs_max_attempts"),
        Index("ix_jobs_status_run_at", "status", "run_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    venue_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("venues.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="queued", server_default=text("'queued'"))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, server_default=text("3"))
    run_at: Mapped[datetime] = mapped_column(AwareDateTime)
    locked_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(String(300), default="", server_default=text("''"))
    created_at: Mapped[datetime] = _stamp()
    updated_at: Mapped[datetime] = _stamp()
    started_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)


class PublicListSnapshot(Base):
    """Guest projection. The anonymous route reads only this table."""

    __tablename__ = "public_list_snapshots"

    token: Mapped[str] = mapped_column(String(128), primary_key=True)
    venue_name: Mapped[str] = mapped_column(String(200))
    rendered: Mapped[dict] = mapped_column(JSON)
    published_at: Mapped[datetime] = mapped_column(AwareDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)


@event.listens_for(ListEntry, "before_update")
def _list_entries_are_insert_only(_mapper, _connection, _target) -> None:
    raise ValueError("List entries are a snapshot and cannot change.")


@event.listens_for(ListEntry, "before_delete")
def _list_entries_are_not_deleted(_mapper, _connection, _target) -> None:
    raise ValueError("List entries are a snapshot and cannot be deleted.")
