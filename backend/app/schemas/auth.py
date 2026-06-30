from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: str     # plain str — DB lookup handles validation; EmailStr rejects .local TLDs
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    must_change_password: bool = False


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
