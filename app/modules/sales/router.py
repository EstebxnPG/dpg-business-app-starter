from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy import Engine

from app.core.authorization import CurrentMembership, get_current_membership
from app.core.errors import error_response
from app.database import get_engine
from app.modules.sales.schemas import (
    ApprovalPinResponse,
    CreateSaleRequest,
    SaleResponse,
    SalesPolicyResponse,
    SetApprovalPinRequest,
    UpdateSalesPolicyRequest,
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
    SubmitSaleApproval,
    SubmitSaleCommand,
    SubmitSaleLine,
    get_sales_policy,
    set_approval_pin,
    submit_sale,
    update_sales_policy,
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
