"""Authentication handler for MyStiebel integration."""

import base64
import json
import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp

from .const import (
    APP_NAME,
    APP_VERSION_ANDROID,
    BASE_URL,
    SERVICE_URL,
    TOKEN_REFRESH_MARGIN,
    USER_AGENT,
)
from .rate_limiter import RateLimiter

_LOGGER = logging.getLogger(__name__)


class MyStiebelAuth:
    """Authentication handler for the MyStiebel integration.

    Handles authentication and installation retrieval using the MyStiebel API.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        client_id: str,
    ) -> None:
        """Initialize the authentication handler with session and credentials."""
        self._session = session
        self._username = username
        self._password = password
        self._client_id = client_id
        self.token: str | None = None
        self.token_expiry: datetime | None = None
        self._rate_limiter = RateLimiter()

    async def authenticate(self) -> None:
        """Authenticate with the MyStiebel API and acquire a JWT token."""
        async def _do_auth() -> None:
            headers = {
                "X-SC-ClientApp-Name": APP_NAME,
                "X-SC-ClientApp-Version": APP_VERSION_ANDROID,
                "User-Agent": USER_AGENT,
                "Content-Type": "application/json; charset=utf-8",
                "Accept-Encoding": "gzip",
            }
            payload = {
                "userName": self._username,
                "password": self._password,
                "clientId": self._client_id,
                "rememberMe": True,
            }

            async with self._session.post(
                f"{BASE_URL}/api/v1/Jwt/login", json=payload, headers=headers
            ) as response:
                response.raise_for_status()
                data = await response.json()
                self.token = data.get("token")
                if not self.token:
                    raise ValueError("Authentication succeeded but no token was received")
                # Determine token expiry from JWT payload if available, else default to 24h
                self.token_expiry = self._extract_token_expiry(self.token) or (
                    datetime.now() + timedelta(hours=24)
                )

        await self._rate_limiter(_do_auth)

    @staticmethod
    def _extract_token_expiry(token: str) -> datetime | None:
        """Extract expiration time from a JWT token payload."""
        try:
            parts = token.split(".")
            if len(parts) >= 2:
                padded = parts[1] + "=" * (-len(parts[1]) % 4)
                payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
                exp = payload.get("exp")
                if exp is not None:
                    return datetime.fromtimestamp(float(exp))
        except Exception as e:
            _LOGGER.debug("Could not parse token expiry: %s", e)
        return None

    async def get_installations(self) -> dict[str, Any]:
        """Retrieve installations associated with the authenticated user."""
        await self.ensure_valid_token()

        async def _do_get() -> dict[str, Any]:
            headers = {
                "Authorization": f"Bearer {self.token}",
                "X-SC-ClientApp-Name": APP_NAME,
                "X-SC-ClientApp-Version": APP_VERSION_ANDROID,
                "User-Agent": USER_AGENT,
                "Content-Type": "application/json; charset=utf-8",
                "Accept-Encoding": "gzip",
            }
            payload = {"includeWithPendingUserAccesses": True}
            async with self._session.post(
                f"{SERVICE_URL}/api/v1/InstallationsInfo/own", json=payload, headers=headers
            ) as response:
                response.raise_for_status()
                return await response.json()

        return await self._rate_limiter(_do_get)

    async def ensure_valid_token(self) -> None:
        """Ensure the token is valid, refreshing if necessary."""
        if not self.token or not self.token_expiry:
            await self.authenticate()
            return

        # Check if token needs refresh
        time_until_expiry = (self.token_expiry - datetime.now()).total_seconds()
        if time_until_expiry <= TOKEN_REFRESH_MARGIN:
            _LOGGER.debug("Token expiring soon, refreshing...")
            await self.authenticate()

    def is_token_valid(self) -> bool:
        """Check if the current token is still valid."""
        if not self.token or not self.token_expiry:
            return False
        return datetime.now() < self.token_expiry
