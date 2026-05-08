from fastapi import APIRouter, HTTPException, status

from app.models.requests import LoginRequest, RefreshRequest, RegisterRequest
from app.models.responses import TokenResponse, UserResponse
from app.services.auth_service import AuthService

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest):
    try:
        user = AuthService.register(req.email, req.password, req.name)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return UserResponse(**user)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    user = AuthService.login(req.email, req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    payload = {"sub": user["user_id"], "email": user["email"], "name": user["name"]}
    return TokenResponse(
        access_token=AuthService.create_access_token(payload),
        refresh_token=AuthService.create_refresh_token(payload),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest):
    payload = AuthService.decode_refresh_token(req.refresh_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    token_payload = {"sub": payload["sub"], "email": payload["email"], "name": payload["name"]}
    return TokenResponse(
        access_token=AuthService.create_access_token(token_payload),
        refresh_token=AuthService.create_refresh_token(token_payload),
    )
