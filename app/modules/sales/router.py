from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy import Engine

from app.core.authorization import CurrentMembership, get_current_membership
from app.core.errors import error_response
from app.database import get_engine
from app.modules.sales.returns_service import (
    ReturnIdempotencyConflictError,
    ReturnQuantityExceededError,
    ReturnSaleNotFoundError,
    SaleAlreadyAdjustedError,
)
from app.modules.sales.schemas import (
    ApprovalPinResponse,
    CreateSaleRequest,
    CreateSaleReturnRequest,
    SaleListResponse,
    SaleReceiptResponse,
    SaleResponse,
    SaleReturnResponse,
    SalesPolicyResponse,
    SetApprovalPinRequest,
    UpdateSalesPolicyRequest,
    VoidSaleRequest,
)
from app.modules.sales.service import (
    ApprovalPinLockedError,
    DiscountApprovalRequiredError,
    DiscountReasonRequiredError,
    InactiveSaleContextError,
    InvalidApprovalPinError,
    SaleContextNotFoundError,
    SaleIdempotencyConflictError,
    SaleInsufficientStockError,
    SalePriceAboveListError,
    SalePriceBelowCostError,
)
from app.modules.sales.use_cases import (
    InvalidSaleCursorError,
    SaleNotFoundError,
    SubmitReturnLine,
    SubmitSaleApproval,
    SubmitSaleCommand,
    SubmitSaleLine,
    SubmitSaleReturnCommand,
    get_sale_receipt,
    get_sales_policy,
    list_sales,
    set_approval_pin,
    submit_sale,
    submit_sale_return,
    update_sales_policy,
    void_sale,
)

router = APIRouter(prefix="/organizations/{organization_id}/sales", tags=["sales"])


@router.post("", response_model=SaleResponse, status_code=status.HTTP_201_CREATED)
def create_sale_endpoint(
    organization_id: UUID,
    payload: CreateSaleRequest,
    request: Request,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    membership: Annotated[CurrentMembership, Depends(get_current_membership)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> SaleResponse | Response:
    command = SubmitSaleCommand(
        organization_id=organization_id,
        warehouse_id=payload.warehouse_id,
        lines=tuple(
            SubmitSaleLine(line.product_id, line.quantity, line.unit_price)
            for line in payload.lines
        ),
        discount_reason=payload.discount_reason,
        approval=(
            SubmitSaleApproval(payload.approval.approver_user_id, payload.approval.pin)
            if payload.approval
            else None
        ),
        idempotency_key=idempotency_key,
    )
    try:
        result = submit_sale(engine, membership, command)
    except SaleContextNotFoundError:
        return error_response(
            request,
            status_code=404,
            code="SALE_CONTEXT_NOT_FOUND",
            message="A sale resource is unavailable in this organization.",
        )
    except InactiveSaleContextError:
        return error_response(
            request,
            status_code=409,
            code="SALE_CONTEXT_INACTIVE",
            message="The warehouse and products must be active.",
        )
    except SalePriceBelowCostError:
        return error_response(
            request,
            status_code=409,
            code="SALE_PRICE_BELOW_COST",
            message="A product cannot be sold below its recorded cost.",
        )
    except SalePriceAboveListError:
        return error_response(
            request,
            status_code=409,
            code="SALE_PRICE_ABOVE_LIST",
            message="Use the catalog price when no discount applies.",
        )
    except DiscountReasonRequiredError:
        return error_response(
            request,
            status_code=409,
            code="DISCOUNT_REASON_REQUIRED",
            message="Discounted sales require a reason.",
        )
    except DiscountApprovalRequiredError:
        return error_response(
            request,
            status_code=409,
            code="DISCOUNT_APPROVAL_REQUIRED",
            message="This discount requires administrator approval.",
        )
    except InvalidApprovalPinError:
        return error_response(
            request,
            status_code=403,
            code="INVALID_APPROVAL_PIN",
            message="The approval credentials are invalid.",
        )
    except ApprovalPinLockedError:
        return error_response(
            request,
            status_code=423,
            code="APPROVAL_PIN_LOCKED",
            message="Approval is temporarily locked after repeated failures.",
        )
    except SaleInsufficientStockError as error:
        return error_response(
            request,
            status_code=409,
            code="INSUFFICIENT_STOCK",
            message="There is not enough stock to complete the sale.",
            details={"product_id": str(error.product_id)},
        )
    except SaleIdempotencyConflictError:
        return error_response(
            request,
            status_code=409,
            code="IDEMPOTENCY_KEY_REUSED",
            message="The idempotency key was already used with different data.",
        )

    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return SaleResponse(**result.__dict__)


@router.get("", response_model=SaleListResponse)
def list_sales_endpoint(
    request: Request,
    membership: Annotated[CurrentMembership, Depends(get_current_membership)],
    engine: Annotated[Engine, Depends(get_engine)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: UUID | None = None,
) -> SaleListResponse | Response:
    try:
        page = list_sales(engine, membership, limit, cursor)
    except InvalidSaleCursorError:
        return error_response(
            request,
            status_code=400,
            code="INVALID_CURSOR",
            message="The sale cursor is invalid for this organization.",
        )
    return SaleListResponse(
        items=[item.__dict__ for item in page.items], next_cursor=page.next_cursor
    )


@router.get("/receipts/{sale_id}", response_model=SaleReceiptResponse)
def read_sale_receipt(
    sale_id: UUID,
    request: Request,
    membership: Annotated[CurrentMembership, Depends(get_current_membership)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> SaleReceiptResponse | Response:
    try:
        receipt = get_sale_receipt(engine, membership, sale_id)
    except SaleNotFoundError:
        return error_response(
            request,
            status_code=404,
            code="SALE_NOT_FOUND",
            message="The sale is unavailable in this organization.",
        )
    return SaleReceiptResponse(
        **{
            key: value
            for key, value in receipt.__dict__.items()
            if key not in {"lines", "adjustments"}
        },
        lines=[line.__dict__ for line in receipt.lines],
        adjustments=[adjustment.__dict__ for adjustment in receipt.adjustments],
    )


def _return_error_response(request: Request, error: Exception) -> Response:
    if isinstance(error, ReturnSaleNotFoundError):
        return error_response(
            request,
            status_code=404,
            code="SALE_NOT_FOUND",
            message="The sale is unavailable in this organization.",
        )
    if isinstance(error, ReturnQuantityExceededError):
        return error_response(
            request,
            status_code=409,
            code="RETURN_QUANTITY_EXCEEDED",
            message="The returned quantity exceeds the remaining sold quantity.",
            details={"product_id": str(error.product_id)},
        )
    if isinstance(error, SaleAlreadyAdjustedError):
        return error_response(
            request,
            status_code=409,
            code="SALE_ALREADY_ADJUSTED",
            message="This sale cannot be adjusted by the requested operation.",
        )
    return error_response(
        request,
        status_code=409,
        code="IDEMPOTENCY_KEY_REUSED",
        message="The idempotency key was already used with different data.",
    )


@router.post(
    "/{sale_id}/returns",
    response_model=SaleReturnResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_sale_return_endpoint(
    sale_id: UUID,
    payload: CreateSaleReturnRequest,
    request: Request,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    membership: Annotated[CurrentMembership, Depends(get_current_membership)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> SaleReturnResponse | Response:
    try:
        result = submit_sale_return(
            engine,
            membership,
            SubmitSaleReturnCommand(
                sale_id=sale_id,
                lines=tuple(
                    SubmitReturnLine(line.product_id, line.quantity, line.disposition)
                    for line in payload.lines
                ),
                refund_resolution=payload.refund_resolution,
                reason=payload.reason,
                idempotency_key=idempotency_key,
            ),
        )
    except (
        ReturnSaleNotFoundError,
        ReturnQuantityExceededError,
        SaleAlreadyAdjustedError,
        ReturnIdempotencyConflictError,
    ) as error:
        return _return_error_response(request, error)
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return SaleReturnResponse(**result.__dict__)


@router.post(
    "/{sale_id}/void",
    response_model=SaleReturnResponse,
    status_code=status.HTTP_201_CREATED,
)
def void_sale_endpoint(
    sale_id: UUID,
    payload: VoidSaleRequest,
    request: Request,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    membership: Annotated[CurrentMembership, Depends(get_current_membership)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> SaleReturnResponse | Response:
    try:
        result = void_sale(
            engine,
            membership,
            sale_id,
            payload.refund_resolution,
            payload.reason,
            idempotency_key,
        )
    except (
        ReturnSaleNotFoundError,
        ReturnQuantityExceededError,
        SaleAlreadyAdjustedError,
        ReturnIdempotencyConflictError,
    ) as error:
        return _return_error_response(request, error)
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return SaleReturnResponse(**result.__dict__)


@router.get("/policy", response_model=SalesPolicyResponse)
def read_sales_policy(
    membership: Annotated[CurrentMembership, Depends(get_current_membership)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> SalesPolicyResponse:
    return SalesPolicyResponse(
        salesperson_max_discount_rate=get_sales_policy(engine, membership)
    )


@router.patch("/policy", response_model=SalesPolicyResponse)
def update_sales_policy_endpoint(
    payload: UpdateSalesPolicyRequest,
    membership: Annotated[CurrentMembership, Depends(get_current_membership)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> SalesPolicyResponse:
    rate = update_sales_policy(
        engine, membership, payload.salesperson_max_discount_rate
    )
    return SalesPolicyResponse(salesperson_max_discount_rate=rate)


@router.put("/approval-pin", response_model=ApprovalPinResponse)
def set_approval_pin_endpoint(
    payload: SetApprovalPinRequest,
    membership: Annotated[CurrentMembership, Depends(get_current_membership)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> ApprovalPinResponse:
    set_approval_pin(engine, membership, payload.pin)
    return ApprovalPinResponse(configured=True)
