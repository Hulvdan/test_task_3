from contextlib import asynccontextmanager

import sqlalchemy as sa
from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

from .settings import settings

_Table = declarative_base()


class Organization(_Table):
    __tablename__ = "organizations"

    id = Column(Integer, autoincrement=True, primary_key=True)
    name = Column(String, nullable=False)
    building_id = Column(Integer, ForeignKey("buildings.id"), nullable=False)

    building = relationship("Building", lazy="raise")
    kinds = relationship("Kind", secondary="organizations_kinds", lazy="raise")
    phones = relationship("Phone", lazy="raise")


class Phone(_Table):
    __tablename__ = "phones"

    id = Column(Integer, autoincrement=True, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    phone = Column(String, nullable=False)


class Building(_Table):
    __tablename__ = "buildings"

    id = Column(Integer, autoincrement=True, primary_key=True)
    address = Column(String, nullable=False)
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)


class Kind(_Table):
    __tablename__ = "kinds"

    id = Column(Integer, autoincrement=True, primary_key=True)
    name = Column(String, nullable=False)
    parent_id = Column(Integer, ForeignKey("kinds.id"), nullable=True)

    # Денормализовал массив id вышестоящих родителей.
    parent_ids = Column(ARRAY(Integer), nullable=False)


class OrganizationKind(_Table):
    __tablename__ = "organizations_kinds"

    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=False, primary_key=True
    )
    kind_id = Column(Integer, ForeignKey("kinds.id"), nullable=False, primary_key=True)

    __table_args__ = (
        sa.UniqueConstraint("organization_id", "kind_id", name="organization_kind_idx"),
    )


_engine = None
_sessionmaker = None


# Для pytest `custom_poolclass = NullPool`, чтобы работало с asyncio.
def init_engine_and_sessionmaker(*, custom_poolclass=None):
    global _engine
    global _sessionmaker

    assert _engine is None
    assert _sessionmaker is None

    _engine = create_async_engine(settings.postgres_dsn, poolclass=custom_poolclass)
    _sessionmaker = sa.orm.sessionmaker(
        bind=_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=AsyncSession,
    )


async def make_session():
    assert _sessionmaker is not None

    session = _sessionmaker()
    try:
        yield session
    finally:
        await session.close()


async def reinit_db_from_scratch():
    assert _engine is not None

    async with asynccontextmanager(make_session)() as session:
        await session.execute(sa.text("DROP SCHEMA IF EXISTS public CASCADE"))
        await session.execute(sa.text("CREATE SCHEMA public"))
        await session.commit()

    async with _engine.begin() as conn:
        await conn.run_sync(_Table.metadata.create_all)
