"""Fixtures for MyHOME tests using pytest-homeassistant-custom-component."""
import pytest
from homeassistant.core import HomeAssistant

import platform
import asyncio

# This fixture allows us to load custom components in tests
@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests."""
    yield

def pytest_sessionstart(session):
    """Set the event loop policy to Selector on Windows to avoid _ssock AttributeError."""
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
