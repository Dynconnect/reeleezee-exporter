"""Authentication routes: login, logout, session info."""

import json

from fastapi import APIRouter, Depends, HTTPException, Response

from reeleezee_exporter.client import AuthenticationError, ReeleezeeClient

from ..auth import (
    create_session,
    decrypt_credentials,
    delete_session,
    encrypt_credentials,
    get_current_session,
)
from ..schemas import LoginRequest, LoginResponse

router = APIRouter(tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, response: Response):
    """Authenticate against Reeleezee API and create a session."""
    try:
        client = ReeleezeeClient(body.username, body.password)
    except AuthenticationError as e:
        raise HTTPException(status_code=401, detail=str(e))

    encrypted = encrypt_credentials(body.username, body.password)
    session_id = create_session(encrypted, client.administrations)

    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=86400,  # 24 hours
    )

    return LoginResponse(
        message="Authenticated successfully",
        administrations=client.administrations,
    )


@router.post("/logout")
def logout(response: Response, session: dict = Depends(get_current_session)):
    """Clear the current session."""
    delete_session(session["id"])
    response.delete_cookie("session_id")
    return {"message": "Logged out"}


@router.get("/me")
def me(session: dict = Depends(get_current_session)):
    """Return current session info."""
    admins = session.get("administrations", "[]")
    if isinstance(admins, str):
        admins = json.loads(admins)
    return {
        "authenticated": True,
        "administrations": admins,
        "created_at": session.get("created_at"),
        "expires_at": session.get("expires_at"),
    }
