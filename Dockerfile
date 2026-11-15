FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/server-bot

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY bot_server.py ./bot_server.py
COPY modules/ ./modules/
RUN mkdir -p /opt/server-bot/logs

# Docker socket access is required by the current control functions. The
# Compose file drops Linux capabilities, but socket access remains root-equivalent.
USER 0:0
CMD ["python", "bot_server.py"]
