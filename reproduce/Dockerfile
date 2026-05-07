FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-fonts-recommended \
    make \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies (scorer + experiment scripts)
COPY requirements-reproduce.txt .
RUN pip install --no-cache-dir -r requirements-reproduce.txt

# Copy project
COPY . .

ENV PYTHONPATH=/app

# Default: run full reproduction pipeline
CMD ["make", "-f", "reproduce/Makefile", "all"]
