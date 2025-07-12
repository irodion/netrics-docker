#!/bin/sh

IMG_NAME=$1
DOCKERFILE_PATH=$2

# Detect container runtime (docker or podman)
if command -v podman >/dev/null 2>&1; then
    CONTAINER_CMD="podman"
elif command -v docker >/dev/null 2>&1; then
    CONTAINER_CMD="docker"
else
    echo "Neither Docker nor Podman found. Please install one of them."
    exit 1
fi

echo "Using $CONTAINER_CMD to build and run container..."

$CONTAINER_CMD build -t $IMG_NAME $DOCKERFILE_PATH
if [ $? -eq 0 ]; then
    echo "Build succeeded"
else
    echo "Build failed. Exiting"
    exit 1
fi

# Ensure volume directory exists with proper permissions
mkdir -p ./volumes/netrics/result
chmod 755 ./volumes/netrics/result
# Set ownership to match container user (1000:1000)
if [ "$(id -u)" = "0" ]; then
    chown 1000:1000 ./volumes/netrics/result 2>/dev/null || true
fi

# Run with additional capabilities for network tools (ping, traceroute)
if [ "$CONTAINER_CMD" = "podman" ]; then
    $CONTAINER_CMD run --rm -i --name netrics-container --cap-add=NET_RAW -v ./volumes/netrics/result:/home/netrics/result:Z $IMG_NAME
else
    $CONTAINER_CMD run --rm -i --name netrics-container -v ./volumes/netrics/result:/home/netrics/result $IMG_NAME
fi
