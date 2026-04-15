"""
Intake Adapter 层 — 将来自不同医院/诊所的原始数据转换为内部标准格式。

新增数据源步骤：
  1. 继承 BaseIntakeAdapter，实现 _map(raw_data) -> dict
  2. 在 _REGISTRY 中注册 source 名称
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from .serializers import validate_order_input
from .exceptions import ValidationError


# ---------------------------------------------------------------------------
# 内部标准格式
# ---------------------------------------------------------------------------

@dataclass
class InternalOrder:
    first_name:           str
    last_name:            str
    mrn:                  Optional[str]
    date_of_birth:        Optional[str]
    provider_name:        str                    # "FirstName LastName"
    npi:                  Optional[str]
    medication_name:      str
    primary_diagnosis:    str
    additional_diagnoses: list  = field(default_factory=list)
    patient_records:      str   = ''


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------

class BaseIntakeAdapter(ABC):

    def parse(self, raw_data) -> InternalOrder:
        """解析原始数据，返回 InternalOrder。"""
        mapped = self._map(raw_data)
        order  = self._build(mapped)
        self.validate(order)
        return order

    @abstractmethod
    def _map(self, raw_data) -> dict:
        """子类实现：将原始字段映射为标准 key。"""

    def validate(self, order: InternalOrder) -> None:
        """
        复用 serializers.validate_order_input() 的验证逻辑。
        将 InternalOrder 转回 validate_order_input 期望的 dict 结构。
        """
        provider_name_parts = (order.provider_name or '').split(' ', 1)
        provider_first = provider_name_parts[0] if len(provider_name_parts) > 0 else ''
        provider_last  = provider_name_parts[1] if len(provider_name_parts) > 1 else ''

        data = {
            'patient': {
                'first_name':    order.first_name,
                'last_name':     order.last_name,
                'mrn':           order.mrn,
                'date_of_birth': order.date_of_birth,
            },
            'provider': {
                'first_name': provider_first,
                'last_name':  provider_last,
                'npi':        order.npi,
            },
            'primary_diagnosis':    order.primary_diagnosis,
            'additional_diagnoses': order.additional_diagnoses,
        }

        try:
            validate_order_input(data)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @staticmethod
    def _build(mapped: dict) -> InternalOrder:
        return InternalOrder(
            first_name=mapped.get('first_name', ''),
            last_name=mapped.get('last_name', ''),
            mrn=mapped.get('mrn'),
            date_of_birth=mapped.get('date_of_birth'),
            provider_name=mapped.get('provider_name', ''),
            npi=mapped.get('npi'),
            medication_name=mapped.get('medication_name', ''),
            primary_diagnosis=mapped.get('primary_diagnosis', ''),
            additional_diagnoses=mapped.get('additional_diagnoses', []),
            patient_records=mapped.get('patient_records', ''),
        )


# ---------------------------------------------------------------------------
# 具体 Adapter — ClinicAdapter（小型诊所 JSON）
# ---------------------------------------------------------------------------

class ClinicAdapter(BaseIntakeAdapter):
    """
    字段映射:
        fname       → first_name
        lname       → last_name
        patient_id  → mrn
        dob         → date_of_birth
        doctor      → provider_name
        doc_npi     → npi
        drug        → medication_name
        diagnosis   → primary_diagnosis
        other_diags → additional_diagnoses
        notes       → patient_records
    """

    def _map(self, raw_data: dict) -> dict:
        return {
            'first_name':           raw_data.get('fname', ''),
            'last_name':            raw_data.get('lname', ''),
            'mrn':                  raw_data.get('patient_id'),
            'date_of_birth':        raw_data.get('dob'),
            'provider_name':        raw_data.get('doctor', ''),
            'npi':                  raw_data.get('doc_npi'),
            'medication_name':      raw_data.get('drug', ''),
            'primary_diagnosis':    raw_data.get('diagnosis', ''),
            'additional_diagnoses': raw_data.get('other_diags', []),
            'patient_records':      raw_data.get('notes', ''),
        }


# ---------------------------------------------------------------------------
# 具体 Adapter — PharmaAdapter（PharmaCorp XML 转 dict）
# ---------------------------------------------------------------------------

class PharmaAdapter(BaseIntakeAdapter):
    """
    字段映射:
        PatientFirstName  → first_name
        PatientLastName   → last_name
        MedicalRecordNum  → mrn
        DateOfBirth       → date_of_birth
        ReferringProvider → provider_name
        ProviderNPI       → npi
        MedicationName    → medication_name
        PrimaryDiagnosis  → primary_diagnosis
        SecondaryDiagnoses→ additional_diagnoses
        ClinicalNotes     → patient_records
    """

    def _map(self, raw_data: dict) -> dict:
        return {
            'first_name':           raw_data.get('PatientFirstName', ''),
            'last_name':            raw_data.get('PatientLastName', ''),
            'mrn':                  raw_data.get('MedicalRecordNum'),
            'date_of_birth':        raw_data.get('DateOfBirth'),
            'provider_name':        raw_data.get('ReferringProvider', ''),
            'npi':                  raw_data.get('ProviderNPI'),
            'medication_name':      raw_data.get('MedicationName', ''),
            'primary_diagnosis':    raw_data.get('PrimaryDiagnosis', ''),
            'additional_diagnoses': raw_data.get('SecondaryDiagnoses', []),
            'patient_records':      raw_data.get('ClinicalNotes', ''),
        }


# ---------------------------------------------------------------------------
# 工厂
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, type[BaseIntakeAdapter]] = {
    'clinic': ClinicAdapter,
    'pharma': PharmaAdapter,
}


def get_adapter(source: str) -> BaseIntakeAdapter:
    """
    根据 source 返回对应 Adapter 实例。
    未知 source 时抛出 ValidationError。

    用法：
        adapter = get_adapter('clinic')
        order   = adapter.parse(raw_json_dict)
    """
    adapter_cls = _REGISTRY.get(source.lower())
    if adapter_cls is None:
        known = ', '.join(_REGISTRY)
        raise ValidationError(f"Unknown source '{source}'. Known sources: {known}")
    return adapter_cls()



# ---------------------------------------------------------------------------
# 具体 Adapter — Hospital System（Dict）
# ---------------------------------------------------------------------------

class HospitalAdapter(BaseIntakeAdapter):
    """
    字段映射:
        pt_given_name        → first_name
        pt_family_name       → last_name
        pt_medical_id        → mrn
        pt_birth_date        → date_of_birth
        attending_physician  → provider_name
        physician_npi_code   → npi
        prescribed_drug      → medication_name
        primary_icd10        → primary_diagnosis
        secondary_icd10_list → additional_diagnoses
        clinical_summary     → patient_records
    """

    def _map(self, raw_data: dict) -> dict:
        return {
            'first_name':           raw_data.get('pt_given_name', ''),
            'last_name':            raw_data.get('pt_family_name', ''),
            'mrn':                  raw_data.get('pt_medical_id'),
            'date_of_birth':        raw_data.get('pt_birth_date'),
            'provider_name':        raw_data.get('attending_physician', ''),
            'npi':                  raw_data.get('physician_npi_code'),
            'medication_name':      raw_data.get('prescribed_drug', ''),
            'primary_diagnosis':    raw_data.get('primary_icd10', ''),
            'additional_diagnoses': raw_data.get('secondary_icd10_list', []),
            'patient_records':      raw_data.get('clinical_summary', ''),
        }