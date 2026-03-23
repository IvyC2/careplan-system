"""
Medical Care Plan System - Django Models
医疗护理计划系统 - 数据模型
"""

from django.db import models
from django.core.validators import RegexValidator


class Patient(models.Model):
    """
    Represents a patient in the system.
    代表系统中的患者。
    """

    # Patient's first name / 患者名字
    first_name = models.CharField(max_length=100)

    # Patient's last name / 患者姓氏
    last_name = models.CharField(max_length=100)

    # Medical Record Number: unique 6-digit identifier / 病历号：唯一的6位数字编号
    mrn = models.CharField(
        max_length=6,
        unique=True,
        validators=[
            RegexValidator(
                regex=r'^\d{6}$',
                message="MRN must be exactly 6 digits. / 病历号必须为6位数字。"
            )
        ],
        help_text="6-digit unique Medical Record Number / 6位唯一病历号"
    )

    # Patient's date of birth / 患者出生日期
    date_of_birth = models.DateField()

    class Meta:
        verbose_name = "Patient"
        verbose_name_plural = "Patients"
        ordering = ["last_name", "first_name"]

    def __str__(self):
        # Format: "Last, First (MRN: 000001)"
        return f"{self.last_name}, {self.first_name} (MRN: {self.mrn})"


class Provider(models.Model):
    """
    Represents a medical provider (doctor/clinician) in the system.
    代表系统中的医疗提供者（医生/临床医师）。
    """

    # Provider's first name / 医疗提供者名字
    first_name = models.CharField(max_length=100)

    # Provider's last name / 医疗提供者姓氏
    last_name = models.CharField(max_length=100)

    # National Provider Identifier: unique 10-digit identifier (US standard)
    # 国家提供者标识符：唯一的10位数字编号（美国标准）
    npi = models.CharField(
        max_length=10,
        unique=True,
        validators=[
            RegexValidator(
                regex=r'^\d{10}$',
                message="NPI must be exactly 10 digits. / NPI必须为10位数字。"
            )
        ],
        help_text="10-digit National Provider Identifier / 10位国家提供者标识符"
    )

    class Meta:
        verbose_name = "Provider"
        verbose_name_plural = "Providers"
        ordering = ["last_name", "first_name"]

    def __str__(self):
        # Format: "Dr. Last, First (NPI: 1234567890)"
        return f"Dr. {self.last_name}, {self.first_name} (NPI: {self.npi})"


class Order(models.Model):
    """
    Represents a medical order linking a patient to a provider,
    including medication and diagnosis information.
    代表一个医疗医嘱，将患者与医疗提供者关联，并包含药物和诊断信息。
    """

    # Associated patient (deleting a patient cascades to their orders)
    # 关联患者（删除患者时级联删除其医嘱）
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="orders",
        help_text="The patient this order belongs to / 该医嘱所属的患者"
    )

    # Associated provider (protect provider from deletion if they have orders)
    # 关联医疗提供者（若有关联医嘱则禁止删除提供者）
    provider = models.ForeignKey(
        Provider,
        on_delete=models.PROTECT,
        related_name="orders",
        help_text="The provider who issued this order / 开具该医嘱的医疗提供者"
    )

    # Name of the prescribed medication / 处方药物名称
    medication_name = models.CharField(
        max_length=255,
        help_text="Name of the prescribed medication / 处方药物名称"
    )

    # Primary diagnosis in ICD-10 format (e.g., "J18.9", "E11.65")
    # ICD-10格式的主要诊断（例如："J18.9"、"E11.65"）
    primary_diagnosis = models.CharField(
        max_length=10,
        validators=[
            RegexValidator(
                regex=r'^[A-Z]\d{2}(\.\d{1,4})?$',
                message=(
                    "Primary diagnosis must be in ICD-10 format (e.g., J18.9). "
                    "/ 主要诊断必须符合ICD-10格式（例如：J18.9）。"
                )
            )
        ],
        help_text="ICD-10 formatted primary diagnosis code / ICD-10格式的主要诊断代码"
    )

    # Additional diagnoses stored as a JSON list of ICD-10 codes
    # 以JSON列表存储的附加诊断（ICD-10代码列表）
    additional_diagnoses = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "List of additional ICD-10 diagnosis codes / "
            "附加ICD-10诊断代码列表，例如：[\"E11.65\", \"I10\"]"
        )
    )

    # Patient's medication history stored as a JSON list
    # 以JSON列表存储的患者用药历史
    medication_history = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "List of previously used medications / "
            "既往用药记录列表，例如：[\"Metformin 500mg\", \"Lisinopril 10mg\"]"
        )
    )

    # Free-text field for relevant patient records and clinical notes
    # 相关患者记录和临床注释的自由文本字段
    patient_records = models.TextField(
        blank=True,
        help_text="Clinical notes and relevant patient record details / 临床注释及相关患者病历详情"
    )

    # Timestamp automatically set when the order is created
    # 医嘱创建时自动记录的时间戳
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the order was created / 医嘱创建时间"
    )

    class Meta:
        verbose_name = "Order"
        verbose_name_plural = "Orders"
        ordering = ["-created_at"]

    def __str__(self):
        # Format: "Order #1 - Last, First | Aspirin (J18.9)"
        return (
            f"Order #{self.pk} - {self.patient} | "
            f"{self.medication_name} ({self.primary_diagnosis})"
        )


class CarePlan(models.Model):
    """
    Represents an AI-generated care plan associated with a specific order.
    代表与特定医嘱关联的AI生成的护理计划（一对一关系）。
    """

    class Status(models.TextChoices):
        """
        Enumeration of possible care plan statuses.
        护理计划可能状态的枚举。
        """
        PENDING    = "pending",    "Pending / 待处理"
        PROCESSING = "processing", "Processing / 处理中"
        COMPLETED  = "completed",  "Completed / 已完成"
        FAILED     = "failed",     "Failed / 失败"

    # One-to-one relationship with Order (each order has at most one care plan)
    # 与医嘱的一对一关系（每个医嘱最多对应一个护理计划）
    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="care_plan",
        help_text="The order this care plan is generated from / 该护理计划所对应的医嘱"
    )

    # LLM-generated care plan content / LLM生成的护理计划内容
    content = models.TextField(
        blank=True,
        help_text="LLM-generated care plan content / 由大型语言模型生成的护理计划内容"
    )

    # Current processing status of the care plan / 护理计划当前的处理状态
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        help_text="Current status of the care plan / 护理计划当前状态"
    )

    # Timestamp automatically set when the care plan is created
    # 护理计划创建时自动记录的时间戳
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the care plan was created / 护理计划创建时间"
    )

    # Timestamp automatically updated whenever the care plan is saved
    # 每次保存护理计划时自动更新的时间戳
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when the care plan was last updated / 护理计划最后更新时间"
    )

    class Meta:
        verbose_name = "Care Plan"
        verbose_name_plural = "Care Plans"
        ordering = ["-created_at"]

    def __str__(self):
        # Format: "CarePlan #1 [completed] - Order #3"
        return f"CarePlan #{self.pk} [{self.status}] - Order #{self.order_id}"