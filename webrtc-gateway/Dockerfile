FROM golang:1.22-alpine AS builder

WORKDIR /app
COPY go.mod ./
RUN go mod download
COPY . ./
RUN CGO_ENABLED=0 go build -o /bin/webrtc-gateway ./

FROM alpine:3.20
WORKDIR /app
COPY --from=builder /bin/webrtc-gateway /usr/local/bin/webrtc-gateway
EXPOSE 7000
ENTRYPOINT ["/usr/local/bin/webrtc-gateway"]
