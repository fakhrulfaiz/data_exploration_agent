FROM node:20-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Note: Application files are NOT copied here
# They will be mounted as a volume from docker-compose.yml
# This allows hot reload to work properly

# Expose Next.js default port
EXPOSE 3000

# Start the development server with Turbopack for fast refresh
CMD ["npm", "run", "dev", "--", "--turbo"]

