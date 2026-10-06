from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import Engine

from app.core.authorization import CurrentMembership, get_current_membership
from app.core.errors import error_response
from app.database import get_engine
from app.modules.products.schemas import (
    CreateProductRequest,
    ProductListResponse,
    ProductResponse,
)
from app.modules.products.use_cases import (
    InvalidProductCursorError,
    ProductSkuConflictError,
    create_product,
    list_products,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/products", tags=["products"]
)


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product_endpoint(
    payload: CreateProductRequest,
    request: Request,
    membership: Annotated[CurrentMembership, Depends(get_current_membership)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> ProductResponse | Response:
    try:
        product = create_product(engine, membership, payload.sku, payload.name)
    except ProductSkuConflictError:
        return error_response(
            request,
            status_code=status.HTTP_409_CONFLICT,
            code="PRODUCT_SKU_CONFLICT",
            message="A product with this SKU already exists in the organization.",
        )
    return ProductResponse(**product.__dict__)


@router.get("", response_model=ProductListResponse)
def list_products_endpoint(
    request: Request,
    membership: Annotated[CurrentMembership, Depends(get_current_membership)],
    engine: Annotated[Engine, Depends(get_engine)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: UUID | None = None,
    include_inactive: bool = False,
) -> ProductListResponse | Response:
    try:
        page = list_products(engine, membership, limit, cursor, include_inactive)
    except InvalidProductCursorError:
        return error_response(
            request,
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_CURSOR",
            message="The product cursor is invalid for this organization and filter.",
        )
    return ProductListResponse(
        items=[item.__dict__ for item in page.items],
        next_cursor=page.next_cursor,
    )
