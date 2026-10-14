from typing import Generic, T, List

from pydantic import BaseModel, Field


class CountResults(BaseModel, Generic[T]):
    count_result: int
    results: List[T]


class Offer(BaseModel):
    inventory: str | int
    offer_description: str
    condition: str
    quantity: int | str
    offer_country: str | int
    price: float
    int_leadtime_start: int | None
    int_leadtime_end: int | None
    company: str | int
    commit_date_unix: float | None
    price_unit: str | int | None
    aviator_purchase: str | int
    to_buy: bool
    sale_type: str
    certificate: str | None = Field(default=None)
    comment: str | None = Field(default='')
    pre_packing: str | None = Field(default='EA')


class Context(BaseModel):
    offer_country: dict[str, str | int]
    company: dict[str, str | int]
    offer_country_short: dict[str, str | int]
    inventory: dict[str, str | int]
    aviator_purchase: str | int
    price_unit: dict[str, str | int]


class OffersRequest(BaseModel):
    part_numbers: List[str]
    context: Context


class DASICookies(BaseModel):
    ASPXANONYMOUS: str
    ASP_NET_SessionId: str
    DASI_CustomerSessionGUIDCookie: str
    NOPCOMMERCE_AUTH: str


class DASIRequest(BaseModel):
    cookies: DASICookies


class LoginTriesRequest(BaseModel):
    sites: List[str] = Field(
        default=[
            'e-csat',
            'AvioSupport',
            'Proponent',
            'Satair',
            'Aviall',
            'BDSI',
            'Wencor',
            'DASI',
            'AeroBay',
            'SatairMarket'
        ]
    )
