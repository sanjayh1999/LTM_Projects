FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim
COPY --from=builder /app /app
RUN pip install fastapi==0.115.6 "uvicorn[standard]>=0.34"
CMD ["python", "app.py"]