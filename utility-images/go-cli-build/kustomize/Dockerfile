ARG PROJECT
ARG VERSION

FROM gladiatr72/misc:${PROJECT}-${VERSION}-build as builder
FROM alpine

USER root

ARG VERSION
ENV VERSION ${VERSION}

COPY --from=builder /home/user/go/src/github.com/kubernetes-sigs/kustomize/kustomize/kustomize /target/_kustomize-${VERSION}

CMD cp /target/_kustomize-${VERSION} /outbox/
