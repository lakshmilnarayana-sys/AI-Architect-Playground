FROM golang:1.22-alpine AS build
WORKDIR /src
COPY go.mod ./
RUN go mod download || true
COPY . .
RUN go mod tidy && CGO_ENABLED=0 go build -o /catalog-server .
FROM gcr.io/distroless/static-debian12
COPY --from=build /catalog-server /catalog-server
EXPOSE 7007
ENTRYPOINT ["/catalog-server"]
