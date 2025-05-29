from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import db, services


@asynccontextmanager
async def app_lifespan(_):
    db.init_engine_and_sessionmaker()

    # Пересоздаю БД при поднятии сервиса.
    await services.fill_db_with_initial_data()
    yield


app = FastAPI(lifespan=app_lifespan)


@app.exception_handler(services.DomainError)
async def domain_errors_handler(_: Request, exc: services.DomainError):
    return JSONResponse(status_code=exc.status, content={"message": exc.message})


@app.get("/orgs/{org_id}")
async def organization_endpoint(
    org_id: int, session=Depends(db.make_session)
) -> services.OrganizationResponse:
    """Вывод информации об организации по её идентификатору."""
    return await services.get_organization(session, org_id=org_id)


@app.get("/orgs/")
async def organizations_endpoint(
    session=Depends(db.make_session),
    # Фильтр по названию
    name: str | None = None,
    # Фильтр по зданию
    building_id: int | None = None,
    # Фильтр по виду деятельности
    kind_id: int | None = None,
    # Фильтр по виду деятельности и его родителям
    kind_id_with_parents: int | None = None,
    # Фильтр в заданном радиусе относительно указанной точки
    x: float | None = None,
    y: float | None = None,
    radius: float | None = None,
    # Фильтр по прямоугольной области
    rect_x: float | None = None,
    rect_y: float | None = None,
    rect_w: float | None = None,
    rect_h: float | None = None,
) -> list[services.OrganizationResponse]:
    """Список организаций. Пагинацию не прикручивал.

    Фильтрация по геопозиции здания организации:
    1) По радиусу и точке. Требуется указать `x`, `y`, `radius`.
    2) По прямоугольной области. Требуется указать все `rect_*`.
    """
    return await services.list_organizations(
        session,
        name=name,
        building_id=building_id,
        kind_id=kind_id,
        kind_id_with_parents=kind_id_with_parents,
        x=x,
        y=y,
        radius=radius,
        rect_x=rect_x,
        rect_y=rect_y,
        rect_w=rect_w,
        rect_h=rect_h,
    )


@app.get("/buildings/")
async def buildings_endpoint(
    session=Depends(db.make_session),
) -> list[services.BuildingResponse]:
    """Список зданий. Пагинацию не прикручивал."""
    return await services.list_buildings(session)


@app.get("/kinds/")
async def kinds_endpoint(session=Depends(db.make_session)) -> list[services.KindResponse]:
    """Список видов деятельности организаций."""
    return await services.list_kinds(session)
