from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse

from app.dependencies import get_current_user
from app.services.google_service import GoogleService

router = APIRouter()


@router.get("/google/auth-url")
async def google_auth_url(_user=Depends(get_current_user)):
    url = GoogleService.get_auth_url()
    return {"auth_url": url}


@router.get("/google/callback")
async def google_callback(code: str, state: str = ""):
    try:
        GoogleService.exchange_code(code)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    # Redirect back to the frontend
    return RedirectResponse(url="http://localhost:3000?google=connected")


@router.get("/google/status")
async def google_status(_user=Depends(get_current_user)):
    connected = GoogleService.is_connected()
    return {"connected": connected}
