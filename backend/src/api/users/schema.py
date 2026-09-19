from pydantic import BaseModel, EmailStr, Field, model_validator


class UpdateUserRequest(BaseModel):
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UpdateUserRequest":
        if self.email is None and self.password is None:
            raise ValueError("At least one of 'email' or 'password' must be provided")
        return self

