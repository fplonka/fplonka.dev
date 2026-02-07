FROM golang:1.24-bookworm AS builder

WORKDIR /build
COPY go.mod ./
COPY main.go ./
RUN CGO_ENABLED=0 go build -o /build/fplonka-dev .

FROM debian:bookworm-slim

WORKDIR /app
COPY --from=builder /build/fplonka-dev ./
COPY static/ ./static/

EXPOSE 3001
CMD ["./fplonka-dev"]
