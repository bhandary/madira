from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from madira.db import Base


class Menu(Base):
    __tablename__ = "menus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="Untitled menu")
    source_type: Mapped[str] = mapped_column(String(32), default="text")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    cuisine: Mapped[str] = mapped_column(String(80), default="")
    price_tier: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    dishes: Mapped[list[Dish]] = relationship(back_populates="menu", cascade="all, delete-orphan")


class Dish(Base):
    __tablename__ = "dishes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    menu_id: Mapped[int] = mapped_column(ForeignKey("menus.id"))
    name: Mapped[str] = mapped_column(String(200))
    course: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    flavor_profile: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[float] = mapped_column(Float, default=0)
    menu: Mapped[Menu] = relationship(back_populates="dishes")
    pairings: Mapped[list[Pairing]] = relationship(back_populates="dish", cascade="all, delete-orphan")


class Pairing(Base):
    __tablename__ = "pairings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"))
    category: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    producer: Mapped[str] = mapped_column(String(200), default="")
    region: Mapped[str] = mapped_column(String(200), default="")
    style: Mapped[str] = mapped_column(String(200), default="")
    vintage: Mapped[str] = mapped_column(String(32), default="")
    rationale: Mapped[str] = mapped_column(Text, default="")
    price_tier: Mapped[str] = mapped_column(String(32), default="")
    glass_price: Mapped[float] = mapped_column(Float, default=0)
    bottle_price: Mapped[float] = mapped_column(Float, default=0)
    dish: Mapped[Dish] = relationship(back_populates="pairings")


class BeverageList(Base):
    __tablename__ = "beverage_lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="House list")
    budget: Mapped[float] = mapped_column(Float, default=0)
    target_margin: Mapped[float] = mapped_column(Float, default=3.0)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    items: Mapped[list[ListItem]] = relationship(back_populates="beverage_list", cascade="all, delete-orphan")


class ListItem(Base):
    __tablename__ = "list_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("beverage_lists.id"))
    category: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    producer: Mapped[str] = mapped_column(String(200), default="")
    region: Mapped[str] = mapped_column(String(200), default="")
    style: Mapped[str] = mapped_column(String(200), default="")
    vintage: Mapped[str] = mapped_column(String(32), default="")
    cost: Mapped[float] = mapped_column(Float, default=0)
    pour_price: Mapped[float] = mapped_column(Float, default=0)
    bottle_price: Mapped[float] = mapped_column(Float, default=0)
    margin_pct: Mapped[float] = mapped_column(Float, default=0)
    beverage_list: Mapped[BeverageList] = relationship(back_populates="items")


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(64), default="distributor")
    contact_email: Mapped[str] = mapped_column(String(200), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    items: Mapped[list[InventoryItem]] = relationship(back_populates="supplier")
    orders: Mapped[list[PurchaseOrder]] = relationship(back_populates="supplier")
    tastings: Mapped[list[Tasting]] = relationship(back_populates="supplier")


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(32))
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    on_hand: Mapped[int] = mapped_column(Integer, default=0)
    par: Mapped[int] = mapped_column(Integer, default=0)
    unit_cost: Mapped[float] = mapped_column(Float, default=0)
    depletion_30d: Mapped[int] = mapped_column(Integer, default=0)
    unit: Mapped[str] = mapped_column(String(32), default="btl")
    supplier: Mapped[Supplier | None] = relationship(back_populates="items")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    status: Mapped[str] = mapped_column(String(32), default="draft")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    supplier: Mapped[Supplier] = relationship(back_populates="orders")
    lines: Mapped[list[POLine]] = relationship(back_populates="purchase_order", cascade="all, delete-orphan")


class POLine(Base):
    __tablename__ = "po_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"))
    sku: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    qty: Mapped[int] = mapped_column(Integer, default=1)
    unit_cost: Mapped[float] = mapped_column(Float, default=0)
    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="lines")


class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(64), default="waitstaff")
    category: Mapped[str] = mapped_column(String(64), default="wine")
    body: Mapped[str] = mapped_column(Text, default="")


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"))
    title: Mapped[str] = mapped_column(String(200))
    questions: Mapped[list] = mapped_column(JSON, default=list)


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"))
    staff_name: Mapped[str] = mapped_column(String(120), default="Floor")
    answers: Mapped[list] = mapped_column(JSON, default=list)
    score: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Tasting(Base):
    __tablename__ = "tastings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    title: Mapped[str] = mapped_column(String(200))
    starts_at: Mapped[str] = mapped_column(String(40))
    ends_at: Mapped[str] = mapped_column(String(40))
    location: Mapped[str] = mapped_column(String(200), default="Maison Madira cellar")
    notes: Mapped[str] = mapped_column(Text, default="")
    ics: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    supplier: Mapped[Supplier] = relationship(back_populates="tastings")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message: Mapped[str] = mapped_column(Text, default="")
    reply: Mapped[str] = mapped_column(Text, default="")
    delegated: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
