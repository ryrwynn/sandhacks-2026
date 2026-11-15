# Next.js app. Built without .env: MAP_BOX_API_KEY and API_INTERNAL_URL are read at request time.
FROM node:22-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build
EXPOSE 3000
CMD ["npm", "start", "--", "-p", "3000", "-H", "0.0.0.0"]
