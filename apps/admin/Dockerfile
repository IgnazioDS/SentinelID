FROM node:18-alpine

WORKDIR /app

ENV NEXT_TELEMETRY_DISABLED=1

COPY package*.json ./
RUN npm ci --no-audit --no-fund

COPY . .

RUN npm run build

EXPOSE 3000

CMD ["npm", "start"]
