# Stage 1: Build
FROM node:18-alpine AS builder

WORKDIR /app

# Package files first so Docker caches the dependency layer
COPY package.json ./

# No lockfile is committed, so install fresh. Vite needs no legacy-peer-deps
# workarounds, but the flag is harmless and keeps parity with the other sites.
RUN npm install --legacy-peer-deps

COPY . .

ENV CI=false
ENV GENERATE_SOURCEMAP=false
ENV NODE_OPTIONS=--max_old_space_size=4096

RUN npm run build

# Stage 2: Production
FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/build /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
