FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UYGHUR_ASR_MODEL_PATH=/opt/shennong/models/uyghur_asr.onnx

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --create-home app \
    && mkdir -p /var/lib/shennong /opt/shennong/models \
    && chown -R app:app /var/lib/shennong

COPY requirements-production.txt ./
RUN pip install --no-cache-dir -r requirements-production.txt

COPY . ./
RUN python scripts/fetch_uyghur_model.py --destination "$UYGHUR_ASR_MODEL_PATH" \
    && chown -R app:app /app /opt/shennong

USER app
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn production_app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 15 --timeout-graceful-shutdown 30"]
