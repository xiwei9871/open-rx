FROM python:3.12-slim

WORKDIR /srv
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
ARG PIP_INDEX_URL=""
RUN pip install --no-cache-dir ${PIP_INDEX_URL:+--index-url "$PIP_INDEX_URL"} \
    -r requirements.txt

COPY . .
EXPOSE 8000

# Runtime only — least-privilege DB role, no admin DSN. Schema/seed run in the
# separate `migrate` compose service (owns easyrs_admin credentials).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
