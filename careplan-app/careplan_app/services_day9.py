def process_clinic_order(raw_data: dict) -> CarePlan:
    # 处理小型诊所的JSON格式
    # 1. 把 fname → first_name，lname → last_name，patient_id → mrn...
        # 用for loop 复制一遍 新的名字规则的json

    # 2. 验证数据（NPI 10位、MRN 6位）


    # 3. 重复检测
    # 4. 创建Order，触发CarePlan生成
    pass

def process_pharma_order(raw_data: dict) -> CarePlan:
    # 处理PharmaCorp的XML转dict格式
    # 1. 把 PatientFirstName → first_name，MedicalRecordNum → mrn...
        # 创建json
    # 2. 验证数据
    # 3. 重复检测
    # 4. 创建Order，触发CarePlan生成
    pass