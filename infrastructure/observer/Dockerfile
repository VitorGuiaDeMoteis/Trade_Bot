FROM python:3.12-alpine
WORKDIR /opt/observer
COPY worker.py prompt.txt ./
USER 65534:65534
ENTRYPOINT ["python", "-I", "-B", "/opt/observer/worker.py"]
