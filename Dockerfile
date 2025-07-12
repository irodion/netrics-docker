# syntax=docker/dockerfile:1
# install app dependencies
FROM golang:1.17-bullseye AS build
RUN apt-get update && apt-get upgrade -y
RUN apt-get install -y ca-certificates sudo apt-utils cron net-tools traceroute iputils-ping dnsutils nmap logrotate python3 python3-pip iproute2 curl git scamper

FROM build as modules
# install ndt7-client with Go
ENV GO111MODULE=on
RUN go get github.com/neubot/dash/cmd/dash-client@master
RUN go get github.com/m-lab/ndt7-client-go/cmd/ndt7-client
RUN go get github.com/m-lab/ndt5-client-go/cmd/ndt5-client

# install Ookla speedtest CLI
RUN curl -s https://packagecloud.io/install/repositories/ookla/speedtest-cli/script.deb.sh | sudo bash
RUN sudo apt-get install speedtest

FROM modules as netrics
# Create netrics user with explicit UID/GID for Podman compatibility
RUN groupadd -g 1000 netrics && \
    useradd -u 1000 -g 1000 -ms /bin/bash netrics

# Fix ping permissions for rootless containers (Podman compatibility)
RUN chmod u+s /bin/ping
USER netrics
WORKDIR /home/netrics

# Install Netrics and run as user
RUN pip install netrics-measurements

# Add Netrics path to environment
ENV PATH="/home/netrics/.local/bin:$PATH"

# Initiatlize Netrics
RUN netrics init conf
RUN netrics init comp --shell bash
RUN netrics init serv
# Need to create this path or else the daemon won't run
RUN mkdir -p /home/netrics/.local/state/netrics

# Note: Do NOT create the result path directory - netrics will create it as needed

# Copy local configuration files (instead of using defaults)
# First copy as root, then change ownership to netrics user
COPY --chown=netrics:netrics ./config/measurements.yaml /home/netrics/.config/netrics/measurements.yaml
COPY --chown=netrics:netrics ./config/defaults.yaml /home/netrics/.config/netrics/defaults.yaml
COPY --chown=netrics:netrics ./config/measurements/netrics-* /home/netrics/
COPY --chown=netrics:netrics ./config/measurements/modules/* /home/netrics/

# Set execute permissions and copy to proper locations
RUN chmod +x /home/netrics/netrics-* && \
    cp /home/netrics/netrics-* /home/netrics/.local/bin/ && \
    cp /home/netrics/*.py /home/netrics/.local/lib/python3.9/site-packages/netrics/measurement


# Run Netrics daemon
CMD netrics.d --foreground