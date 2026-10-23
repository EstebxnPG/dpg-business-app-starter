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
    UpdateProductRequest,
)
from app.modules.products.use_cases import (
    InvalidProductCursorError,
    ProductHasStockError,
    ProductNotFoundError,
    ProductPriceBelowCostError,
    ProductSkuConflictError,
    create_product,
    get_product,
    list_products,
    update_product,
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
        product = create_product(
            engine,
            membership,
            payload.sku,
            payload.name,
            payload.cost,
            payload.sale_price,
        )
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
    search: Annotated[str | None, Query(min_length=1, max_length=160)] = None,
) -> ProductListResponse | Response:
    try:
        page = list_products(
            engine, membership, limit, cursor, include_inactive, search
        )
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


@router.get("/{product_id}", response_model=ProductResponse)
def get_product_endpoint(
    product_id: UUID,
    request: Request,
    membership: Annotated[CurrentMembership, Depends(get_current_membership)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> ProductResponse | Response:
    try:
        product = get_product(engine, membership, product_id)
    except ProductNotFoundError:
        return error_response(
            request,
            status_code=status.HTTP_404_NOT_FOUND,
            code="PRODUCT_NOT_FOUND",
            message="The product is unavailable in this organization.",
        )
    return ProductResponse(**product.__dict__)


@router.patch("/{product_id}", response_model=ProductResponse)
def update_product_endpoint(
    product_id: UUID,
    payload: UpdateProductRequest,
    request: Request,
    membership: Annotated[CurrentMembership, Depends(get_current_membership)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> ProductResponse | Response:
    try:
        product = update_product(
            engine,
            membership,
            product_id,
            payload.name,
            payload.active,
            payload.cost,
            payload.sale_price,
        )
    except ProductNotFoundError:
        return error_response(
            request,
            status_code=status.HTTP_404_NOT_FOUND,
            code="PRODUCT_NOT_FOUND",
            message="The product is unavailable in this organization.",
        )
    except ProductHasStockError:
        return error_response(
            request,
            status_code=status.HTTP_409_CONFLICT,
            code="PRODUCT_HAS_STOCK",
            message="A product with stock cannot be deactivated.",
        )
    except ProductPriceBelowCostError:
        return error_response(
            request,
            status_code=status.HTTP_409_CONFLICT,
            code="PRODUCT_PRICE_BELOW_COST",
            message="The sale price must not be below the product cost.",
        )
    return ProductResponse(**product.__dict__)
