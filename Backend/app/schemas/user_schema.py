from pydantic import BaseModel
from uuid import UUID


class UserBase(BaseModel):
    name: str


class UserCreate(UserBase):
    pass


class UserUpdate(BaseModel):
    name: str | None = None


class UserResponse(UserBase):
    id: UUID

    class Config:
        from_attributes = True
