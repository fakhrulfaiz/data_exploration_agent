FROM node:20-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Expose Next.js default port
EXPOSE 3000

# Start the development server with Turbopack for fast refresh
CMD ["npm", "run", "dev", "--", "--turbo"]

