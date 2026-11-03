FROM python:3.12-slim

WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY backend /app/backend
COPY fixtures /app/fixtures
ENV PYTHONPATH=/app/backend
ENV MADIRA_DEMO_MODE=true
WORKDIR /app/backend
EXPOSE 8123
CMD ["python", "-m", "madira.main"]
