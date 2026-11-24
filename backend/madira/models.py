from __future__ import annotations

import uuid
from datetime import date, datetime
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
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from madira.db import Base
from madira.money import DEFAULT_CURRENCY
from madira.timestamps import AwareDateTime

ROLES = ("Owner", "Sommelier", "Manager", "Staff", "Auditor")


def _pk():
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def _fk(target: str, *, nullable: bool = False, index: bool = False):
    return mapped_column(Uuid, ForeignKey(target), nullable=nullable, index=index)


def _currency():
    return mapped_column(String(3), default=DEFAULT_CURRENCY, server_default=text("'USD'"))


def _stamp():
    return mapped_column(AwareDateTime, server_default=func.now())


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    # Manju's approved default. The compliance service only accepts 1..25.
    document_retention_years: Mapped[int] = mapped_column(
        Integer, nullable=False, default=7, server_default=text("7")
    )


class Venue(Base):
    __tablename__ = "venues"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_venues_org_slug"),)

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _fk("organizations.id", index=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80))
    currency: Mapped[str] = _currency()


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
    created_at: Mapped[datetime] = _stamp()
    contacts: Mapped[list[SupplierContact]] = relationship(back_populates="supplier", cascade="all, delete-orphan")
    items: Mapped[list[InventoryItem]] = relationship(back_populates="supplier")
    orders: Mapped[list[PurchaseOrder]] = relationship(back_populates="supplier")
    tastings: Mapped[list[Tasting]] = relationship(back_populates="supplier")


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


class Lesson(Base):
    __tablename__ = "lessons"
    __table_args__ = (UniqueConstraint("venue_id", "slug", name="uq_lessons_venue_slug"),)

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    slug: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(64), default="waitstaff")
    category: Mapped[str] = mapped_column(String(64), default="wine")
    body: Mapped[str] = mapped_column(Text, default="")


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    lesson_id: Mapped[uuid.UUID] = _fk("lessons.id")
    title: Mapped[str] = mapped_column(String(200))
    questions: Mapped[list] = mapped_column(JSON, default=list)


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    quiz_id: Mapped[uuid.UUID] = _fk("quizzes.id")
    staff_name: Mapped[str] = mapped_column(String(120), default="Floor")
    answers: Mapped[list] = mapped_column(JSON, default=list)
    score: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = _stamp()


class Tasting(Base):
    __tablename__ = "tastings"

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    supplier_id: Mapped[uuid.UUID] = _fk("suppliers.id")
    title: Mapped[str] = mapped_column(String(200))
    starts_at: Mapped[datetime] = mapped_column(AwareDateTime)
    ends_at: Mapped[datetime] = mapped_column(AwareDateTime)
    location: Mapped[str] = mapped_column(String(200), default="Maison Madira cellar")
    notes: Mapped[str] = mapped_column(Text, default="")
    ics: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _stamp()
    supplier: Mapped[Supplier] = relationship(back_populates="tastings")


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

    id: Mapped[uuid.UUID] = _pk()
    venue_id: Mapped[uuid.UUID] = _fk("venues.id", index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    reply: Mapped[str] = mapped_column(Text, default="")
    delegated: Mapped[list] = mapped_column(JSON, default=list)
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
