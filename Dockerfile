# Pinned Linux environment from the methodology (Ubuntu 22.04).
# Local work on macOS does not require this image.
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc g++ git python3 python3-venv python3-pip \
    flex bison byacc ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# CBMC from the distro when available; SPIN is built from source in a later week.
RUN apt-get update && apt-get install -y --no-install-recommends cbmc \
    || echo "cbmc package missing on this Ubuntu; install later" \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
COPY pyproject.toml README.md /work/
COPY src /work/src
COPY benchmarks /work/benchmarks
COPY tests /work/tests

RUN python3 -m pip install --no-cache-dir -e ".[dev]"

CMD ["python3", "-m", "semanticdrift", "check-tools"]
