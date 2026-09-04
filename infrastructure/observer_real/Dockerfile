ARG PYTHON_IMAGE=sha256:8c3c56c0b12bf22016d4383696838395d4694bb7fa58e0714c4a71a7413ed80a
FROM ${PYTHON_IMAGE} AS python_local
FROM ollama/ollama@sha256:57a73f11f75b32b97b59b003f351445c9c2a8af4b9d586ecdc928dee6150ef26
# Reuse the already installed Python runtime; no second runtime download or pip/apt.
COPY --from=python_local /usr/local /usr/local
COPY --from=python_local /lib/ld-musl-x86_64.so.1 /lib/ld-musl-x86_64.so.1
COPY --from=python_local /usr/lib/libcrypto.so.3 /usr/lib/libcrypto.so.3
COPY --from=python_local /usr/lib/libssl.so.3 /usr/lib/libssl.so.3
COPY --from=python_local /usr/lib/libz.so.1 /usr/lib/libz.so.1
ARG PROMPT_HASH
ARG RESOURCE_PROFILE=deepseek-cpu-v1
LABEL observer.model="deepseek-r1:8b" \
      observer.weights="e6a7edc1a4d7d9b2de136a221a57336b76316cfe53a252aeba814496c5ae439d" \
      observer.prompt=${PROMPT_HASH} \
      observer.profile=${RESOURCE_PROFILE}
COPY --chown=65534:65534 models /opt/observer/models
COPY worker.py prompt.txt output.schema.json profile.json /opt/observer/
ENV HOME=/tmp OLLAMA_NO_CLOUD=1 OLLAMA_HOST=127.0.0.1:11434
USER 65534:65534
WORKDIR /tmp
ENTRYPOINT ["/usr/local/bin/python3", "-I", "-B", "/opt/observer/worker.py"]
