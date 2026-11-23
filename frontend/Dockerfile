FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
COPY scripts/guard-picomatch.mjs ./scripts/
RUN npm ci
COPY . .
ARG VITE_PUBLIC_DATA_MODE=api
ENV VITE_PUBLIC_DATA_MODE=$VITE_PUBLIC_DATA_MODE
ARG VITE_HOME_INTRO=1
ENV VITE_HOME_INTRO=$VITE_HOME_INTRO
RUN npm run build
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY --from=build /app/nginx.generated.conf /etc/nginx/conf.d/default.conf
COPY security-headers.conf /etc/nginx/snippets/security-headers.conf
