FROM node:20-alpine AS build
ARG VITE_DEMO=0
ARG VITE_APP_VERSION=dev
ENV VITE_DEMO=$VITE_DEMO VITE_APP_VERSION=$VITE_APP_VERSION
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
