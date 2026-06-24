FROM golang:1.22-alpine AS build
WORKDIR /src
COPY go.mod ./
RUN go mod download || true
COPY . .
RUN CGO_ENABLED=0 go build -o /alert-sink .

FROM gcr.io/distroless/static-debian12
COPY --from=build /alert-sink /alert-sink
EXPOSE 8080
ENTRYPOINT ["/alert-sink"]
