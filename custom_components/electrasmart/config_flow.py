"""Config flow for Electra Air Conditioner integration."""
from __future__ import annotations

import logging
from typing import Any

from electra import (
    ATTR_DATA,
    ATTR_RES,
    ATTR_STATUS,
    ATTR_TOKEN,
    STATUS_SUCCESS,
    ElectraAPI,
    ElectraApiError,
    generate_imei,
)
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_SCAN_INTERVAL, CONF_TOKEN
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .const import CONF_IMEI, CONF_OTP, CONF_PHONE_NUMBER, DOMAIN

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Electra Air Conditioner."""

    VERSION = 1

    def __init__(self):
        """Device settings."""
        self._phone_number = None
        self._description_placeholders = None
        self._otp = None
        self._imei = None
        self._token = None
        self._api = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""

        self._api = ElectraAPI(async_get_clientsession(self.hass))
        errors: dict[str, Any] = {}

        if user_input is None:
            return self._show_setup_form(user_input, errors, "user")

        return await self._validate_phone_number(user_input)

    def _show_setup_form(self, user_input=None, errors=None, step_id="user"):
        """Show the setup form to the user."""
        if user_input is None:
            user_input = {}

        if step_id == "user":
            schema = {
                vol.Required(
                    CONF_PHONE_NUMBER, default=user_input.get(CONF_PHONE_NUMBER, "")
                ): str
            }
        else:
            schema = {vol.Required(CONF_OTP, default=user_input.get(CONF_OTP, "")): str}

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(schema),
            errors=errors or {},
            description_placeholders=self._description_placeholders,
        )

    async def _validate_phone_number(self, user_input):
        """Check if config is valid and create entry if so."""

        self._phone_number = user_input[CONF_PHONE_NUMBER]
        self._imei = generate_imei()

        # Check if already configured
        if self.unique_id is None:
            await self.async_set_unique_id(self._phone_number)
            self._abort_if_unique_id_configured()

        try:
            resp = await self._api.generate_new_token(self._phone_number, self._imei)
        except ElectraApiError as exp:
            _LOGGER.error("Failed to connect to API: %s", exp)
            return self._show_setup_form(user_input, {"base": "cannot_connect"}, "user")

        if resp[ATTR_STATUS] == STATUS_SUCCESS:
            if resp[ATTR_DATA][ATTR_RES] != STATUS_SUCCESS:
                return self._show_setup_form(
                    user_input, {CONF_PHONE_NUMBER: "invalid_phone_number"}, "user"
                )

        return await self.async_step_one_time_password()

    async def _validate_one_time_password(self, user_input):
        self._otp = user_input[CONF_OTP]

        try:
            resp = await self._api.validate_one_time_password(
                self._otp, self._imei, self._phone_number
            )
        except ElectraApiError as exp:
            _LOGGER.error("Failed to connect to API: %s", exp)
            return self._show_setup_form(
                user_input, {"base": "cannot_connect"}, CONF_OTP
            )

        if resp[ATTR_DATA][ATTR_RES] == STATUS_SUCCESS:
            self._token = resp[ATTR_DATA][ATTR_TOKEN]

            data = {
                CONF_TOKEN: self._token,
                CONF_IMEI: self._imei,
                CONF_PHONE_NUMBER: self._phone_number,
            }
            return self.async_create_entry(title=self._phone_number, data=data)
        return self._show_setup_form(user_input, {CONF_OTP: "invalid_auth"}, CONF_OTP)

    async def async_step_one_time_password(self, user_input=None, errors=None):
        """Ask the verification code to the user."""
        if errors is None:
            errors = {}

        if user_input is None:
            return await self._show_otp_form(user_input, errors)

        return await self._validate_one_time_password(user_input)

    async def _show_otp_form(self, user_input=None, errors=None):
        """Show the verification_code form to the user."""

        return self.async_show_form(
            step_id=CONF_OTP,
            data_schema=vol.Schema({vol.Required(CONF_OTP): str}),
            errors=errors or {},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle a option flow for AEMET."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Handle options flow."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(CONF_SCAN_INTERVAL),
                ): cv.positive_int,
            }
        )
        return self.async_show_form(step_id="init", data_schema=data_schema)
