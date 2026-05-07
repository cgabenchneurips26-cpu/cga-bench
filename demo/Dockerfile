# Gradio demo container for HuggingFace Spaces (or any Docker host).
# Build:   docker build -t cga-audit-demo -f demo/Dockerfile .
# Run:     docker run -p 7860:7860 cga-audit-demo

FROM python:3.11-slim

WORKDIR /app

# Install minimal system deps (none required for audit harness proper)
RUN apt-get update && apt-get install -y --no-install-recommends \
      git \
    && rm -rf /var/lib/apt/lists/*

# Copy repo
COPY . /app

# Install Gradio and the audit harness's minimal Python deps
RUN pip install --no-cache-dir -r demo/requirements.txt \
    && pip install --no-cache-dir pyyaml

# The audit harness reads results/full_706_v6_aliasfix_* and
# evidence_pack/analysis/verdict_matrix_v6.json at runtime — ensure
# both are present in the image build context.

ENV PYTHONPATH=/app
EXPOSE 7860

CMD ["python", "demo/app.py"]
