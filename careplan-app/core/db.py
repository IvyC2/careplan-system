"""
core/db.py — Database abstraction layer.

DjangoDB  : Django ORM (local / Django runtime)
PostgresDB: psycopg2 raw SQL (Lambda runtime)
"""

import datetime
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional, Tuple


# ---------------------------------------------------------------------------
# Plain data-row types returned by PostgresDB
# (DjangoDB returns ORM instances, which already expose the same attributes.)
# ---------------------------------------------------------------------------

@dataclass
class PatientRow:
    pk: int
    first_name: str
    last_name: str
    mrn: str
    date_of_birth: Any  # str or datetime.date

    def __str__(self):
        return f"{self.last_name}, {self.first_name} (MRN: {self.mrn})"


@dataclass
class ProviderRow:
    pk: int
    first_name: str
    last_name: str
    npi: str

    def __str__(self):
        return f"Dr. {self.last_name}, {self.first_name} (NPI: {self.npi})"


@dataclass
class OrderRow:
    pk: int
    created_at: datetime.datetime


@dataclass
class CarePlanRow:
    pk: int


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class DBInterface(ABC):

    # --- Provider ---

    @abstractmethod
    def get_or_create_provider(self, npi: str, defaults: dict) -> Tuple[Any, bool]:
        """Return (provider, created). Mirrors Django's get_or_create semantics."""

    @abstractmethod
    def filter_provider_by_npi(self, npi: str) -> Optional[Any]: ...

    @abstractmethod
    def filter_provider_by_name(self, first_name: str, last_name: str) -> Optional[Any]: ...

    @abstractmethod
    def provider_npi_exists(self, npi: str) -> bool: ...

    @abstractmethod
    def create_provider(self, first_name: str, last_name: str, npi: str) -> Any: ...

    # --- Patient ---

    @abstractmethod
    def filter_patient_by_mrn(self, mrn: str) -> Optional[Any]: ...

    @abstractmethod
    def filter_patient_by_name_dob(
        self, first_name: str, last_name: str, date_of_birth: Any
    ) -> Optional[Any]: ...

    @abstractmethod
    def filter_patient_by_name(self, first_name: str, last_name: str) -> Optional[Any]: ...

    @abstractmethod
    def patient_mrn_exists(self, mrn: str) -> bool: ...

    @abstractmethod
    def create_patient(
        self, first_name: str, last_name: str, mrn: str, date_of_birth: Any
    ) -> Any: ...

    # --- Order ---

    @abstractmethod
    def filter_order_same_day(
        self, patient: Any, medication_name: str, today: datetime.date
    ) -> Optional[Any]: ...

    @abstractmethod
    def filter_order_previous(
        self, patient: Any, medication_name: str
    ) -> Optional[Any]: ...

    @abstractmethod
    def create_order(
        self,
        patient: Any,
        provider: Any,
        medication_name: str,
        primary_diagnosis: str,
        additional_diagnoses: list,
        medication_history: list,
        patient_records: str,
    ) -> Any: ...

    # --- CarePlan ---

    @abstractmethod
    def create_careplan(self, order: Any, status: str) -> Any: ...


# ---------------------------------------------------------------------------
# DjangoDB — wraps Django ORM
# ---------------------------------------------------------------------------

class DjangoDB(DBInterface):
    """Uses Django ORM. Suitable for local / Django-managed runtime."""

    # Lazy imports keep this module importable without a Django environment.

    def get_or_create_provider(self, npi: str, defaults: dict) -> Tuple[Any, bool]:
        from careplan_app.models import Provider
        return Provider.objects.get_or_create(npi=npi, defaults=defaults)

    def filter_provider_by_npi(self, npi: str) -> Optional[Any]:
        from careplan_app.models import Provider
        return Provider.objects.filter(npi=npi).first()

    def filter_provider_by_name(self, first_name: str, last_name: str) -> Optional[Any]:
        from careplan_app.models import Provider
        return Provider.objects.filter(first_name=first_name, last_name=last_name).first()

    def provider_npi_exists(self, npi: str) -> bool:
        from careplan_app.models import Provider
        return Provider.objects.filter(npi=npi).exists()

    def create_provider(self, first_name: str, last_name: str, npi: str) -> Any:
        from careplan_app.models import Provider
        return Provider.objects.create(first_name=first_name, last_name=last_name, npi=npi)

    def filter_patient_by_mrn(self, mrn: str) -> Optional[Any]:
        from careplan_app.models import Patient
        return Patient.objects.filter(mrn=mrn).first()

    def filter_patient_by_name_dob(
        self, first_name: str, last_name: str, date_of_birth: Any
    ) -> Optional[Any]:
        from careplan_app.models import Patient
        return Patient.objects.filter(
            first_name=first_name, last_name=last_name, date_of_birth=date_of_birth
        ).first()

    def filter_patient_by_name(self, first_name: str, last_name: str) -> Optional[Any]:
        from careplan_app.models import Patient
        return Patient.objects.filter(first_name=first_name, last_name=last_name).first()

    def patient_mrn_exists(self, mrn: str) -> bool:
        from careplan_app.models import Patient
        return Patient.objects.filter(mrn=mrn).exists()

    def create_patient(
        self, first_name: str, last_name: str, mrn: str, date_of_birth: Any
    ) -> Any:
        from careplan_app.models import Patient
        return Patient.objects.create(
            first_name=first_name, last_name=last_name, mrn=mrn, date_of_birth=date_of_birth
        )

    def filter_order_same_day(
        self, patient: Any, medication_name: str, today: datetime.date
    ) -> Optional[Any]:
        from careplan_app.models import Order
        return Order.objects.filter(
            patient=patient,
            medication_name=medication_name,
            created_at__date=today,
        ).first()

    def filter_order_previous(self, patient: Any, medication_name: str) -> Optional[Any]:
        from careplan_app.models import Order
        return Order.objects.filter(
            patient=patient,
            medication_name=medication_name,
        ).first()

    def create_order(
        self,
        patient: Any,
        provider: Any,
        medication_name: str,
        primary_diagnosis: str,
        additional_diagnoses: list,
        medication_history: list,
        patient_records: str,
    ) -> Any:
        from careplan_app.models import Order
        return Order.objects.create(
            patient=patient,
            provider=provider,
            medication_name=medication_name,
            primary_diagnosis=primary_diagnosis,
            additional_diagnoses=additional_diagnoses,
            medication_history=medication_history,
            patient_records=patient_records,
        )

    def create_careplan(self, order: Any, status: str) -> Any:
        from careplan_app.models import CarePlan
        return CarePlan.objects.create(order=order, status=status)


# ---------------------------------------------------------------------------
# PostgresDB — raw psycopg2
# ---------------------------------------------------------------------------

class PostgresDB(DBInterface):
    """
    Uses psycopg2 directly. Suitable for Lambda runtime where Django ORM
    is not available.

    Usage:
        import psycopg2
        conn = psycopg2.connect(dsn)
        db = PostgresDB(conn)
    """

    def __init__(self, conn):
        self._conn = conn

    def _cur(self):
        return self._conn.cursor()

    # --- Provider ---

    def get_or_create_provider(self, npi: str, defaults: dict) -> Tuple[ProviderRow, bool]:
        with self._cur() as cur:
            cur.execute(
                "SELECT id, first_name, last_name, npi"
                " FROM careplan_app_provider WHERE npi = %s",
                (npi,),
            )
            row = cur.fetchone()
            if row:
                return ProviderRow(pk=row[0], first_name=row[1], last_name=row[2], npi=row[3]), False

            first_name = defaults.get("first_name", "")
            last_name = defaults.get("last_name", "")
            cur.execute(
                "INSERT INTO careplan_app_provider (npi, first_name, last_name)"
                " VALUES (%s, %s, %s) RETURNING id",
                (npi, first_name, last_name),
            )
            pk = cur.fetchone()[0]
            self._conn.commit()
            return ProviderRow(pk=pk, first_name=first_name, last_name=last_name, npi=npi), True

    def filter_provider_by_npi(self, npi: str) -> Optional[ProviderRow]:
        with self._cur() as cur:
            cur.execute(
                "SELECT id, first_name, last_name, npi"
                " FROM careplan_app_provider WHERE npi = %s",
                (npi,),
            )
            row = cur.fetchone()
            if row:
                return ProviderRow(pk=row[0], first_name=row[1], last_name=row[2], npi=row[3])
            return None

    def filter_provider_by_name(self, first_name: str, last_name: str) -> Optional[ProviderRow]:
        with self._cur() as cur:
            cur.execute(
                "SELECT id, first_name, last_name, npi"
                " FROM careplan_app_provider"
                " WHERE first_name = %s AND last_name = %s",
                (first_name, last_name),
            )
            row = cur.fetchone()
            if row:
                return ProviderRow(pk=row[0], first_name=row[1], last_name=row[2], npi=row[3])
            return None

    def provider_npi_exists(self, npi: str) -> bool:
        with self._cur() as cur:
            cur.execute("SELECT 1 FROM careplan_app_provider WHERE npi = %s", (npi,))
            return cur.fetchone() is not None

    def create_provider(self, first_name: str, last_name: str, npi: str) -> ProviderRow:
        with self._cur() as cur:
            cur.execute(
                "INSERT INTO careplan_app_provider (first_name, last_name, npi)"
                " VALUES (%s, %s, %s) RETURNING id",
                (first_name, last_name, npi),
            )
            pk = cur.fetchone()[0]
            self._conn.commit()
            return ProviderRow(pk=pk, first_name=first_name, last_name=last_name, npi=npi)

    # --- Patient ---

    def filter_patient_by_mrn(self, mrn: str) -> Optional[PatientRow]:
        with self._cur() as cur:
            cur.execute(
                "SELECT id, first_name, last_name, mrn, date_of_birth"
                " FROM careplan_app_patient WHERE mrn = %s",
                (mrn,),
            )
            row = cur.fetchone()
            if row:
                return PatientRow(pk=row[0], first_name=row[1], last_name=row[2],
                                  mrn=row[3], date_of_birth=row[4])
            return None

    def filter_patient_by_name_dob(
        self, first_name: str, last_name: str, date_of_birth: Any
    ) -> Optional[PatientRow]:
        with self._cur() as cur:
            cur.execute(
                "SELECT id, first_name, last_name, mrn, date_of_birth"
                " FROM careplan_app_patient"
                " WHERE first_name = %s AND last_name = %s AND date_of_birth = %s",
                (first_name, last_name, date_of_birth),
            )
            row = cur.fetchone()
            if row:
                return PatientRow(pk=row[0], first_name=row[1], last_name=row[2],
                                  mrn=row[3], date_of_birth=row[4])
            return None

    def filter_patient_by_name(self, first_name: str, last_name: str) -> Optional[PatientRow]:
        with self._cur() as cur:
            cur.execute(
                "SELECT id, first_name, last_name, mrn, date_of_birth"
                " FROM careplan_app_patient"
                " WHERE first_name = %s AND last_name = %s",
                (first_name, last_name),
            )
            row = cur.fetchone()
            if row:
                return PatientRow(pk=row[0], first_name=row[1], last_name=row[2],
                                  mrn=row[3], date_of_birth=row[4])
            return None

    def patient_mrn_exists(self, mrn: str) -> bool:
        with self._cur() as cur:
            cur.execute("SELECT 1 FROM careplan_app_patient WHERE mrn = %s", (mrn,))
            return cur.fetchone() is not None

    def create_patient(
        self, first_name: str, last_name: str, mrn: str, date_of_birth: Any
    ) -> PatientRow:
        with self._cur() as cur:
            cur.execute(
                "INSERT INTO careplan_app_patient (first_name, last_name, mrn, date_of_birth)"
                " VALUES (%s, %s, %s, %s) RETURNING id",
                (first_name, last_name, mrn, date_of_birth),
            )
            pk = cur.fetchone()[0]
            self._conn.commit()
            return PatientRow(pk=pk, first_name=first_name, last_name=last_name,
                              mrn=mrn, date_of_birth=date_of_birth)

    # --- Order ---

    def filter_order_same_day(
        self, patient: Any, medication_name: str, today: datetime.date
    ) -> Optional[OrderRow]:
        with self._cur() as cur:
            cur.execute(
                "SELECT id, created_at FROM careplan_app_order"
                " WHERE patient_id = %s AND medication_name = %s AND created_at::date = %s",
                (patient.pk, medication_name, today),
            )
            row = cur.fetchone()
            if row:
                return OrderRow(pk=row[0], created_at=row[1])
            return None

    def filter_order_previous(self, patient: Any, medication_name: str) -> Optional[OrderRow]:
        with self._cur() as cur:
            cur.execute(
                "SELECT id, created_at FROM careplan_app_order"
                " WHERE patient_id = %s AND medication_name = %s",
                (patient.pk, medication_name),
            )
            row = cur.fetchone()
            if row:
                return OrderRow(pk=row[0], created_at=row[1])
            return None

    def create_order(
        self,
        patient: Any,
        provider: Any,
        medication_name: str,
        primary_diagnosis: str,
        additional_diagnoses: list,
        medication_history: list,
        patient_records: str,
    ) -> OrderRow:
        with self._cur() as cur:
            cur.execute(
                "INSERT INTO careplan_app_order"
                " (patient_id, provider_id, medication_name, primary_diagnosis,"
                "  additional_diagnoses, medication_history, patient_records, created_at)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())"
                " RETURNING id, created_at",
                (
                    patient.pk,
                    provider.pk,
                    medication_name,
                    primary_diagnosis,
                    json.dumps(additional_diagnoses),
                    json.dumps(medication_history),
                    patient_records,
                ),
            )
            row = cur.fetchone()
            self._conn.commit()
            return OrderRow(pk=row[0], created_at=row[1])

    # --- CarePlan ---

    def create_careplan(self, order: Any, status: str) -> CarePlanRow:
        with self._cur() as cur:
            cur.execute(
                "INSERT INTO careplan_app_careplan"
                " (order_id, status, content, created_at, updated_at)"
                " VALUES (%s, %s, '', NOW(), NOW()) RETURNING id",
                (order.pk, status),
            )
            pk = cur.fetchone()[0]
            self._conn.commit()
            return CarePlanRow(pk=pk)
