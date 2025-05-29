from contextlib import asynccontextmanager

from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload, selectinload

from . import utils
from .db import Building, Kind, Organization, OrganizationKind, Phone
from .utils import log


class DomainError(Exception):
    status: int
    message: str


class OrganizationNotFoundError(DomainError):
    status = 404
    message = "Организация не найдена"


class GeoSearchError(DomainError):
    status = 400
    message = "Можно указать либо (x, y, radius), либо (rect_x, rect_y, rect_w, rect_h)"


class KindResponse(BaseModel):
    id: int
    name: str
    parent_id: int | None
    parent_ids: list[int]

    @classmethod
    def from_sa(cls, value):
        return cls(
            id=value.id,
            name=value.name,
            parent_id=value.parent_id,
            parent_ids=value.parent_ids,
        )


class BuildingResponse(BaseModel):
    id: int
    address: str
    x: float
    y: float

    @classmethod
    def from_sa(cls, value):
        return cls(
            id=value.id,
            address=value.address,
            x=value.x,
            y=value.y,
        )


class OrganizationResponse(BaseModel):
    id: int
    name: str
    phones: list[str]
    building: BuildingResponse
    kinds: list[KindResponse]

    @classmethod
    def from_sa(cls, value):
        return cls(
            id=value.id,
            name=value.name,
            phones=[i.phone for i in value.phones],
            building=BuildingResponse.from_sa(value.building),
            kinds=[KindResponse.from_sa(k) for k in value.kinds],
        )


async def get_organization(session, org_id: int) -> OrganizationResponse:
    value = (
        await session.execute(
            select(Organization)
            .options(
                joinedload(Organization.building),
                selectinload(Organization.kinds),
                selectinload(Organization.phones),
            )
            .filter(Organization.id == org_id)
            .limit(1)
        )
    ).scalar()

    if not value:
        raise OrganizationNotFoundError

    return OrganizationResponse.from_sa(value)


async def list_organizations(
    session,
    *,
    name: str | None,
    building_id: int | None,
    kind_id: int | None,
    kind_id_with_parents: int | None,
    x: float | None,
    y: float | None,
    radius: float | None,
    rect_x: float | None,
    rect_y: float | None,
    rect_w: float | None,
    rect_h: float | None,
) -> list[OrganizationResponse]:
    geo_search_by_radius = utils.any_isnt_none(x, y, radius)
    geo_search_by_rect = utils.any_isnt_none(rect_x, rect_y, rect_w, rect_h)

    if geo_search_by_radius and geo_search_by_rect:
        raise GeoSearchError
    if geo_search_by_radius and not utils.all_arent_none(x, y, radius):
        raise GeoSearchError
    if geo_search_by_rect and not utils.all_arent_none(rect_x, rect_y, rect_w, rect_h):
        raise GeoSearchError

    query = select(Organization)

    if name is not None:
        query = query.filter(utils.sa_column_contains(Organization.name, name))

    if building_id is not None:
        query = query.filter(Organization.building_id == building_id)

    if kind_id is not None:
        query = query.join(
            OrganizationKind, OrganizationKind.organization_id == Organization.id
        ).filter(OrganizationKind.kind_id == kind_id)

    if kind_id_with_parents is not None:
        query = (
            query.join(
                OrganizationKind, OrganizationKind.organization_id == Organization.id
            )
            .join(Kind, Kind.id == OrganizationKind.kind_id)
            .filter(
                or_(
                    OrganizationKind.kind_id == kind_id_with_parents,
                    Kind.parent_ids.any(kind_id_with_parents),
                )
            )
        )

    if geo_search_by_radius:
        query = query.filter(
            (Building.x - x) * (Building.x - x) + (Building.y - y) * (Building.y - y)
            < radius * radius
        )
    elif geo_search_by_rect:
        query = query.filter(
            Building.x >= rect_x,
            Building.x <= rect_x + rect_w,
            Building.y >= rect_y,
            Building.y <= rect_y + rect_h,
        )

    query = query.options(
        selectinload(Organization.kinds),
        joinedload(Organization.building),
        selectinload(Organization.phones),
    )

    values = (await session.execute(query)).scalars()
    return [OrganizationResponse.from_sa(i) for i in values]


async def list_kinds(session) -> list[KindResponse]:
    values = (await session.execute(select(Kind))).scalars()
    return [KindResponse.from_sa(i) for i in values]


async def list_buildings(session) -> list[BuildingResponse]:
    values = (await session.execute(select(Building))).scalars()
    return [BuildingResponse.from_sa(i) for i in values]


async def fill_db_with_initial_data():
    from .db import make_session

    log.info("Filling db with with initial data...")

    # Создание таблиц при запуске без alembic.
    # from .db import reinit_db_from_scratch
    # await reinit_db_from_scratch()

    # Заполнение тестовыми данными.
    async with asynccontextmanager(make_session)() as session:
        # Создание дерева видов деятельности.
        kinds_to_create = [
            [
                "Еда",
                ["Мясная продукция"],
                ["Молочная продукция"],
            ],
            [
                "Автомобили",
                ["Грузовые"],
                [
                    "Легковые",
                    ["Запчасти"],
                    ["Аксессуары"],
                ],
            ],
        ]

        created_kinds = []
        kinds_to_process = [(i, None) for i in kinds_to_create]

        parents_by_kind: dict[int, int] = {}

        for kind, parent_id_or_none in kinds_to_process:
            parent_ids = []
            p_id = parent_id_or_none
            while p_id in parents_by_kind:
                parent_ids.append(p_id)
                p_id = parents_by_kind[p_id]

            kind_instance = Kind(
                name=kind[0], parent_id=parent_id_or_none, parent_ids=parent_ids
            )
            created_kinds.append(kind_instance)
            session.add(kind_instance)
            await session.commit()

            parents_by_kind[kind_instance.id] = kind_instance.parent_id

            for i in range(1, len(kind)):
                kinds_to_process.append((kind[i], kind_instance.id))

        await session.commit()

        # Создание зданий.
        buildings = [
            Building(
                address="Россия, г. Долгопрудный, Новоселов ул., д. 19 кв.196",
                x=-14.09921,
                y=-152.62413,
            ),
            Building(
                address="Россия, г. Саратов, Красноармейская ул., д. 8 кв.28",
                x=64.72257,
                y=9.97868,
            ),
            Building(
                address="Казахстан, Белгород, ул. Хуторская, 5, 210",
                x=-23.49938,
                y=39.48771,
            ),
            Building(
                address="Санкт-Петербург, Дружбы ул., д. 6 кв.135",
                x=-8.66373,
                y=-31.77276,
            ),
        ]
        session.add_all(buildings)
        await session.commit()

        # Создание организаций.
        organizations = [
            Organization(name="Рога и копыта", building_id=buildings[0].id),
            Organization(name="Gugle", building_id=buildings[0].id),
            Organization(name="Сбербутылк", building_id=buildings[1].id),
        ]
        session.add_all(organizations)
        await session.commit()

        session.add_all(
            [
                Phone(organization_id=organizations[0].id, phone="88005553535"),
                Phone(organization_id=organizations[0].id, phone="88005553535"),
                Phone(organization_id=organizations[1].id, phone="+5625328511"),
                Phone(organization_id=organizations[2].id, phone="+66025381423"),
            ]
        )

        # Привязка видов деятельности к компаниям.
        session.add_all(
            [
                OrganizationKind(
                    organization_id=organizations[0].id, kind_id=created_kinds[0].id
                ),
                OrganizationKind(
                    organization_id=organizations[1].id, kind_id=created_kinds[1].id
                ),
                OrganizationKind(
                    organization_id=organizations[1].id, kind_id=created_kinds[2].id
                ),
                OrganizationKind(
                    organization_id=organizations[2].id, kind_id=created_kinds[5].id
                ),
            ]
        )
        await session.commit()

    log.info("Filled db with with initial data!")
