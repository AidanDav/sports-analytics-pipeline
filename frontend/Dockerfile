# Node 20 LTS on Alpine -- small image, all we need is the Vite dev server.
FROM node:20-alpine

WORKDIR /app

# Install dependencies first so Docker caches this layer.
# Only re-runs when package.json or lockfile changes.
COPY package.json package-lock.json ./
RUN npm ci

# Copy source code. In dev, the volume mount overrides this,
# but having it here means the image works standalone too.
COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev"]