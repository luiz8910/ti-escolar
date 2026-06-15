FROM node:20-slim

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

EXPOSE 3000
# Em desenvolvimento usamos `next dev` (hot reload). Para produção: build + start.
CMD ["npm", "run", "dev"]
