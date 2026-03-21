import os
import requests
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt


# 内存存储，key 是 order_id，value 是 {status, text}
# 注意：重启服务后数据会消失，这是 MVP 故意的设计
CAREPLANS = {}

ANTHROPIC_API_KEY = os.environ.get("CLAUDE_API_KEY")

def index(request):
    # 返回前端页面
    return render(request, 'index.html')

@csrf_exempt  # 开发阶段先关掉 CSRF 保护，生产环境不能这样做
def generate_careplan(request):
    print("=== generate_careplan called ===")
    if request.method == 'POST':
        print("=== POST request received ===")
        # 从前端表单收集数据
        patient_info = {
            'first_name': request.POST.get('first_name'),
            'last_name': request.POST.get('last_name'),
        }
        medication = request.POST.get('medication')
        diagnosis = request.POST.get('diagnosis')

        # 生成一个简单的 order_id，存到内存里
        order_id = f"order_{len(CAREPLANS)+1}"
        CAREPLANS[order_id] = {'status': 'processing', 'text': None}

        # 拼 prompt，告诉 Claude 要生成什么
        prompt = f"""
        Generate a care plan for the following patient:
        Patient: {patient_info['first_name']} {patient_info['last_name']}
        Medication: {medication}
        Primary Diagnosis: {diagnosis}

        Please include these sections:
        Problem List:
        Goals:
        Pharmacist Interventions:
        Monitoring Plan:

        Important: Use only basic ASCII characters. Do not use special characters like em-dashes (--), 
        smart quotes, or any unicode characters. Use regular hyphens (-) and straight quotes instead.
        """

        try:
            # 调用 Claude API（新版 /v1/messages）
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "claude-sonnet-4-5",
                    "max_tokens": 1024,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                }
            )

            # 从返回结果里取出 care plan 文字
            result = response.json()

            print("API response:", result)
            careplan_text = result['content'][0]['text']
            careplan_text = careplan_text.encode('ascii', errors='replace').decode('ascii')

            print("careplan_text:", careplan_text)

            # 更新内存里的状态
            CAREPLANS[order_id]['status'] = 'completed'
            CAREPLANS[order_id]['text'] = careplan_text

        except Exception as e:
            # 如果出错，标记为 failed
            error_text = str(e).encode('ascii', errors='replace').decode('ascii')
            print("=== ERROR ===", error_text)
            CAREPLANS[order_id]['status'] = 'failed'
            CAREPLANS[order_id]['text'] = error_text

        careplan = CAREPLANS[order_id]
        if careplan.get('text'):
            careplan['text'] = str(careplan['text']).encode('ascii', errors='replace').decode('ascii')
        return render(request, 'index.html', {'careplan': careplan})

    return render(request, 'index.html')