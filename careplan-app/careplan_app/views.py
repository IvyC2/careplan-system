import os
import json
import random
import requests
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from .models import Patient, Provider, Order, CarePlan
from .tasks import generate_careplan_task
from .llm import generate_careplan_text

ANTHROPIC_API_KEY = os.environ.get("CLAUDE_API_KEY")


# -----------------------------------------------------------------------------
# Shared helpers / 共用辅助函数
# -----------------------------------------------------------------------------

def get_or_create_default_provider():
    """
    Returns the default system provider, creating one if it doesn't exist.
    返回默认系统提供者，如果不存在则自动创建。
    """
    provider, _ = Provider.objects.get_or_create(
        npi="0000000000",
        defaults={
            "first_name": "System",
            "last_name": "Default",
        }
    )
    return provider


def get_or_create_patient(first_name, last_name, mrn=None, date_of_birth=None):
    """
    Finds an existing patient by MRN (if provided) or by name.
    Creates a new one if not found.
    优先按 MRN 查找患者，否则按姓名查找，找不到则自动创建。
    """
    # Look up by MRN first if provided / 优先用 MRN 查找
    if mrn:
        patient = Patient.objects.filter(mrn=mrn).first()
        if patient:
            return patient

    # Fall back to name lookup / 退回到姓名查找
    patient = Patient.objects.filter(
        first_name=first_name,
        last_name=last_name
    ).first()

    if not patient:
        # Generate a unique 6-digit MRN if not supplied / 未提供时自动生成唯一病历号
        if not mrn:
            while True:
                mrn = str(random.randint(100000, 999999))
                if not Patient.objects.filter(mrn=mrn).exists():
                    break

        patient = Patient.objects.create(
            first_name=first_name,
            last_name=last_name,
            mrn=mrn,
            date_of_birth=date_of_birth or "2000-01-01",  # placeholder / 占位值
        )

    return patient


def get_or_create_provider(first_name, last_name, npi=None):
    """
    Finds an existing provider by NPI (if provided) or by name.
    Creates a new one if not found.
    优先按 NPI 查找提供者，否则按姓名查找，找不到则自动创建。
    """
    if npi:
        provider = Provider.objects.filter(npi=npi).first()
        if provider:
            return provider

    provider = Provider.objects.filter(
        first_name=first_name,
        last_name=last_name
    ).first()

    if not provider:
        if not npi:
            # Generate a unique 10-digit NPI placeholder / 生成唯一的10位占位 NPI
            while True:
                npi = str(random.randint(1000000000, 9999999999))
                if not Provider.objects.filter(npi=npi).exists():
                    break

        provider = Provider.objects.create(
            first_name=first_name,
            last_name=last_name,
            npi=npi,
        )

    return provider


def call_llm(patient_name, medication, diagnosis, additional_diagnoses,
             medication_history, patient_records):
    # Backward-compatible wrapper; implementation lives in careplan_app.llm
    return generate_careplan_text(
        patient_name=patient_name,
        medication=medication,
        diagnosis=diagnosis,
        additional_diagnoses=additional_diagnoses,
        medication_history=medication_history,
        patient_records=patient_records,
    )


# -----------------------------------------------------------------------------
# Web views / 页面视图
# -----------------------------------------------------------------------------

def index(request):
    return render(request, 'index.html')


@csrf_exempt
def generate_careplan(request):
    """
    Legacy form POST: persist Order + CarePlan (pending), enqueue, return JSON.
    旧版表单提交：写入医嘱与护理计划（pending）、入队后立即返回 JSON。
    """
    if request.method != 'POST':
        return render(request, 'index.html')

    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    medication = request.POST.get('medication', '').strip()
    diagnosis = request.POST.get('diagnosis', '').strip()

    patient = get_or_create_patient(first_name, last_name)
    provider = get_or_create_default_provider()

    order = Order.objects.create(
        patient=patient,
        provider=provider,
        medication_name=medication,
        primary_diagnosis=diagnosis,
    )

    care_plan = CarePlan.objects.create(
        order=order,
        status=CarePlan.Status.PENDING,
    )
    generate_careplan_task.delay(care_plan.pk)

    return JsonResponse(
        {
            'message': 'Received',
            'careplan_id': care_plan.pk,
            'order_id': order.pk,
            'care_plan': {
                'id': care_plan.pk,
                'status': care_plan.status,
                'content': care_plan.content,
            },
        },
        status=201,
    )


# -----------------------------------------------------------------------------
# New REST API endpoints / 新 REST API 端点
# -----------------------------------------------------------------------------

@csrf_exempt
def api_create_order(request):
    """
    POST /api/orders/
    Accepts JSON body, creates Patient + Provider + Order + CarePlan (pending),
    enqueues careplan_id for async processing, returns immediately.
    接收 JSON 请求体，创建患者、提供者、医嘱和护理计划（pending），将 careplan_id 入队后立刻返回。

    Request body example / 请求体示例:
    {
        "patient": {
            "first_name": "John",
            "last_name": "Doe",
            "mrn": "123456",           // optional / 可选
            "date_of_birth": "1990-01-15"  // optional / 可选
        },
        "provider": {
            "first_name": "Jane",
            "last_name": "Smith",
            "npi": "1234567890"        // optional / 可选
        },
        "medication_name": "Metformin 500mg",
        "primary_diagnosis": "E11.9",
        "additional_diagnoses": ["I10"],      // optional / 可选
        "medication_history": ["Aspirin"],    // optional / 可选
        "patient_records": "..."              // optional / 可选
    }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    # Parse JSON body / 解析 JSON 请求体
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    # Extract patient info / 提取患者信息
    patient_data = body.get('patient', {})
    patient = get_or_create_patient(
        first_name    = patient_data.get('first_name', ''),
        last_name     = patient_data.get('last_name', ''),
        mrn           = patient_data.get('mrn'),
        date_of_birth = patient_data.get('date_of_birth'),
    )

    # Extract provider info, fall back to default if not provided
    # 提取提供者信息，未提供时使用默认提供者
    provider_data = body.get('provider')
    if provider_data:
        provider = get_or_create_provider(
            first_name = provider_data.get('first_name', ''),
            last_name  = provider_data.get('last_name', ''),
            npi        = provider_data.get('npi'),
        )
    else:
        provider = get_or_create_default_provider()

    # Extract order fields / 提取医嘱字段
    medication_name      = body.get('medication_name', '')
    primary_diagnosis    = body.get('primary_diagnosis', '')
    additional_diagnoses = body.get('additional_diagnoses', [])
    medication_history   = body.get('medication_history', [])
    patient_records      = body.get('patient_records', '')

    # Create Order / 创建医嘱
    order = Order.objects.create(
        patient              = patient,
        provider             = provider,
        medication_name      = medication_name,
        primary_diagnosis    = primary_diagnosis,
        additional_diagnoses = additional_diagnoses,
        medication_history   = medication_history,
        patient_records      = patient_records,
    )

    # Create CarePlan (pending) and enqueue for async worker / 待处理并入队，由后续 worker 生成内容
    care_plan = CarePlan.objects.create(
        order=order,
        status=CarePlan.Status.PENDING,
    )
    generate_careplan_task.delay(care_plan.pk)

    return JsonResponse(
        {
            'message': 'Received',
            'careplan_id': care_plan.pk,
            'order_id': order.pk,
            'patient': {
                'id': patient.pk,
                'first_name': patient.first_name,
                'last_name': patient.last_name,
                'mrn': patient.mrn,
            },
            'provider': {
                'id': provider.pk,
                'first_name': provider.first_name,
                'last_name': provider.last_name,
                'npi': provider.npi,
            },
            'medication_name': order.medication_name,
            'primary_diagnosis': order.primary_diagnosis,
            'additional_diagnoses': order.additional_diagnoses,
            'medication_history': order.medication_history,
            'patient_records': order.patient_records,
            'created_at': order.created_at.isoformat(),
            'care_plan': {
                'id': care_plan.pk,
                'status': care_plan.status,
                'content': care_plan.content,
                'created_at': care_plan.created_at.isoformat(),
                'updated_at': care_plan.updated_at.isoformat(),
            },
        },
        status=201,
    )


@csrf_exempt
def api_get_order(request, order_id):
    """
    GET /api/orders/<id>/
    Retrieves an Order and its associated CarePlan from the database.
    从数据库查询指定 Order 及其关联的 CarePlan。
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    # Fetch order / 查找医嘱
    try:
        order = Order.objects.select_related(
            'patient', 'provider', 'care_plan'
        ).get(pk=order_id)
    except Order.DoesNotExist:
        return JsonResponse({'error': f'Order {order_id} not found'}, status=404)

    # Fetch associated care plan / 获取关联的护理计划
    try:
        care_plan = order.care_plan
        care_plan_data = {
            'id':         care_plan.pk,
            'status':     care_plan.status,
            'content':    care_plan.content,
            'created_at': care_plan.created_at.isoformat(),
            'updated_at': care_plan.updated_at.isoformat(),
        }
    except CarePlan.DoesNotExist:
        care_plan_data = None

    return JsonResponse({
        'order_id': order.pk,
        'patient': {
            'id':             order.patient.pk,
            'first_name':     order.patient.first_name,
            'last_name':      order.patient.last_name,
            'mrn':            order.patient.mrn,
            'date_of_birth':  str(order.patient.date_of_birth),
        },
        'provider': {
            'id':         order.provider.pk,
            'first_name': order.provider.first_name,
            'last_name':  order.provider.last_name,
            'npi':        order.provider.npi,
        },
        'medication_name':      order.medication_name,
        'primary_diagnosis':    order.primary_diagnosis,
        'additional_diagnoses': order.additional_diagnoses,
        'medication_history':   order.medication_history,
        'patient_records':      order.patient_records,
        'created_at':           order.created_at.isoformat(),
        'care_plan':            care_plan_data,
    })


@csrf_exempt
def api_careplan_status(request, careplan_id: int):
    """
    GET /api/careplan/<id>/status/
    返回 CarePlan 的 status 和 content（仅 completed 返回 content；failed 返回 error）。
    """
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        care_plan = CarePlan.objects.get(pk=careplan_id)
    except CarePlan.DoesNotExist:
        return JsonResponse({"error": f"CarePlan {careplan_id} not found"}, status=404)

    payload = {
        "careplan_id": care_plan.pk,
        "status": care_plan.status,
    }

    if care_plan.status == CarePlan.Status.COMPLETED:
        payload["content"] = care_plan.content
    elif care_plan.status == CarePlan.Status.FAILED:
        payload["error"] = care_plan.content

    return JsonResponse(payload)