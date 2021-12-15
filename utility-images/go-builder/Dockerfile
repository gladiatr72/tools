FROM golang

USER 0

RUN \
    apt -qq update && apt -y install git && \
    groupadd -g 1000 user && \
    useradd -g user user && \
    mkdir -pv ~user/go && \
    chown -Rv user:user ~user && \
    find /var -type f -atime 0 -delete


COPY rc/* /home/user/

USER 1000
ENV GOPATH=/home/user/go

WORKDIR /home/user/go

ENTRYPOINT ["/bin/bash", "-c"]

CMD ["while [[ ! -f /tmp/stop ]]; do sleep 1; done"]
