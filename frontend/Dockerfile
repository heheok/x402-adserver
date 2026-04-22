# Dev-only image: runs the Vite dev server with HMR. Production build lands in
# Session 12 (Cloud Storage + CDN), so this image is not meant for deploy.

FROM node:20-alpine

WORKDIR /app

# Install deps first for a smaller re-build cache surface.
COPY package.json ./
RUN npm install

# The compose file mounts ./frontend over /app, so this COPY only matters for
# first-run startup when the mount is empty or the user built the image
# standalone.
COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev"]
