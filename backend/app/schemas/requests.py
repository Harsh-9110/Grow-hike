from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field, field_validator

def exact_decimal(value):
    if isinstance(value, (float, bool)):
        raise ValueError("Send decimal amounts as strings, for example '100.25'")
    return value


Money = Annotated[Decimal, BeforeValidator(exact_decimal), Field(gt=0, max_digits=22, decimal_places=8, allow_inf_nan=False)]
Quantity = Annotated[Decimal, BeforeValidator(exact_decimal), Field(gt=0, max_digits=16, decimal_places=8, allow_inf_nan=False)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(StrictModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=72)

    @field_validator("password")
    @classmethod
    def password_bytes(cls, value: str) -> str:
        if len(value.encode()) > 72:
            raise ValueError("Password must fit in 72 UTF-8 bytes")
        return value


class OrderRequest(StrictModel):
    symbol: str = Field(min_length=1, max_length=40, pattern=r"^[A-Z0-9.^=\-]+$")
    side: Literal["BUY", "SELL"]
    quantity: Quantity


class AlertRequest(StrictModel):
    symbol: str = Field(max_length=40)
    direction: Literal["above", "below"]
    target: Money


class SymbolRequest(StrictModel):
    symbol: str = Field(max_length=40)


class ImportConfirm(StrictModel):
    preview_id: str


class IPORequest(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    issue_price: Money
    gmp: Annotated[Decimal, BeforeValidator(exact_decimal)] = Field(max_digits=22, decimal_places=8, allow_inf_nan=False)
    subscription: Annotated[Decimal, BeforeValidator(exact_decimal)] = Field(ge=0, le=10000, allow_inf_nan=False)
