"""Customer PII repository with AES-GCM encryption and TTL deletion (MVP-83)."""

from __future__ import annotations

import uuid
from contextlib import nullcontext
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from booking_agent.booking.models import CustomerRecord
from booking_agent.shared.clock import Clock, SystemClock
from booking_agent.shared.db import DatabasePool
from booking_agent.shared.pii import PiiCipher, mask_email, mask_name, mask_phone

if TYPE_CHECKING:
    import aiosqlite

_PURGED_MARKER = "[PURGED]"


class CustomerRepository:
    """Manages encrypted customer PII in booking_customers with TTL expiration."""

    def __init__(
        self,
        db: DatabasePool,
        cipher: PiiCipher,
        *,
        clock: Clock | None = None,
        default_ttl_days: int = 30,
    ) -> None:
        self._db = db
        self._cipher = cipher
        self._clock = clock or SystemClock()
        self._default_ttl_days = default_ttl_days

    def _row_to_record(self, row: object, *, include_decrypted: bool) -> CustomerRecord:
        deleted_at_raw = row["deleted_at"]  # type: ignore[index]
        is_purged = deleted_at_raw is not None or row["phone_encrypted"] == _PURGED_MARKER  # type: ignore[index]

        if is_purged:
            phone = None
            name = None
            email = None
            masked_p = "***"
            masked_n = "***"
            masked_e = None
        else:
            phone_dec = self._cipher.decrypt(row["phone_encrypted"])  # type: ignore[index]
            name_dec = self._cipher.decrypt(row["name_encrypted"])  # type: ignore[index]
            email_enc = row["email_encrypted"]  # type: ignore[index]
            email_dec = self._cipher.decrypt(email_enc) if email_enc else None

            masked_p = mask_phone(phone_dec)
            masked_n = mask_name(name_dec)
            masked_e = mask_email(email_dec) if email_dec else None

            phone = phone_dec if include_decrypted else None
            name = name_dec if include_decrypted else None
            email = email_dec if include_decrypted else None

        return CustomerRecord(
            customer_id=row["customer_id"],  # type: ignore[index]
            masked_phone=masked_p,
            masked_name=masked_n,
            masked_email=masked_e,
            phone=phone,
            name=name,
            email=email,
            created_at=datetime.fromisoformat(row["created_at"]),  # type: ignore[index]
            expires_at=datetime.fromisoformat(row["expires_at"]),  # type: ignore[index]
            deleted_at=datetime.fromisoformat(deleted_at_raw) if deleted_at_raw else None,
        )

    async def upsert_customer(
        self,
        *,
        phone: str,
        name: str,
        email: str | None = None,
        ttl_days: int | None = None,
        conn: aiosqlite.Connection | None = None,
    ) -> CustomerRecord:
        """Create or update an encrypted customer record with a sliding TTL."""
        now = self._clock.utc_now()
        expires_at = now + timedelta(days=ttl_days or self._default_ttl_days)
        phone_hash = self._cipher.hash_value(phone)
        phone_enc = self._cipher.encrypt(phone.strip())
        name_enc = self._cipher.encrypt(name.strip())
        email_enc = self._cipher.encrypt(email.strip()) if email else None

        tx_ctx = nullcontext(conn) if conn is not None else self._db.transaction()
        async with tx_ctx as active_conn:
            cursor = await active_conn.execute(
                """
                SELECT * FROM booking_customers
                WHERE phone_hash = ? AND deleted_at IS NULL
                """,
                (phone_hash,),
            )
            existing = await cursor.fetchone()
            if existing is not None:
                customer_id = existing["customer_id"]
                await active_conn.execute(
                    """
                    UPDATE booking_customers
                    SET phone_encrypted = ?,
                        name_encrypted = ?,
                        email_encrypted = ?,
                        expires_at = ?
                    WHERE customer_id = ?
                    """,
                    (phone_enc, name_enc, email_enc, expires_at.isoformat(), customer_id),
                )
            else:
                customer_id = f"cust_{uuid.uuid4().hex[:20]}"
                await active_conn.execute(
                    """
                    INSERT INTO booking_customers (
                        customer_id, phone_hash, phone_encrypted, name_encrypted,
                        email_encrypted, created_at, expires_at, deleted_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        customer_id,
                        phone_hash,
                        phone_enc,
                        name_enc,
                        email_enc,
                        now.isoformat(),
                        expires_at.isoformat(),
                    ),
                )
            cursor = await active_conn.execute(
                "SELECT * FROM booking_customers WHERE customer_id = ?",
                (customer_id,),
            )
            row = await cursor.fetchone()
        return self._row_to_record(row, include_decrypted=False)

    async def get_customer(
        self,
        customer_id: str,
        *,
        include_decrypted: bool = False,
    ) -> CustomerRecord | None:
        async with self._db.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM booking_customers WHERE customer_id = ?",
                (customer_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_record(row, include_decrypted=include_decrypted)

    async def find_by_phone(
        self,
        phone: str,
        *,
        include_decrypted: bool = False,
    ) -> CustomerRecord | None:
        phone_hash = self._cipher.hash_value(phone)
        async with self._db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT * FROM booking_customers
                WHERE phone_hash = ? AND deleted_at IS NULL
                """,
                (phone_hash,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_record(row, include_decrypted=include_decrypted)

    async def purge_expired(self, *, now: datetime | None = None) -> int:
        """Irreversibly scrub expired PII fields (preserving FK integrity) and return count."""
        cutoff = (now or self._clock.utc_now()).isoformat()
        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                """
                UPDATE booking_customers
                SET phone_hash = 'purged_' || customer_id,
                    phone_encrypted = ?,
                    name_encrypted = ?,
                    email_encrypted = NULL,
                    deleted_at = ?
                WHERE expires_at <= ? AND deleted_at IS NULL
                """,
                (_PURGED_MARKER, _PURGED_MARKER, cutoff, cutoff),
            )
            return cursor.rowcount or 0
