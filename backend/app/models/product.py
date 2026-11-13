
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    brand: Mapped[str] = mapped_column(String(80), index=True)
    barcode: Mapped[str | None] = mapped_column(String(20))
    category: Mapped[str] = mapped_column(String(40))