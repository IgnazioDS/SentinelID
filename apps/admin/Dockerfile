FROM node:18-alpine

WORKDIR /app

RUN npm config set fetch-timeout 60000 && \
    npm config set fetch-retries 5 && \
    npm install -g next@latest

COPY package*.json ./
RUN npm install

COPY . .

RUN npm run build

EXPOSE 3000

CMD ["npm", "start"]
