from datetime import date, time
from pydantic import BaseModel, Field


class SearchProductsInput(BaseModel):
    category: str | None = Field(
        default=None,
        description="Product category: coffee, tea, pastry, or dessert"
    )
    product_name: str | None = Field(
        default=None,
        description="Specific product name, such as Americano, Latte, or Croissant"
    )


class CheckStockInput(BaseModel):
    product_id: int = Field(gt=0, description="Positive product ID")


class PlaceOrderInput(BaseModel):
    customer_name: str = Field(min_length=1, max_length=100)
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=10)


class ReserveTableInput(BaseModel):
    customer_name: str = Field(min_length=1, max_length=100)
    reservation_date: date
    reservation_time: time
    number_of_people: int = Field(gt=0, le=20)


class UpdateStockInput(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(ge=0, le=1000, description="New stock quantity")
