FROM golang:1.22-alpine AS build
WORKDIR /src
COPY go.mod ./
RUN go mod download || true
COPY . .
RUN go mod tidy && CGO_ENABLED=0 go build -o /streamflix-service .

FROM gcr.io/distroless/static-debian12
COPY --from=build /streamflix-service /streamflix-service
EXPOSE 8080
ENTRYPOINT ["/streamflix-service"]
