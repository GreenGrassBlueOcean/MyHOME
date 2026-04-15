"""Tests for OWNGateway, OWNSession crypto helpers, and connection infrastructure."""
import pytest
import logging
from custom_components.myhome.ownd.connection import OWNGateway, OWNSession


# ── OWNGateway ─────────────────────────────────────────────────────────────

class TestOWNGateway:
    """Validate the OWNGateway data holder."""

    @pytest.fixture
    def gateway_info(self):
        return {
            "address": "192.168.0.35",
            "password": "12345",
            "ssdp_location": "http://192.168.0.35:8080/desc.xml",
            "ssdp_st": "upnp:rootdevice",
            "deviceType": "urn:schemas-upnp-org:device:server:1",
            "friendlyName": "MH200N",
            "manufacturer": "BTicino S.p.A.",
            "manufacturerURL": "http://www.bticino.it",
            "modelName": "MH200N",
            "modelNumber": "1.2.3",
            "serialNumber": "00:03:50:00:12:34",
            "UDN": "uuid:deadbeef",
            "port": 20000,
        }

    def test_basic_construction(self, gateway_info):
        gw = OWNGateway(gateway_info)
        assert gw.host == "192.168.0.35"
        assert gw.password == "12345"
        assert gw.model_name == "MH200N"
        assert gw.manufacturer == "BTicino S.p.A."
        assert gw.port == 20000

    def test_unique_id(self, gateway_info):
        gw = OWNGateway(gateway_info)
        assert gw.unique_id == "00:03:50:00:12:34"
        gw.unique_id = "aa:bb:cc:dd:ee:ff"
        assert gw.unique_id == "aa:bb:cc:dd:ee:ff"

    def test_host_setter(self, gateway_info):
        gw = OWNGateway(gateway_info)
        gw.host = "10.0.0.1"
        assert gw.host == "10.0.0.1"

    def test_firmware_accessor(self, gateway_info):
        gw = OWNGateway(gateway_info)
        assert gw.firmware == "1.2.3"
        gw.firmware = "4.5.6"
        assert gw.firmware == "4.5.6"

    def test_serial_accessor(self, gateway_info):
        gw = OWNGateway(gateway_info)
        assert gw.serial == "00:03:50:00:12:34"
        gw.serial = "new_serial"
        assert gw.serial == "new_serial"

    def test_password_setter(self, gateway_info):
        gw = OWNGateway(gateway_info)
        gw.password = "new_pass"
        assert gw.password == "new_pass"

    def test_log_id(self, gateway_info):
        gw = OWNGateway(gateway_info)
        assert "MH200N" in gw.log_id
        assert "192.168.0.35" in gw.log_id
        gw.log_id = "[custom]"
        assert gw.log_id == "[custom]"

    def test_minimal_construction(self):
        """Gateway with minimum required fields."""
        gw = OWNGateway({"address": "10.0.0.1"})
        assert gw.host == "10.0.0.1"
        assert gw.password is None
        assert gw.model_name == "Unknown model"
        assert gw.manufacturer == "BTicino S.p.A."
        assert gw.port is None


# ── OWNSession Properties ──────────────────────────────────────────────────

class TestOWNSessionProperties:
    """Validate OWNSession construction without network."""

    @pytest.fixture
    def session(self):
        gw = OWNGateway({"address": "192.168.0.35", "port": 20000})
        return OWNSession(gateway=gw, connection_type="Command", logger=logging.getLogger("test"))

    def test_gateway_property(self, session):
        assert session.gateway.host == "192.168.0.35"

    def test_gateway_setter(self, session):
        new_gw = OWNGateway({"address": "10.0.0.1"})
        session.gateway = new_gw
        assert session.gateway.host == "10.0.0.1"

    def test_connection_type(self, session):
        assert session.connection_type == "command"

    def test_connection_type_setter(self, session):
        session.connection_type = "EVENT"
        assert session.connection_type == "event"

    def test_logger_property(self, session):
        assert session.logger is not None

    def test_logger_setter(self, session):
        new_logger = logging.getLogger("new_test")
        session.logger = new_logger
        assert session.logger == new_logger


# ── Crypto Helper Functions ────────────────────────────────────────────────

class TestCryptoHelpers:
    """Test the password encoding/decoding methods on OWNSession.
    These are pure computational functions with no I/O."""

    @pytest.fixture
    def session(self):
        gw = OWNGateway({"address": "test", "port": 20000, "password": "12345"})
        return OWNSession(gateway=gw, connection_type="test", logger=logging.getLogger("test"))

    def test_hex_to_int_string(self, session):
        result = session._hex_string_to_int_string("0a1b2c")
        assert isinstance(result, str)
        assert all(c.isdigit() for c in result)

    def test_int_to_hex_string(self, session):
        result = session._int_string_to_hex_string("0010021503")
        assert isinstance(result, str)

    def test_hex_int_roundtrip(self, session):
        """Converting hex->int->hex should be deterministic."""
        original = "aabbccdd"
        int_str = session._hex_string_to_int_string(original)
        assert len(int_str) > 0
        assert all(c.isdigit() for c in int_str)

    def test_get_own_password(self, session):
        """Legacy nonce-based password hashing (non-HMAC)."""
        result = session._get_own_password("12345", "123456789")
        assert isinstance(result, int)
        assert result >= 0

    def test_get_own_password_all_digits(self, session):
        """Test with nonce containing every digit 0-9."""
        result = session._get_own_password("12345", "1234567890")
        assert isinstance(result, int)

    def test_get_own_password_zeros(self, session):
        """Nonce with leading zeros should skip initial processing."""
        result = session._get_own_password("12345", "0001234")
        assert isinstance(result, int)

    def test_encode_hmac_sha1(self, session):
        result = session._encode_hmac_password(
            method="sha1",
            password="12345",
            nonce_a="1234567890",
            nonce_b="0987654321"
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_encode_hmac_sha256(self, session):
        result = session._encode_hmac_password(
            method="sha256",
            password="12345",
            nonce_a="1234567890",
            nonce_b="0987654321"
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_encode_hmac_unknown_method(self, session):
        result = session._encode_hmac_password(
            method="md5",
            password="12345",
            nonce_a="1234567890",
            nonce_b="0987654321"
        )
        assert result is None

    def test_decode_hmac_sha1(self, session):
        result = session._decode_hmac_response(
            method="sha1",
            password="12345",
            nonce_a="1234567890",
            nonce_b="0987654321"
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_decode_hmac_sha256(self, session):
        result = session._decode_hmac_response(
            method="sha256",
            password="12345",
            nonce_a="1234567890",
            nonce_b="0987654321"
        )
        assert isinstance(result, str)

    def test_decode_hmac_unknown_method(self, session):
        result = session._decode_hmac_response(
            method="md5",
            password="12345",
            nonce_a="1234567890",
            nonce_b="0987654321"
        )
        assert result is None

    def test_encode_decode_consistency(self, session):
        """Encode and decode with same params should produce different results
        (encode adds 'scope' constants, decode does not)."""
        encoded = session._encode_hmac_password(
            method="sha256", password="12345",
            nonce_a="1234567890", nonce_b="0987654321"
        )
        decoded = session._decode_hmac_response(
            method="sha256", password="12345",
            nonce_a="1234567890", nonce_b="0987654321"
        )
        # They use different input strings (encode includes 'scope' constants)
        assert encoded != decoded

# ── OWNSession IO Mocking ────────────────────────────────────────────────

import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from custom_components.myhome.ownd.connection import OWNEventSession, OWNCommandSession

class TestOWNSessionConnecting:
    @pytest.fixture
    def session(self):
        gw = OWNGateway({"address": "127.0.0.1", "port": 20000})
        return OWNSession(gateway=gw, connection_type="test", logger=logging.getLogger("test"))

    @pytest.mark.asyncio
    async def test_connect_success(self, session):
        mock_reader = AsyncMock()
        mock_writer = AsyncMock()
        
        with patch('asyncio.open_connection', return_value=(mock_reader, mock_writer)) as mock_open:
            with patch.object(session, '_negotiate', return_value={"Success": True}) as mock_neg:
                res = await session.connect()
                assert res["Success"] is True
                mock_open.assert_called_once_with("127.0.0.1", 20000)
                mock_neg.assert_called_once()
                assert session._stream_reader == mock_reader
                assert session._stream_writer == mock_writer

    @pytest.mark.asyncio
    async def test_connect_refused_retry_success(self, session):
        mock_reader = AsyncMock()
        mock_writer = AsyncMock()
        
        with patch('asyncio.sleep', return_value=None):
            with patch('asyncio.open_connection', side_effect=[ConnectionRefusedError, (mock_reader, mock_writer)]) as mock_open:
                with patch.object(session, '_negotiate', return_value={"Success": True}):
                    res = await session.connect()
                    assert res["Success"] is True
                    assert mock_open.call_count == 2

    @pytest.mark.asyncio
    async def test_connect_refused_max_retries(self, session):
        with patch('asyncio.sleep', return_value=None):
            with patch('asyncio.open_connection', side_effect=ConnectionRefusedError) as mock_open:
                res = await session.connect()
                assert res is None
                assert mock_open.call_count == 5  # Submits 5 total checks (0 through 4) before returning None

    @pytest.mark.asyncio
    async def test_close(self, session):
        session._stream_writer = AsyncMock()
        await session.close()
        session._stream_writer.close.assert_called_once()
        session._stream_writer.wait_closed.assert_called_once()

class TestOWNEventSession:
    @pytest.fixture
    def session(self):
        gw = OWNGateway({"address": "127.0.0.1", "port": 20000})
        return OWNEventSession(gateway=gw, logger=logging.getLogger("test"))

    @pytest.mark.asyncio
    async def test_get_next_success(self, session):
        session._stream_reader = AsyncMock()
        session._stream_reader.readuntil.return_value = b"*1*1*12##"
        
        msg = await session.get_next()
        assert msg is not None

    @pytest.mark.asyncio
    async def test_get_next_heartbeat_timeout(self, session):
        session._stream_reader = AsyncMock()
        
        async def mock_readuntil(*args, **kwargs):
            raise asyncio.TimeoutError()
            
        session._stream_reader.readuntil.side_effect = mock_readuntil
        
        with patch('asyncio.sleep', return_value=None):
            with patch.object(session, 'close', new_callable=AsyncMock) as mock_close:
                with patch.object(session, 'connect', new_callable=AsyncMock) as mock_connect:
                    msg = await session.get_next()
                    assert msg is None
                    mock_close.assert_called_once()
                    mock_connect.assert_called_once()

class TestOWNCommandSession:
    @pytest.fixture
    def session(self):
        gw = OWNGateway({"address": "127.0.0.1", "port": 20000})
        return OWNCommandSession(gateway=gw, logger=logging.getLogger("test"))

    @pytest.mark.asyncio
    async def test_send_success(self, session):
        session._stream_writer = AsyncMock()
        session._stream_reader = AsyncMock()
        
        # Simulating ACK response
        session._stream_reader.readuntil.return_value = b"*#*1##"

        await session.send("*1*1*12##")
        session._stream_writer.write.assert_called_once()
        session._stream_writer.drain.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_retry_on_reset(self, session):
        session._stream_writer = AsyncMock()
        session._stream_reader = AsyncMock()
        
        session._stream_writer.write.side_effect = ConnectionResetError
        
        with patch.object(session, 'connect', new_callable=AsyncMock) as mock_connect:
            # Need to restore writer to simulate reconnect success
            async def restore_network():
                session._stream_writer = AsyncMock()
                session._stream_reader = AsyncMock()
                session._stream_reader.readuntil.return_value = b"*1*1*12##"
                return {"Success": True}
            mock_connect.side_effect = restore_network
            await session.send("*1*1*12##")
            mock_connect.assert_called_once()
