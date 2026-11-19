"""Unit tests for PII masking, AES-GCM encryption, and CustomerRepository TTL purge (MVP-83)."""

from __future__ import annotations

from datetime import timedelta

from booking_agent.booking.models import BookingCreateRequest
from booking_agent.booking.service import BookingService
from booking_agent.shared.clock import FakeClock
from booking_agent.shared.pii import (
    PiiCipher,
    mask_email,
    mask_name,
    mask_phone,
    redact_pii_in_dict,
    redact_pii_in_text,
)


def test_pii_cipher_and_redaction_helpers() -> None:
    cipher = PiiCipher("mvp83-secret-key")
    ciphertext = cipher.encrypt("0901234567")
    assert ciphertext.startswith("enc:v1:")
    assert "0901234567" not in ciphertext
    assert cipher.decrypt(ciphertext) == "0901234567"
    assert cipher.hash_value("0901234567") == cipher.hash_value(" 0901234567 ")

    assert mask_phone("0901234567") == "090***4567"
    assert mask_email("khach@pasgo.vn") == "k***@pasgo.vn"
    assert mask_name("Le Thi Hoa") == "L*** T*** H***"

    redacted_text = redact_pii_in_text("SĐT 0901234567, email khach@pasgo.vn, Bearer secret_jwt")
    assert "0901234567" not in redacted_text
    assert "khach@pasgo.vn" not in redacted_text
    assert "secret_jwt" not in redacted_text

    redacted_dict = redact_pii_in_dict(
        {"customer_phone": "0901234567", "api_key": "k123", "site_id": "pasgo"}
    )
    assert redacted_dict["customer_phone"] == "090***4567"
    assert redacted_dict["api_key"] == "***REDACTED***"
    assert redacted_dict["site_id"] == "pasgo"


async def test_customer_repository_ttl_purge(
    booking_service: BookingService,
    fake_clock: FakeClock,
) -> None:
    req = BookingCreateRequest(
        site_id="pasgo",
        restaurant_name="Sen Tay Ho",
        customer_name="Nguyen Van K",
        customer_phone="0911222333",
        party_size=2,
        booking_time=fake_clock.utc_now() + timedelta(hours=4),
    )
    booking, _ = await booking_service.create_booking(req)
    assert await booking_service.customers.purge_expired() == 0

    fake_clock.advance(31 * 86400)
    assert await booking_service.customers.purge_expired() == 1
    purged = await booking_service.customers.get_customer(
        booking.customer_id,
        include_decrypted=True,
    )
    assert purged is not None
    assert purged.phone is None
    assert purged.deleted_at is not None
