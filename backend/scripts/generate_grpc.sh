#!/usr/bin/env bash
# Generate Python gRPC stubs from proto definitions.
# Run from the backend/ directory:
#   bash scripts/generate_grpc.sh

set -euo pipefail

cd "$(dirname "$0")/.."

python -m grpc_tools.protoc \
    -I proto \
    --python_out=blackbeard/grpc \
    --grpc_python_out=blackbeard/grpc \
    proto/blackbeard.proto

echo "gRPC stubs generated in blackbeard/grpc/"
