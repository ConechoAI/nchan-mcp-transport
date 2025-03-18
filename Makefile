all: build

build-nchan:
    sudo docker build --platform=linux/amd64 --no-cache -t d.conecho.dev:5000/nchan-proxy:latest -f docker/Dockerfile.nchan .

build-video:
    sudo docker build --platform=linux/amd64 --no-cache -t d.conecho.dev:5000/video-mcp-nchan:latest -f docker/Dockerfile.py_video .
