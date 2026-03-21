FROM python:3.11

WORKDIR /app

ENV PYTHONIOENCODING=utf-8
ENV LANG=C.UTF-8
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .

# 升级 pip 并安装依赖
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]