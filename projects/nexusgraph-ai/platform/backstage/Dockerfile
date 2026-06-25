# Stage 1: scaffold + build a Backstage backend on Node 20.
FROM node:20-bookworm AS build
WORKDIR /work
ENV CI=true
# Scaffold a Backstage app non-interactively (pinned). --path sets dir+name, --skip-install lets us control install.
# Pipe the app name to stdin since create-app 0.5.25 prompts interactively even with CI=true.
RUN echo "streamflix-backstage" | npx --yes @backstage/create-app@0.5.25 --path streamflix-backstage --skip-install
WORKDIR /work/streamflix-backstage
# Overlay our app-config (SQLite + guest + file catalog location).
COPY app-config.yaml ./app-config.production.yaml
RUN corepack enable && yarn install --network-timeout 600000
RUN yarn tsc && yarn build:backend --config app-config.yaml --config app-config.production.yaml

# Stage 2: runtime.
FROM node:20-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /work/streamflix-backstage/yarn.lock /work/streamflix-backstage/package.json ./
COPY --from=build /work/streamflix-backstage/packages/backend/dist/skeleton.tar.gz ./
RUN tar xzf skeleton.tar.gz && rm skeleton.tar.gz && corepack enable && yarn install --production --network-timeout 600000
COPY --from=build /work/streamflix-backstage/packages/backend/dist/bundle.tar.gz ./
RUN tar xzf bundle.tar.gz && rm bundle.tar.gz
COPY app-config.yaml ./app-config.yaml
EXPOSE 7007
CMD ["node", "packages/backend", "--config", "app-config.yaml"]
