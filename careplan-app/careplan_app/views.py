import json
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from .models import Order, CarePlan
from . import services, serializers
from .intake_adapters import get_adapter


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

    data     = serializers.parse_legacy_form(request.POST)
    patient  = services.get_or_create_patient(data['first_name'], data['last_name'])
    provider = services.get_or_create_default_provider()
    order, care_plan = services.create_order_and_careplan(
        patient=patient,
        provider=provider,
        medication_name=data['medication'],
        primary_diagnosis=data['diagnosis'],
        additional_diagnoses=[],
        medication_history=[],
        patient_records='',
    )
    return JsonResponse(
        serializers.serialize_legacy_careplan_response(order, care_plan),
        status=201,
    )


# -----------------------------------------------------------------------------
# REST API endpoints / REST API 端点
# -----------------------------------------------------------------------------

@csrf_exempt
def api_create_order(request):
    """
    POST /api/orders/
    接收 JSON 请求体，创建患者、提供者、医嘱和护理计划（pending），将 careplan_id 入队后立刻返回。
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    confirm = bool(body.get('confirm', False))
    source  = body.get('source', 'webform')

    if source != 'webform':
        # Adapter path: clinic / pharma / ...
        adapter = get_adapter(source)           # raises ValidationError for unknown source
        internal_order = adapter.parse(body)    # maps fields + validates format
        patient, provider, order, care_plan = services.create_order_from_internal(
            internal_order, confirm=confirm,
        )
    else:
        # Webform path: existing flow unchanged
        data = serializers.parse_create_order_body(body)
        serializers.validate_order_input(data)  # raises ValidationError → middleware

        patient = services.get_or_create_patient(**data['patient'])  # raises BlockError / WarningException → middleware

        if data['provider'] is not None:
            provider = services.get_or_create_provider(**data['provider'])  # raises BlockError → middleware
        else:
            provider = services.get_or_create_default_provider()

        order, care_plan = services.create_order_and_careplan(
            patient=patient,
            provider=provider,
            medication_name=data['medication_name'],
            primary_diagnosis=data['primary_diagnosis'],
            additional_diagnoses=data['additional_diagnoses'],
            medication_history=data['medication_history'],
            patient_records=data['patient_records'],
            confirm=confirm,
        )  # raises BlockError / WarningException → middleware

    return JsonResponse(
        serializers.serialize_create_order_response(patient, provider, order, care_plan),
        status=201,
    )


@csrf_exempt
def api_get_order(request, order_id):
    """
    GET /api/orders/<id>/
    从数据库查询指定 Order 及其关联的 CarePlan。
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        order = Order.objects.select_related(
            'patient', 'provider', 'care_plan'
        ).get(pk=order_id)
    except Order.DoesNotExist:
        return JsonResponse({'error': f'Order {order_id} not found'}, status=404)

    return JsonResponse(serializers.serialize_get_order_response(order))


@csrf_exempt
def api_careplan_status(request, careplan_id: int):
    """
    GET /api/careplan/<id>/status/
    返回 CarePlan 的 status 和 content（仅 completed 返回 content；failed 返回 error）。
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        care_plan = CarePlan.objects.get(pk=careplan_id)
    except CarePlan.DoesNotExist:
        return JsonResponse({'error': f'CarePlan {careplan_id} not found'}, status=404)

    return JsonResponse(serializers.serialize_careplan_status_response(care_plan))
