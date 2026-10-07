"""Config flow for DOMO: phone number, then the SMS code."""
from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
)

from . import entry_language
from .api import (
    DomoClient,
    DomoConnectionError,
    DomoRequestError,
    new_client_secret,
    new_device_id,
    normalize_phone,
)
from .const import (
    CONF_ACCESS,
    CONF_CLIENT_SECRET,
    CONF_DEVICE_ID,
    CONF_LANGUAGE,
    CONF_PHONE,
    CONF_REFRESH,
    CONF_SCAN_INTERVAL,
    CONF_USER_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LANGUAGES,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)
CONF_CODE = "code"

LANGUAGE_SELECTOR = SelectSelector(
    SelectSelectorConfig(options=LANGUAGES, translation_key=CONF_LANGUAGE)
)


class DomoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Log in to DOMO with an SMS code."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> DomoOptionsFlow:
        return DomoOptionsFlow()

    def __init__(self) -> None:
        self._client: DomoClient | None = None
        self._phone: str | None = None
        self._session: str | None = None
        self._language: str | None = None

    def _new_client(self, device_id: str, client_secret: str) -> DomoClient:
        return DomoClient(
            async_get_clientsession(self.hass), device_id, client_secret, lang=self._language
        )

    async def _send_code(self, errors: dict[str, str], placeholders: dict[str, str]) -> bool:
        assert self._client is not None and self._phone is not None
        try:
            self._session = await self._client.request_otp(self._phone)
        except DomoRequestError as err:
            if err.code == "invalid_address":
                errors["base"] = "invalid_phone"
            elif err.retry_after:
                errors["base"] = "too_many_requests"
                placeholders["retry_after"] = str(err.retry_after)
            else:
                _LOGGER.warning("DOMO rejected the SMS request: %s", err.code)
                errors["base"] = "otp_request_failed"
                placeholders["error"] = err.code
            return False
        except DomoConnectionError:
            errors["base"] = "cannot_connect"
            return False
        return True

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the phone registered in DOMO and send the SMS."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            self._language = user_input[CONF_LANGUAGE]
            try:
                self._phone = normalize_phone(user_input[CONF_PHONE])
            except ValueError:
                errors["base"] = "invalid_phone"
            else:
                self._client = self._new_client(new_device_id(), new_client_secret())
                if await self._send_code(errors, placeholders):
                    return await self.async_step_otp()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PHONE, default="+998"): str,
                    vol.Required(
                        CONF_LANGUAGE, default=self._language or entry_language(self.hass, None)
                    ): LANGUAGE_SELECTOR,
                }
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_otp(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Check the SMS code and log in."""
        assert self._client is not None and self._session is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                user_id = await self._client.login(self._session, user_input[CONF_CODE].strip())
                await self._client.homes()
            except DomoRequestError as err:
                _LOGGER.debug("DOMO login rejected: %s", err.code)
                errors["base"] = "invalid_code"
            except DomoConnectionError:
                errors["base"] = "cannot_connect"
            else:
                return await self._finish(user_id)
        return self.async_show_form(
            step_id="otp",
            data_schema=vol.Schema({vol.Required(CONF_CODE): str}),
            errors=errors,
            description_placeholders={"phone": self._phone or ""},
        )

    async def _finish(self, user_id: str) -> ConfigFlowResult:
        assert self._client is not None
        data = {
            CONF_PHONE: self._phone,
            CONF_USER_ID: user_id,
            CONF_DEVICE_ID: self._client.device_id,
            CONF_CLIENT_SECRET: self._client.client_secret,
            CONF_ACCESS: self._client.access,
            CONF_REFRESH: self._client.refresh,
        }
        await self.async_set_unique_id(user_id)
        if self.source == SOURCE_REAUTH:
            self._abort_if_unique_id_mismatch(reason="wrong_account")
            return self.async_update_reload_and_abort(self._get_reauth_entry(), data_updates=data)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"DOMO {self._phone}",
            data=data,
            options={CONF_LANGUAGE: self._language},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """The refresh token died: log in again with a new SMS code."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm, then send the SMS to the stored phone."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        placeholders = {"phone": entry.data[CONF_PHONE]}
        if user_input is not None:
            self._phone = entry.data[CONF_PHONE]
            self._language = entry_language(self.hass, entry)
            # Same device identity, so DOMO keeps one session for Home Assistant.
            self._client = self._new_client(entry.data[CONF_DEVICE_ID], entry.data[CONF_CLIENT_SECRET])
            if await self._send_code(errors, placeholders):
                return await self.async_step_otp()
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders=placeholders,
        )


class DomoOptionsFlow(OptionsFlowWithReload):
    """Polling interval and language; the entry reloads to apply them."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            # NumberSelector returns a float; store whole hours.
            return self.async_create_entry(
                data={
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    CONF_LANGUAGE: user_input[CONF_LANGUAGE],
                }
            )
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        language = entry_language(self.hass, self.config_entry)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            max=MAX_SCAN_INTERVAL,
                            step=1,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="h",
                        )
                    ),
                    vol.Required(CONF_LANGUAGE, default=language): LANGUAGE_SELECTOR,
                }
            ),
        )
